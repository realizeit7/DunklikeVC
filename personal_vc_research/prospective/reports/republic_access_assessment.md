# Republic access assessment (v2.1, Workstream A)

Date of attempts: 2026-10-15 (UTC). Log: `reports/republic_access_attempts.csv` (also in table `access_attempts`, append-only).
Code: `access.py` (attempts and page classifier), `outputs.py::screen_import_file` / `import_evidence` (manual route).

## Conclusion

**From this environment, Republic campaign pages are not accessible by ordinary means.** Both a plain HTTP GET and
an ordinary headless-browser page load received a Cloudflare block page ("Attention Required! | Cloudflare — Sorry,
you have been blocked", HTTP 403). This is a block, not an interactive challenge: no CAPTCHA or login was offered
that a person could complete. Attempts stopped there. This shows what this cloud container can do. It says nothing
about what the user's own browser can do.

**Recommended route: user-assisted import** (section 5). The user opens the page in their own browser, saves it, and
imports it with the existing CSV workflow. The importer now refuses block, challenge, login, error and cookie/token
files before storing anything. SEC filings remain the source of record for terms and financials.

## 1. What was tried (scope: at most 3 campaign URLs; 2 were used)

The campaign URLs come from the issuers' own Form C text in the frozen packs. Hope-Neuron and Mightylicious each
cite `https://republic.com/<slug>` twice. TradeFunded's pack contains no Republic URL. Its website links to
`https://republic.com/tradefunded`, but that URL was **not** tried because the block was already persistent.

| # | UTC | Method | URL | Status | Result |
|---|---|---|---|---|---|
| — | ~16:07 | plain GET | republic.com/hope-neuron | not recorded | completed, but the result was lost to a logging bug (fixed) and never inspected |
| 1 | 16:08:05 | plain GET (identifying UA, no cookies, no retry) | republic.com/hope-neuron | 403 | Cloudflare block page |
| 2 | 16:08:06 | plain GET | republic.com/mightylicious | 403 | Cloudflare block page |
| 3 | 16:08:22 | headless Chromium (default Playwright, fresh context, no stealth, nothing clicked) | republic.com/hope-neuron | 403 | Cloudflare block page |
| 4 | 16:08:28 | headless Chromium | republic.com/mightylicious | 403 | Cloudflare block page |
| 5 | 16:08:44 | plain GET | hopeneuron.com/investors (issuer site) | 200 | public content |
| 6 | 16:08:45 | plain GET | mightylicious.com (issuer site) | 200 | classifier v1 said "challenge": **false positive**, see below |
| 7 | 16:08:46 | plain GET | tradefunded.com (issuer site) | 200 | public content |
| 8–9 | 16:08:54–59 | Wayback availability API (documented) | republic.com/hope-neuron, /mightylicious | 200 | no archived snapshots |
| 10 | 16:09:32 | one manual re-GET to check row 6 | mightylicious.com | 200 | public content (classifier v2) |

Earlier record, from the v1 pilot: on 2026-10-14 `https://republic.com/companies` returned HTTP 403. Earlier WebFetch
attempts on Republic help pages returned 403/525.

**Total Republic requests:** 3 plain GETs (one of them unrecorded) and 2 browser loads. There were no retries after
the block was established, and none against the 3rd URL.

**Classifier false positive (rows 6 and 10).** Classifier v1 treated any CAPTCHA script on a page as a challenge. The
Mightylicious store is an ordinary Shopify page with full product text; its form-protection hCaptcha/reCAPTCHA
scripts triggered the false label. Classifier v2 separates the two kinds of marker:
- block/interstitial markers, which decide the result on their own;
- widget-script markers, which count only when the page is nearly empty.

The original row 6 is kept unchanged (append-only). Row 10 records the check.

## 2. Route-by-route findings

1. **Ordinary public HTTP:** blocked (403 block page) for both campaign URLs. This matches the 2026-10-14 record.
2. **Normal browser access:**
   - This environment has **no integration with the user's own browser** (no Chrome/Claude-in-Chrome tools).
   - The only browser here is container-local headless Chromium. It loaded the same 403 block page. This
     means the container's network origin is blocked, not that the pages are private.
   - Whether the pages are public is **not determined from here.** No login prompt was ever shown, because the block
     comes before any page logic runs.
   - Republic campaign pages are generally viewable logged out in a normal consumer browser, but that was not
     verified in this run.
3. **Official alternatives:**
   - **SEC EDGAR** (Form C, C/A, C-U, C-AR) remains the source of record and is reachable. It carries the offering
     terms, financial statements and progress updates (C-U), but not the campaign page, Q&A or updates tab.
   - **Issuer websites** are reachable. Each holds *issuer claims* observed 2026-10-15:
     - Hope-Neuron: a fundraising page.
     - TradeFunded: "Our community raise is live on Republic".
     - Mightylicious: a banner, "WE'RE RAISING ON REPUBLIC! INVEST NOW", and a "Form C-AR" footer link.
     These are current, issuer-prepared statements. They are not verification of availability, and they are **not**
     inserted into any earlier evidence pack.
   - **Wayback Machine:** the documented availability API returned no snapshots for either campaign URL.
   - **Republic public docs** (help center): previously 403/525 from this environment. Not retried.
4. **User-assisted import:** works and is tested (section 5).

## 3. Page classification before extraction

`access.classify_page` runs on every response and every imported HTML/PDF capture **before** anything is stored or
extracted. It returns one of:

- `challenge` (a block or interstitial)
- `login_required`
- `http_error`
- `empty_or_script_only`
- `public_content`
- `network_error`

Only `public_content` is stored, as a content-addressed blob with its SHA-256. Each attempt records:
- the URL and final URL, method, UTC time and HTTP status;
- the markers that fired and the challenge and login states;
- visibility (public / authenticated / not determined);
- capture completeness (complete HTML snapshot or none).

Cookies are never written: every browser context is fresh and discarded, and no storage state is saved.

## 4. What was deliberately not done

- CAPTCHA services, stealth plugins and fingerprint changes.
- Rotating proxies or IPs.
- Copying session tokens or cookies.
- Probing private or undocumented endpoints.
- Paywall or investor-area access.
- Retries after the block.

Search-engine snippets were not used as evidence.

## 5. Recommended route for future collection: user-assisted import

**Steps (English).**
1. In your own browser, open the campaign page. Logged out is preferred. If you must log in to see something, mark
   the row `captured_while_logged_in=yes`; it will be stored privately.
2. Save it with **File → Save Page As (HTML)** or **Print → Save as PDF**. Write down the dates shown on the page
   (for example "Update posted Oct 18").
3. Add one CSV row per file (see `templates/republic_manual_import/example_import.csv`):
   - `offering_id`, `file`, `url`, `source_type` (`campaign_page`, `founder_qa`, `company_update`, …);
   - `visibility`, `captured_while_logged_in`;
   - `claimed_publication_date` (the date shown on the page);
   - `captured_utc` (when you saved it);
   - `description`.
4. Run `python -m prospective import-evidence <csv>`.
   - Block, challenge, login and error pages are refused.
   - Cookie files, HAR files and anything with session tokens are refused.
   - The import time becomes the observation time, so the material can enter only a **new** evidence pack.
5. Never import cookies, passwords, HAR files or investor-only messages as public evidence. Investor notices go in
   as `investor_notice` and are stored privately, outside git.

**절차 (한국어).**
1. 본인 브라우저로 캠페인 페이지를 엽니다. 로그아웃 상태를 권장합니다. 로그인해야만 보이는 내용이면
   `captured_while_logged_in=yes`로 표시하세요. 이 경우 비공개로 저장됩니다.
2. "다른 이름으로 저장(HTML)" 또는 "PDF로 인쇄"로 저장합니다. 페이지에 표시된 날짜도 메모하세요.
3. 파일마다 CSV 한 줄을 작성합니다. 예시: `templates/republic_manual_import/example_import.csv`
4. `python -m prospective import-evidence <csv>`를 실행합니다.
   - 차단·챌린지·로그인·오류 페이지와 쿠키·토큰 파일은 자동으로 거부됩니다.
   - 가져온 자료의 관측 시각은 가져온 시각입니다. 따라서 기존 분석에는 들어가지 않고 **새 증거팩**에만 들어갑니다.
5. 쿠키, 비밀번호, HAR 파일, 투자자 전용 메시지는 공개 증거로 가져오지 마세요.

**Cadence.** Import at most a few pages, only for offerings in the weekly review queue. Do it when a decision is
pending, not on a schedule. SEC follow-up stays automated.

## 6. What remains unknown

- Whether Republic pages are publicly viewable from an ordinary residential browser. This is likely, but not
  verified here.
- Whether any campaign is still accepting investments today. The issuer websites claim so, but that is unverified.
  The briefs therefore show availability as `availability_unknown`, not as available.
