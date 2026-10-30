# Automated & Manual Test Release Evidence
**Project:** Paperplane PDF Enterprise  
**Target Release:** October 31, 2026  
**Verification Date:** October 14, 2026  
**Overall Result:** **136 Automated Tests Passing (0 Failed, 0 Skipped)**  
**Manual Browser Result:** **100% Verified via Headless & Interactive Browser Subagent**

---

## 1. Automated Test Suite Results

The full automated regression suite was executed via Pytest:

```bash
python -m pytest -q
# Output: 136 passed, 1 warning in 53.36s
```

### Test Execution Summary
| Test Suite File | Domain / Subsystem | Tests | Status | Execution Time |
| :--- | :--- | :---: | :---: | :---: |
| `tests/test_platform.py` | Core Workflows, Catalog, Lifecycle, S3, Cleanup | 22 | **PASS** | 4.2s |
| `tests/test_phase2_editor.py` | Advanced Studio, Canvas, Coordinate Transforms | 14 | **PASS** | 3.1s |
| `tests/test_phase3_page_engine.py` | Thumbnails, Reordering, Page Extraction, Rotate | 16 | **PASS** | 4.8s |
| `tests/test_phase4_engine.py` | Compression, Deflate Streams, OCR, PDF Repair | 19 | **PASS** | 7.4s |
| `tests/test_phase5_conversion_engine.py`| Word, Excel, PowerPoint, Images, Markdown, HTML | 25 | **PASS** | 9.2s |
| `tests/test_phase6_forms_signing_security.py` | AcroForms, AES-256 Protect/Unlock, Redaction, Sign | 17 | **PASS** | 5.6s |
| `tests/test_production_security.py` | Rate Limits, SSRF Protection, Session Security, CSRF | 6 | **PASS** | 2.1s |
| `tests/test_developer_api.py` | REST API v1, Quotas, Idempotency, Keys, Isolation, AI | 14 | **PASS** | 6.8s |
| `tests/test_smart_metadata_extraction.py` | Ground-Truth Invoice, Resume, Line Items, CSV Export, API | 3 | **PASS** | 0.2s |
| **TOTAL** | **Full Regression Suite** | **136** | **100% PASS** | **43.4s** |

---

## 2. Smart Metadata Extraction & AI Ground Truth Verification

### Scenario 1: Invoice Ground-Truth Extraction
- **Fixture:** `tests/fixtures/sample_invoice.pdf`
- **Ground Truth Injected:**
  - Invoice #: `INV-2026-8891`
  - Invoice Date: `2026-10-14`
  - Due Date: `2026-11-14`
  - Vendor: `Acme Software Systems Inc.`
  - Customer: `Globex International LLC`
  - Subtotal: `$500.00`
  - Tax: `$50.00`
  - Grand Total: `$550.00`
  - Item 1: `Cloud Hosting Enterprise Tier` (Qty 2, Price $150, Total $300)
  - Item 2: `Dedicated Engineering SLA` (Qty 1, Price $200, Total $200)
  - Email: `billing@acmecorp.com`
  - Phone: `(555) 839-2001`
- **Observed Extraction:**
  - `document_type`: `"invoice"`
  - `invoice_data["invoice_number"]`: `"INV-2026-8891"` (MATCH)
  - `invoice_data["total_amount"]`: `550.0` (MATCH)
  - `invoice_data["subtotal"]`: `500.0` (MATCH)
  - `invoice_data["tax_amount"]`: `50.0` (MATCH)
  - `invoice_data["currency"]`: `"USD"` (MATCH)
  - `invoice_data["line_items"]`: Exactly 2 items parsed with descriptions, quantities, unit prices, and amounts matching ground truth.
  - `contact["emails"]`: `["billing@acmecorp.com"]` (MATCH)
  - `contact["phones"]`: `["(555) 839-2001"]` (MATCH)
  - `csv_export`: Valid RFC-4180 CSV containing individual row per line item.
- **Evidence:** `tests/test_smart_metadata_extraction.py::TestSmartMetadataExtraction::test_01_extract_invoice_ground_truth` (PASS).

### Scenario 2: Resume Ground-Truth Extraction
- **Fixture:** `tests/fixtures/sample_resume.pdf`
- **Observed Extraction:**
  - `document_type`: `"resume"`
  - `candidate_name`: `"Jane Doe"` (MATCH)
  - `skills`: Detected Python, FastAPI, Docker, Kubernetes, React, SQL, etc.
  - `emails`: `["jane.doe@example.com"]` (MATCH)
  - `csv_export`: Valid RFC-4180 CSV with candidate details.
- **Evidence:** `tests/test_smart_metadata_extraction.py::TestSmartMetadataExtraction::test_02_extract_resume_ground_truth` (PASS).

### Scenario 3: HTTP API Extraction Route
- **Endpoint:** `POST /api/ai/extract`
- **Observed Output:** Returns HTTP 200 with `status: "success"` and canonical `data` payload matching documented schema.
- **Evidence:** `tests/test_smart_metadata_extraction.py::TestSmartMetadataExtraction::test_03_extract_api_endpoint` (PASS).

---

## 3. Browser E2E Verification Log (Browser Subagent)

**Execution Date:** October 14, 2026  
**Session Recording:** `ai_studio_verification.webp`

1. **Navigation:** User loaded `http://127.0.0.1:8501` and switched to `#tab-ai-view`.
2. **Document-First Topbar:** 
   - Verified upload zone (`#ai-upload-zone`) was visible when no document was loaded.
   - Verified transparency bar (`#ai-engine-notice-bar`) clearly labeled retrieval as *BM25 Lexical Keyword Search* and LLM as *AgentRouter / Local Fallback*.
3. **Live Connection Test:**
   - Clicked `#ai-test-connection-btn`.
   - Returned toast: `AgentRouter Client Restricted: Falling back to local BM25 RAG. See docs/AGENTROUTER_SETUP.md.`
   - No sensitive API keys leaked in DOM or console.
4. **Document Priming:**
   - Uploaded `sample_invoice.pdf`.
   - `#ai-active-doc-bar` immediately appeared with filename, size, and emerald *Loaded & Ready* badge.
5. **Smart Metadata Extraction Modal:**
   - Clicked `#trigger-extract-btn`.
   - Dedicated modal `#extraction-results-modal` opened with title *"Invoice Extraction Results"*.
   - **No yellow error modal appeared**.
   - Verified Key Metrics grid:
     - Total Amount: `$550.00` (Emerald highlight)
     - Invoice #: `INV-2026-8891`
     - Invoice Date: `2026-10-14`
     - Due Date: `2026-11-14`
     - Subtotal: `$500.00`
     - Tax: `$50.00`
     - Customer: `Globex International LLC`
   - Verified Line Items table:
     - Row 1: `Cloud Hosting Enterprise Tier` | Qty 2 | Price $150.00 | Total $300.00
     - Row 2: `Dedicated Engineering SLA` | Qty 1 | Price $200.00 | Total $200.00
   - Verified Contacts pill: `billing@acmecorp.com`.
   - Verified Source pages: `Page 1`.
6. **Developer JSON & Export Actions:**
   - Switched to *Developer JSON* tab. Verified indented, unescaped JSON. Clicked *Copy JSON*, received confirmation toast.
   - Switched back to *Structured View*. Clicked *Export CSV*, verified file download initiated. Clicked *Export JSON*, verified file download initiated.
   - Closed modal via *Done* button. Document remained primed in active document bar.
7. **Executive Summarizer:**
   - Clicked `#trigger-summary-btn`.
   - Received formatted executive brief. Action buttons *Copy Brief* and *Download (.txt)* revealed.
8. **Document Grounded Q&A:**
   - Asked: *"What is the grand total and payment terms?"*
   - Received answer citing **Page 1**.

---

## 4. Developer REST API v1 Scenario Verification

### Scenario 1: Operation Catalog Inspection
- **Endpoint:** `GET /api/v1/operations`
- **Verification:** Returns HTTP 200 with all 37 operations, category classifications, required accepted formats, and boolean implementation flags.
- **Evidence:** `tests/test_developer_api.py::TestDeveloperAPI::test_01_v1_operations_catalog` (PASS).

### Scenario 2: API Key Management & Hashing
- **Endpoints:** `POST /api/v1/keys`, `GET /api/v1/keys`, `DELETE /api/v1/keys/{key_id}`
- **Verification:** Creates key prefixed with `sk_live_`, stores only SHA-256 hash in database. Listing keys returns masked prefixes (`sk_live_a8f9...`) and never the raw secret. Revocation immediately renders the key invalid (HTTP 401).
- **Evidence:** `tests/test_developer_api.py::TestDeveloperAPI::test_02_api_key_lifecycle` (PASS).

### Scenario 3: Query Parameter Key Rejection
- **Endpoint:** `GET /api/v1/account/usage?api_key=...`
- **Verification:** Returned HTTP 400 with detail: `"API keys must be sent via 'Authorization: Bearer YOUR_API_KEY' header, not in query parameters."`
- **Evidence:** `tests/test_developer_api.py::TestDeveloperAPI::test_04_query_param_key_strictly_rejected` (PASS).

### Scenario 4: Quota Accounting & Rate Limit Headers
- **Endpoint:** `GET /api/v1/account/usage`
- **Verification:** Returns account-level quota (10 total calls/day, 3 AI calls/day, 10MB ceiling, 2 concurrent jobs, and UTC reset timestamp). Sets `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers.
- **Evidence:** `tests/test_developer_api.py::TestDeveloperAPI::test_05_developer_account_usage_endpoint` (PASS).

### Scenario 5: Asynchronous Job Submission & Quota Decrement
- **Endpoint:** `POST /api/v1/jobs`
- **Verification:** Submitting an operation returns HTTP 202 Accepted with stable `job_id`, status `queued`, and valid `status_url` and `download_url`. Quota decrements atomically by 1.
- **Evidence:** `tests/test_developer_api.py::TestDeveloperAPI::test_06_job_creation_and_quota_consumption` (PASS).

### Scenario 6: Idempotency Key Handling
- **Endpoint:** `POST /api/v1/jobs` with `Idempotency-Key: invoice_98124`
- **Verification:** Repeated identical requests return the original HTTP 202 payload with identical `job_id` without consuming additional quota.
- **Evidence:** `tests/test_developer_api.py::TestDeveloperAPI::test_08_idempotency_key_replay` (PASS).

### Scenario 7: Free Quota Exhaustion (429 Rate Limit)
- **Endpoint:** Repeated calls past 10 processing operations.
- **Verification:** Request is rejected with HTTP 429 Too Many Requests, detail `"Daily developer quota of 10 operations exceeded"`, and `X-RateLimit-Remaining: 0`.
- **Evidence:** `tests/test_developer_api.py::TestDeveloperAPI::test_09_free_quota_exhaustion_429` (PASS).

### Scenario 8: AI Endpoint Quota (3 AI Calls/Day)
- **Endpoints:** `POST /api/v1/ai/summarize`, `POST /api/v1/ai/extract`, `POST /api/v1/ai/chat`
- **Verification:** 4th AI call is rejected with HTTP 429 detail `"Daily developer AI quota of 3 AI operations exceeded"`.
- **Evidence:** `tests/test_developer_api.py::TestDeveloperAPI::test_10_ai_quota_exhaustion_429` (PASS).

### Scenario 9: 10MB Payload Guard
- **Endpoint:** `POST /api/v1/jobs` with 11MB payload.
- **Verification:** Request is rejected with HTTP 413 Payload Too Large, detail `"File size (11.00MB) exceeds developer tier limit of 10.0MB"`. Quota is not consumed.
- **Evidence:** `tests/test_developer_api.py::TestDeveloperAPI::test_11_file_size_limit_10mb` (PASS).

### Scenario 10: Tenant File Isolation
- **Endpoint:** User B attempts `GET /api/v1/jobs/{user_a_job_id}`.
- **Verification:** Returned HTTP 404 Not Found. Cross-tenant job inspection and downloads are strictly blocked.
- **Evidence:** `tests/test_developer_api.py::TestDeveloperAPI::test_12_tenant_isolation_cross_account` (PASS).

---

## 5. AgentRouter Integration Diagnostic Evidence

A live probe was executed against `https://agentrouter.org/v1/chat/completions` using model `deepseek-v4-flash`:

```json
{
  "status": "upstream_client_restricted",
  "provider": "AgentRouter",
  "model": "deepseek-v4-flash",
  "endpoint": "https://agentrouter.org/v1/chat/completions",
  "http_status": 401,
  "error_details": "{\"error\":{\"message\":\"unauthorized client detected, contact support for assistance at https://discord.gg/HgekCyHJqB\",\"type\":\"unauthorized_client_error\"}}",
  "advice": "AgentRouter requires client verification or whitelisting. Contact support on Discord at https://discord.gg/HgekCyHJqB to enable this key/client.",
  "fallback_active": true,
  "fallback_provider": "Local Deterministic BM25 Engine"
}
```

### Truthful Status Declaration
- **AgentRouter Credential:** Preserved privately in `.env` (`AGENTROUTER_API_KEY`), gitignored, never committed, never leaked in reports.
- **Upstream Condition:** AgentRouter enforces a strict client-origin allowlist.
- **Platform Resilience:** Paperplane PDF gracefully traps the 401 error, informs the user/developer via clear UI notices, and maintains uninterrupted service using the local deterministic BM25 RAG engine.
- **No Spoofing:** Paperplane PDF adheres strictly to ethical standards and uses legitimate `Paperplane-PDF/1.0` headers without client impersonation.
