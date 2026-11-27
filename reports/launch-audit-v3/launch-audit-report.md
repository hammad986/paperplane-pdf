# Paperplane — Local Release Readiness Audit

**Tarikh:** 2026-11-06  
**Scope:** Sirf repository aur `http://127.0.0.1:8501`. Live website, account, billing, OTP, Google/Dropbox, ya AI provider ko contact nahi kiya.  
**Kul status:** **PARTIAL — ise production deployment sign-off na samjhein.** Local app aur tested user journeys behtar hue, par production TLS, container build, aur asli service credentials abhi verify hone baaki hain.

## Final verification

- Aakhri code/config edit ke baad full suite: `python -m pytest -q` — **250 passed, 1 warning, 93.28s**. Warning Starlette ka `TestClient` mein `httpx` use karne par deprecation notice hai.
- Responsive operation matrix: **41 tools × 9 viewport widths × 2 themes × 2 sidebar states = 1,476 cases**; 0 layout failures, 0 chhote touch-target cases, 0 browser errors.
- General page layout matrix: **252 cases**, 0 failures, 0 browser errors.
- Local route census: **41/41 tool routes** ne titled page diya; 7 redirects/disabled docs endpoints expected behavior se match hue.
- 390×844 phone profile par touch test: dono horizontal tool ribbons swipe se scroll hue; aakhri controls reachable aur 44px high the. Vertical swipe se canvas page 2 par gaya aur page indicator/thumbnail dono sync rahe.
- Static checks: `py_compile`, `bash -n scripts/provision_ssl.sh`, `docker compose config --quiet`, aur `git diff --check` pass hue.
- Python dependency audit: `python -m pip_audit -r requirements-dev.txt` ne **koi known vulnerability report nahi ki**.
- Deployment dry-run pass hua aur planned steps dikhaye. Isne containers build/start nahi kiye. `docker compose build paperplane` nahi chala kyunki Docker Engine available nahi tha.

## Maange gaye checklist ke statuses

| ID | Status | Saboot aur baaki kaam |
|---|---|---|
| A1 — galat premise aur prompt injection | **FIXED locally** | Galat geography/author/date/page-count daavon ko bina galat PDF citation ke sahi kiya. Prompt, identity, code likhne, aur credential maangne wale sawalon ko Paperplane scope mein rakha. |
| A2 — Executive Brief | **PARTIAL** | Local capability `ai_service_disabled` batati hai; asli provider wala brief test nahi hua. |
| A3 — summary citations | **PARTIAL** | Offline extractive overview ke citations aur visible citation chips 3-page aur 69-page PDFs par 3-3 runs mein match hue. Yeh deterministic extraction hai, verified model-generated summary nahi. |
| A4 — incremental AI response | **PARTIAL** | Desktop aur phone browser profiles par offline fallback text dheere-dheere aaya, stages complete hue aur citations match hue. AI provider key configured nahi tha, isliye upstream model streaming test nahi hui. |
| A5 — Studio page jump aur continuous scroll | **FIXED locally** | Page 1, page 35 thumbnail jump aur page 69 test hue; render ke dauran target page visible raha. Phone touch scroll par page aur active thumbnail sync rahe. |
| A6 — Advanced Studio navigation | **FIXED locally** | Home aur paanch tool routes se Advanced Studio tab ne Studio khola; dead Tool Desk tab nahi raha. |
| A7 — organizer delete/extract | **FIXED locally** | Ek page delete, batch delete, output page/content count, aur ek-page extraction locally verify hue. |
| A8 — reload behavior | **FIXED, chune hue ephemeral design ke mutabik** | PDF aur AI chat memory mein hi rehte hain. Reload se pehle warning, aur reload ke baad message user ko PDF dobara chunne/sawal dobara poochhne ko batata hai. Studio view available rehta hai. |
| A9 — developer documentation links | **FIXED locally** | `/docs` aur `/api-docs` `/developers` par redirect hote hain; `/redoc` aur `/openapi.json` jaan-boojhkar disabled hain. Public site check nahi hui. |
| A10 — PDF chooser | **PARTIAL** | Visible Windows file picker se local sample PDF load hua; Playwright desktop/phone profiles par upload se cited answer tak flow pass hua. Asli mobile OS file picker test nahi hui. |
| R1 — currency | **PARTIAL** | Local checks INR default aur USD checkout rejection confirm karte hain. Live Cashfree checkout/settlement nahi chalaya; local Cashfree environment TEST hai. |
| R2 — docs endpoints | **FIXED locally** | A9 wale local redirects/disabled endpoints verify hue. |
| R3 — provider/model identity leakage | **FIXED locally** | AI responses provider/model identity fields nahi bhejte; guarded prompts ne private credentials expose nahi kiye. Asli provider connection available nahi thi. |
| R4 — provider timeouts | **PARTIAL** | Code paths aur timeout caps dekhe; live provider latency/retry measure nahi hui. |
| R5 — bada merge | **FIXED, local stress run mein** | 69×2 pages aur 100×69 pages ke outputs readable rahe; 6,900-page output page/content checks pass kar gaya. |
| R6 — quotas aur fallback UI | **FIXED locally** | Auth delay mein “Checking usage” dikhta hai; auth failure aur no-JavaScript fallback 0/100 dikhate hain; free/paid file limits aur 100-file batch cap consistent hain. |
| R7 — upload validation aur limits | **PARTIAL** | Corrupt/header-only PDFs aur mislabeled files quota consume karne se pehle reject hue; over-limit upload 413 raha. Final code par exact 524,288,000-byte Pro streaming helper 8,000 × 64 KiB chunks mein pass hua aur final PDF validator valid PDF par pass hua. Pehle full 500 MiB multipart HTTP upload 202 tha, lekin final parser gate ke baad full multipart/background-job request dobara nahi chalayi. |

## Visual aur workflow coverage

Viewport widths 360, 375, 390, 414, 768, 1024, 1280, 1366, aur 1920 CSS pixels par light/dark mode aur sidebar open/closed ke saath test hui. Ismein phone, tablet, laptop, aur desktop widths Chromium emulation mein shamil hain. Yeh physical device, Safari/Firefox, ya browser zoom test ka badal nahi hai.

Extra local checks mein PDF choose → grounded chat answer, desktop/phone reload warning aur cleanup, cloud modal ke Escape/outside click/navigation behavior, translation unavailable message, CSP/PDF worker rendering, aur split, rotate, protect/unlock, compress, grayscale, form-fill, metadata, PDF-to-Markdown output content shamil the.

## Security aur deployment findings

| Severity | Finding | Abhi ki sthiti / agla kadam |
|---|---|---|
| High — deployment blocker | Local mounted certificate expired self-signed `localhost` certificate hai, production domain ka nahi. | Preflight ab expired, mismatched, galat domain, ya key mismatch certificate reject karta hai. Production host par valid DNS/ports ke saath `scripts/provision_ssl.sh` chalao, phir deployment preflight chalao. Asli ACME issuance nahi hui. |
| High — deployment verify nahi | Docker CLI/Compose config parse hota hai, par Docker Engine available nahi tha; production image build aur containers start nahi hue. | Launch se pehle working Docker Engine chala kar documented build aur smoke checks karo. |
| Medium — AI unavailable | `BLUESMINDS_API_KEY` set nahi hai aur local audit server par AI kill switch on tha. | Chat labeled deterministic local fallback use karta hai; Executive Brief aur AI Translate provider ke saath verify nahi hue. In features ko live AI kehne se pehle provider configure karo. |
| Medium — billing unavailable | Local Cashfree config TEST hai. | Payment activation verified nahi hai; production credentials ke saath authorized checkout verification chahiye. |
| Low/Medium — CSP hardening | Inline scripts block hain aur PDF worker bina CSP error render hua. Current inline styles ke liye `style-src 'unsafe-inline'` enabled hai. | Inline style paths badalne ke baad hi is rule ko tighten karo aur browser checks dobara chalao. |
| Scope limitation | Public-domain TLS/headers/exposed-file paths, live auth/OTP, cloud imports, real billing, aur external AI ko contact nahi kiya. | Yeh local-only audit tha; penetration test ya live-site release certification nahi. |

Secret-pattern scan ne tracked files mein test/password literals aur ek placeholder flag kiye; review mein un hits ya checked 18 commits/458 tracked paths mein known vendor-token format nahi mila. `.env` aur local certs ignored hain; `.dockerignore` unhe aur audit artifacts ko build context se hataata hai. Local `localhost` TLS keypair workspace mein maujood hai, par Git/Docker se ignored hai.

## Kiye gaye changes

- `ai_engine.py` mein offline AI scope/fact handling aur sampled-page summaries behtar kiye.
- `server.py` mein PDF upload validation harden ki: pehle 1 KiB mein header check hota hai aur parser se readable page bhi chahiye.
- `web/assets/editor.js` mein phone Pan-mode touch scrolling fix ki; `web/index.html` mein editor asset version bump hua.
- `web/assets/app.js`, `web/assets/styles.css`, aur `web/index.html` mein Studio/mobile layout, reload notice, aur quota messaging update hui.
- `scripts/deploy_production.py` mein production TLS certificate/domain/expiry/key-pair preflight add hua; `scripts/provision_ssl.sh` mein Certbot renewal-path selection fix hui.
- `tests/test_deploy_preflight.py` aur `tests/test_launch_audit_v3_hardening.py` mein regression coverage add hui; `tests/test_production_security.py` ka valid-PDF fixture theek hua.
- `.gitignore` aur `.dockerignore` audit/runtime generated data ko Git aur Docker context se bahar rakhte hain.

## Local artifact note

Generated synthetic test data `runtime_data_codex_audit/` mein abhi bhi hai. Filesystem policy ne ise delete karne se roka; Git aur Docker se ignore kar diya hai, isliye commit ya container build mein nahi jaayega. Zarurat na ho to user is exact local folder ko baad mein manually remove kar sakta hai.

`.git/index.lock` ek zero-byte stale file ke roop mein dikh raha hai; audit ke waqt koi Git process active nahi tha. Is environment ki filesystem policy ne ise remove karne se roka. `git status` aur `git diff --check` chal gaye, lekin Git index ko update karne wale agle operation se pehle is lock ko locally saaf karna pad sakta hai.
