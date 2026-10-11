# User-provided evidence (optional)

Put files you captured yourself in `files/` (gitignored), add one row per item to
`import_register.csv` (public items only) or `private/import_register.csv` (investor-only items;
gitignored), then run `python -m personal_vc_research import --config config.yaml`.

Never include passwords, session cookies, account numbers, tax IDs or other private account data.
Crop or redact personal details from screenshots before saving.

Required columns: item_id, offering_id (from data/sample/frozen_sample.csv), url_or_document_identity,
file, capture_date_utc, displayed_publication_or_update_date, visibility (public | investor_only),
security_class (e.g. "Crowd SAFE Series 2020"), evidence_locator (page/section/screen region),
publication_timing_independently_verified (true/false), evidence_type, summary.

A page you capture today supports *later outcomes* only. It can serve as a historical (decision-date)
feature only if its original publication date is independently verified and on or before the decision date.

## Collection checklist (5 pilot offerings, ~30-45 minutes in your own logged-in Republic account)
For each of Hemster, Up Sonder, SkyHi, People First RH, Janover Ventures:
1. Campaign page "Updates" tab: save each update as PDF (print to PDF), noting its displayed date. (public)
2. Your Portfolio / investment detail page, if you ever invested: screenshot status, security type, amount
   and any conversion or "exited/written off" label. (investor_only; redact account numbers)
3. Any investor e-mail or document about conversion, share delivery, repurchase, cash-out or dissolution
   (e.g. Janover 2022 conversion notice, transfer-agent statement). (investor_only)
4. For Janover only: the 2022 notice describing whether your SAFE converted in October 2022 or at the IPO,
   the share count received per dollar, and how shares were delivered (transfer agent / broker).
