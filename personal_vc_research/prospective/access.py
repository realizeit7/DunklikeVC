"""Republic access investigation (v2.1, Workstream A): bounded, logged, ordinary access attempts only.

What this module does
* One plain HTTP GET per URL (no retries, identifying user agent, no cookies carried between requests).
* One ordinary headless-Chromium page load per URL (Node Playwright, default settings: no stealth plugin, no
  fingerprint changes, no proxy rotation, no stored session). A challenge or login page ends the attempt.
* Every response is classified BEFORE any extraction: challenge / login_required / http_error / public_content.
* Every attempt is written to `access_attempts` (append-only) and to a public CSV log. Raw content is hashed; only
  public, non-challenge content is stored, and never cookies, tokens or credentials.

What it never does (by design, see reports/republic_access_assessment.md): CAPTCHA solving, stealth/fingerprint
evasion, rotating proxies or IPs, copied session tokens, private-endpoint probing, paywall circumvention, or retrying
to defeat a denial. A page captured now is current evidence: it is recorded with the current retrieval time and can
only enter a NEW evidence pack.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .core import Ctx

UA = "personal_vc_research/2.1 (individual non-commercial research)"
CSV_COLS = ["attempt_id", "attempted_utc", "url", "method", "http_status", "final_url", "result", "content_available",
            "visibility", "challenge_state", "login_state", "capture", "content_sha256", "n_bytes", "markers", "note"]

CLASSIFIER_VERSION = "page_classifier_v2"
# v2 (2026-10-15): v1 treated any captcha script include as a challenge, which mislabelled an ordinary Shopify store
# page (form-protection hCaptcha/reCAPTCHA scripts, 200, full product text) as a challenge (attempt 6). v2 separates
# interstitial/block markers (decisive) from widget-script markers (decisive only on a near-empty page).
CHALLENGE_MARKERS = [
    r"cf-chl", r"challenge-platform", r"/cdn-cgi/challenge", r"just a moment\.\.\.", r"attention required",
    r"checking your browser", r"cf-browser-verification", r"px-captcha", r"verify you are (a )?human",
    r"are you a robot", r"enable javascript and cookies to continue", r"ddos protection", r"_incapsula_resource",
    r"request unsuccessful", r"error 1020", r"sorry, you have been blocked", r"access denied"]
WIDGET_MARKERS = [r"cf-turnstile", r"hcaptcha", r"g-recaptcha", r"recaptcha", r"datadome", r"perimeterx"]
LOGIN_MARKERS = [r"<input[^>]+type=[\"']?password", r"sign in to (continue|view)", r"log in to (continue|view)",
                 r"please (log|sign) in", r"create an account to (continue|view)"]
LOGIN_URL = re.compile(r"/(login|log-in|sign_in|sign-in|signin|users/sign_in|auth)(\b|/|\?)", re.I)


def classify_page(status: int | None, url: str, final_url: str, body: str, headers: dict | None = None) -> dict:
    """Classify a response before extraction. Challenge and login checks run on every status (a 200 can be a
    challenge interstitial). Returns result, challenge/login state and the markers that fired."""
    low = (body or "")[:400000].lower()
    hdr = {k.lower(): str(v).lower() for k, v in (headers or {}).items()}
    markers = [m for m in CHALLENGE_MARKERS if re.search(m, low)]
    widgets = [m for m in WIDGET_MARKERS if re.search(m, low)]
    if hdr.get("cf-mitigated") == "challenge":
        markers.append("header:cf-mitigated=challenge")
    login = [m for m in LOGIN_MARKERS if re.search(m, low)]
    if final_url and LOGIN_URL.search(final_url) and not LOGIN_URL.search(url):
        login.append("redirected_to_login_url")
    text_len = len(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", low))).strip())
    if status is None:
        result = "network_error"
    elif markers and (status in (403, 429, 503) or text_len < 3000 or "header:cf-mitigated=challenge" in markers):
        result = "challenge"
    elif widgets and text_len < 300:
        result = "challenge"
    elif login:
        result = "login_required"
    elif status >= 400:
        result = "http_error"
    elif text_len < 200:
        result = "empty_or_script_only"
    else:
        result = "public_content"
    return {"result": result, "challenge_state": "challenge_shown" if result == "challenge" else
            ("markers_present_but_content_served" if markers or widgets else "none_detected"),
            "login_state": "login_required" if result == "login_required" else ("login_prompt_present" if login else "none_detected"),
            "markers": markers + [f"widget:{w}" for w in widgets] + login, "visible_text_chars": text_len,
            "classifier_version": CLASSIFIER_VERSION}


def _record(ctx: Ctx, csv_path: Path, row: dict) -> dict:
    cur = ctx.con.execute(
        """INSERT INTO access_attempts(attempted_utc, url, method, http_status, final_url, result, content_available,
           visibility, challenge_state, login_state, capture, content_sha256, n_bytes, markers, note)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        tuple(json.dumps(row.get(c)) if isinstance(row.get(c), list) else row.get(c) for c in CSV_COLS[1:]))
    ctx.con.commit()
    row["attempt_id"] = cur.lastrowid
    new = not csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS)
        if new:
            w.writeheader()
        w.writerow({c: (json.dumps(row[c]) if isinstance(row.get(c), list) else row.get(c, "")) for c in CSV_COLS})
    return row


def _finish(ctx: Ctx, csv_path: Path, url: str, method: str, status, final_url: str, body: str, headers: dict,
            raw: bytes, note: str, store_public: bool = True) -> dict:
    cl = classify_page(status, url, final_url, body, headers)
    ok = cl["result"] == "public_content"
    sha = hashlib.sha256(raw).hexdigest() if raw else ""
    if ok and store_public:
        ctx.store_blob(raw)      # content-addressed; gitignored blob store; only public non-challenge content
    row = {"attempted_utc": ctx.now(), "url": url, "method": method, "http_status": status, "final_url": final_url,
           "result": cl["result"], "content_available": "yes" if ok else "no",
           "visibility": "public" if ok else ("authenticated" if cl["result"] == "login_required" else "not_determined"),
           "challenge_state": cl["challenge_state"], "login_state": cl["login_state"],
           "capture": "complete_html_snapshot" if ok else "none", "content_sha256": sha, "n_bytes": len(raw or b""),
           "markers": cl["markers"], "note": f"{note} [{cl['classifier_version']}]"}
    return _record(ctx, csv_path, row)


def http_attempt(ctx: Ctx, url: str, csv_path: Path, timeout: int = 30, note: str = "") -> dict:
    """Exactly one GET. No retry on failure: a denial is recorded, not retried."""
    import requests
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=timeout, allow_redirects=True)
    except requests.RequestException as exc:
        return _record(ctx, csv_path, {"attempted_utc": ctx.now(), "url": url, "method": "http_get_single", "http_status": None,
                                       "final_url": "", "result": "network_error", "content_available": "no",
                                       "visibility": "not_determined", "challenge_state": "not_reached",
                                       "login_state": "not_reached", "capture": "none", "content_sha256": "", "n_bytes": 0,
                                       "markers": [], "note": f"{type(exc).__name__}: {str(exc)[:200]}"})
    return _finish(ctx, csv_path, url, "http_get_single", r.status_code, r.url, r.text, dict(r.headers), r.content,
                   note or "plain requests GET, identifying user agent, no cookies, no retry")


NODE_SCRIPT = r"""
const { chromium } = require('playwright');
(async () => {
  const url = process.argv[2];
  const out = { status: null, final_url: '', title: '', html: '', headers: {}, error: null };
  let browser;
  try {
    const opts = { headless: true };
    if (process.env.HTTPS_PROXY) opts.proxy = { server: process.env.HTTPS_PROXY };
    browser = await chromium.launch(opts);
    const context = await browser.newContext();          // fresh, empty, discarded afterwards: no stored session
    const page = await context.newPage();
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(5000);                     // let an ordinary page render; nothing is clicked or solved
    out.status = resp ? resp.status() : null;
    out.headers = resp ? resp.headers() : {};
    out.final_url = page.url();
    out.title = await page.title();
    out.html = await page.content();
  } catch (e) { out.error = String(e).slice(0, 400); }
  if (browser) await browser.close();
  process.stdout.write(JSON.stringify(out));
})();
"""


def browser_available() -> dict:
    node = shutil.which("node")
    if not node:
        return {"available": False, "detail": "node not installed"}
    p = subprocess.run([node, "-e", "require('playwright'); console.log('ok')"], capture_output=True, text=True)
    return {"available": p.returncode == 0, "detail": "container-local headless Chromium via Node Playwright"
            if p.returncode == 0 else p.stderr[:200]}


def browser_attempt(ctx: Ctx, url: str, csv_path: Path) -> dict:
    """One ordinary headless page load in a fresh, discarded browser context. Cookies are never saved."""
    with tempfile.TemporaryDirectory() as d:
        script = Path(d) / "load.js"
        script.write_text(NODE_SCRIPT)
        p = subprocess.run(["node", str(script), url], capture_output=True, text=True, timeout=120)
    try:
        o = json.loads(p.stdout)
    except json.JSONDecodeError:
        o = {"error": (p.stderr or p.stdout)[:400]}
    if o.get("error") and not o.get("html"):
        return _record(ctx, csv_path, {"attempted_utc": ctx.now(), "url": url, "method": "headless_chromium_single",
                                       "http_status": o.get("status"), "final_url": o.get("final_url", ""),
                                       "result": "network_error", "content_available": "no", "visibility": "not_determined",
                                       "challenge_state": "not_reached", "login_state": "not_reached", "capture": "none",
                                       "content_sha256": "", "n_bytes": 0, "markers": [],
                                       "note": f"browser error: {o['error'][:300]}"})
    html = o.get("html", "")
    return _finish(ctx, csv_path, url, "headless_chromium_single", o.get("status"), o.get("final_url", ""), html,
                   o.get("headers") or {}, html.encode(), f"title={o.get('title', '')[:80]!r}; default Playwright "
                   "Chromium, fresh context, no stealth, nothing clicked")


def cooldown_active(ctx: Ctx, host: str = "republic.com", days: int = 7) -> dict | None:
    """A challenge/403 within the cooldown window ends further automated attempts against the host."""
    import datetime as dt
    from .core import iso, parse_utc
    since = iso(parse_utc(ctx.now()) - dt.timedelta(days=days))
    r = ctx.con.execute("SELECT * FROM access_attempts WHERE url LIKE ? AND result IN ('challenge','http_error','login_required') "
                        "AND attempted_utc > ? ORDER BY attempt_id DESC LIMIT 1", (f"%{host}%", since)).fetchone()
    return dict(r) if r else None
