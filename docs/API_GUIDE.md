# Paperplane PDF Developer REST API (v1) Guide
**Target Release: October 31, 2026**
**API Version: 2.0.0 (REST API v1)**
**Base URL:** `http://127.0.0.1:8501/api/v1` (Local) / `https://api.paperplanepdf.com/api/v1` (Production)

---

## 1. Overview & Architecture

Paperplane PDF exposes a high-performance, asynchronous REST API enabling developers to integrate all 37 enterprise-grade PDF processing, conversion, security, and AI intelligence capabilities into external applications, microservices, backend services, and automated CI/CD pipelines.

### Why Use the Paperplane PDF Developer API?
- **Headless Document Pipelines:** Convert Office documents, web pages, and image collections to PDF programmatically without human intervention.
- **Enterprise Security & Signing:** Encrypt PDFs with AES-256, sanitize document metadata, apply cryptographic digital signatures, and execute certified redaction in automated workflows.
- **AI Document Intelligence:** Extract structured JSON from invoices and resumes, generate executive summaries, and query complex contracts with verified page citations via `deepseek-v4-flash`.
- **Deterministic Ephemeral Storage:** Uploaded and processed documents are automatically isolated per tenant and permanently purged within 24 hours.

---

## 2. Authentication & Security

All protected endpoints require an authenticated Paperplane API key issued to your account.

### Header Specification
```http
Authorization: Bearer YOUR_PAPERPLANE_API_KEY
```
*(Legacy `X-API-Key: YOUR_PAPERPLANE_API_KEY` header is also supported for backward compatibility).*

> [!CAUTION]
> **Query Parameter Keys Strictly Prohibited:**
> API credentials must **never** be passed via URL query parameters (e.g. `?api_key=...`). The server strictly rejects query parameter API keys with `HTTP 400 Bad Request` to prevent credentials from leaking into proxy logs, browser histories, and referrer headers.

### API Key Management
Generate and revoke keys through the web dashboard (Settings → API Keys) or programmatically via:
- `GET /api/v1/keys`: List active keys and masked prefixes (`sk_live_...`).
- `POST /api/v1/keys`: Generate a cryptographically random 256-bit API key. Full secret is displayed **exactly once**.
- `DELETE /api/v1/keys/{key_id}`: Immediately revoke a key.

---

## 3. Free Daily Testing Sandbox & Quotas

Paperplane provides a generous, automated daily testing sandbox for all verified developer accounts:

| Metric | Free Sandbox Tier | Notes |
| :--- | :--- | :--- |
| **Daily Operations Allowance** | **10 calls / day** | Resets daily at 00:00 UTC |
| **Daily AI-Assisted Operations** | **3 calls / day** | Included within the 10 total daily operations |
| **Max File Upload Size** | **10 MB / request** | Sufficient for developer testing & verification |
| **Max Concurrency** | **2 active jobs** | Prevents resource exhaustion on shared sandboxes |
| **Rate Limit** | **120 requests / min** | Protects polling & status inspection endpoints |

### Quota Status Headers
Every developer API response includes real-time quota tracking headers:
```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 9
X-RateLimit-Reset: 1792195200
X-RateLimit-AI-Limit: 3
X-RateLimit-AI-Remaining: 2
```

When quota is exhausted, the API returns:
```json
HTTP/1.1 429 Too Many Requests
{
  "code": "QUOTA_EXHAUSTED",
  "message": "Daily API allowance (10 calls/day) exceeded. Limit resets at 2026-10-15T00:00:00+00:00.",
  "usage": {
    "calls_used": 10,
    "calls_remaining": 0,
    "reset_time_utc": "2026-10-15T00:00:00+00:00"
  }
}
```

---

## 4. Asynchronous Job Lifecycle & Idempotency

All heavy PDF transformations run asynchronously on the server worker pool.

### Job Status Transitions
```
queued ───> processing ───> completed
                       └───> failed
                       └───> cancelled
```

### Idempotency
To prevent duplicate processing and redundant quota deduction on network retries, submit a unique `Idempotency-Key` header with your `POST /api/v1/jobs` requests:
```http
Idempotency-Key: invoice_batch_98124_retry1
```
If a request with the same idempotency key is received within 24 hours, the server returns the existing job status (`HTTP 200 OK`) and does not re-charge your quota.

---

## 5. Endpoints Reference

### 5.1 Discovery & Account
- `GET /api/v1/operations`: Returns catalog of all 37 supported operations.
- `GET /api/v1/account/usage`: Returns current daily usage, remaining calls, active concurrency, and UTC reset timestamp.

### 5.2 PDF Processing Jobs
- `POST /api/v1/jobs`: Create and queue an asynchronous processing job.
  - Multipart form fields:
    - `operation` (string, required): e.g. `compress`, `merge`, `word_to_pdf`, `pdf_to_word`, `protect`, `unlock`, `redact`.
    - `options` (JSON string, optional): Operation parameters (e.g. `{"preset": "balanced"}`).
    - `files` (file, required): One or more input documents.
- `GET /api/v1/jobs/{job_id}`: Poll job status, progress percentage, error message, and output name.
- `GET /api/v1/jobs/{job_id}/download`: Download verified binary output artifact once status is `completed`.
- `DELETE /api/v1/jobs/{job_id}`: Cancel a job and purge its disk directory immediately.

### 5.3 Direct AI Intelligence Endpoints
- `POST /api/v1/ai/summarize`: Upload a PDF to generate a document-grounded executive summary with key takeaways.
- `POST /api/v1/ai/extract`: Upload an invoice, resume, or form to extract structured JSON entities and contact details.
- `POST /api/v1/ai/chat`: Query a PDF via RAG with BM25 vector search and exact page citations (`[Page X]`).
- `GET /api/v1/ai/test-connection`: Diagnostic health check probing upstream `deepseek-v4-flash` via AgentRouter.

---

## 6. Tested Code Examples

### 6.1 cURL (CLI)

#### Compress a PDF
```bash
# 1. Submit compression job
curl -X POST "http://127.0.0.1:8501/api/v1/jobs" \
  -H "Authorization: Bearer YOUR_PAPERPLANE_API_KEY" \
  -H "Idempotency-Key: compress_job_001" \
  -F "operation=compress" \
  -F "options={\"preset\":\"balanced\"}" \
  -F "files=@annual_report.pdf"

# Response: HTTP 202 Accepted
# {"job_id":"a8f9c1e0...","operation":"compress","status":"queued","status_url":"/api/v1/jobs/a8f9c1e0...","download_url":"/api/v1/jobs/a8f9c1e0.../download"}

# 2. Check status
curl -X GET "http://127.0.0.1:8501/api/v1/jobs/a8f9c1e0..." \
  -H "Authorization: Bearer YOUR_PAPERPLANE_API_KEY"

# 3. Download verified result
curl -O -J "http://127.0.0.1:8501/api/v1/jobs/a8f9c1e0.../download" \
  -H "Authorization: Bearer YOUR_PAPERPLANE_API_KEY"
```

---

### 6.2 Python

```python
import time
import requests

API_BASE = "http://127.0.0.1:8501/api/v1"
HEADERS = {"Authorization": "Bearer YOUR_PAPERPLANE_API_KEY"}

# 1. Check account quota
usage = requests.get(f"{API_BASE}/account/usage", headers=HEADERS).json()
print(f"Remaining operations: {usage['calls_remaining']}/{usage['daily_limit']}")

# 2. Submit Word document to PDF conversion
with open("contract.docx", "rb") as f:
    resp = requests.post(
        f"{API_BASE}/jobs",
        headers={**HEADERS, "Idempotency-Key": "contract_conversion_v1"},
        data={"operation": "word_to_pdf"},
        files={"files": f}
    )
resp.raise_for_status()
job_id = resp.json()["job_id"]
print(f"Job queued: {job_id}")

# 3. Poll until completed
while True:
    status_resp = requests.get(f"{API_BASE}/jobs/{job_id}", headers=HEADERS).json()
    status = status_resp["status"]
    if status == "completed":
        print("Conversion complete!")
        break
    elif status == "failed":
        raise RuntimeError(f"Processing failed: {status_resp.get('error')}")
    time.sleep(0.5)

# 4. Download converted PDF
dl_resp = requests.get(f"{API_BASE}/jobs/{job_id}/download", headers=HEADERS)
dl_resp.raise_for_status()
with open("contract.pdf", "wb") as f:
    f.write(dl_resp.content)
print("Saved converted file to contract.pdf")
```

---

### 6.3 Node.js / TypeScript

```typescript
import fs from 'node:fs';
import { Blob } from 'node:buffer';

const API_BASE = 'http://127.0.0.1:8501/api/v1';
const API_KEY = process.env.PAPERPLANE_API_KEY || 'YOUR_PAPERPLANE_API_KEY';
const HEADERS = { Authorization: `Bearer ${API_KEY}` };

async function mergePdfDocuments(files: string[], outputFilename: string) {
  const form = new FormData();
  form.append('operation', 'merge');

  for (const filePath of files) {
    const bytes = fs.readFileSync(filePath);
    form.append('files', new Blob([bytes], { type: 'application/pdf' }), filePath);
  }

  // 1. Submit merge job
  const res = await fetch(`${API_BASE}/jobs`, {
    method: 'POST',
    headers: { ...HEADERS, 'Idempotency-Key': `merge_${Date.now()}` },
    body: form,
  });
  if (!res.ok) throw new Error(`API submission failed: ${res.statusText}`);
  const { job_id } = await res.json();
  console.log(`Job queued: ${job_id}`);

  // 2. Poll until completed
  while (true) {
    const poll = await fetch(`${API_BASE}/jobs/${job_id}`, { headers: HEADERS });
    const job = await poll.json();
    if (job.status === 'completed') break;
    if (job.status === 'failed') throw new Error(job.error);
    await new Promise(r => setTimeout(r, 500));
  }

  // 3. Download output
  const dl = await fetch(`${API_BASE}/jobs/${job_id}/download`, { headers: HEADERS });
  const buffer = Buffer.from(await dl.arrayBuffer());
  fs.writeFileSync(outputFilename, buffer);
  console.log(`Merged output saved to ${outputFilename}`);
}

mergePdfDocuments(['invoice_1.pdf', 'invoice_2.pdf'], 'combined_invoices.pdf');
```
