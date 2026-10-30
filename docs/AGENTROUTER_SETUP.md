# AgentRouter AI Provider Integration & Verification Report
**Project:** Paperplane PDF Platform
**Target Release:** October 31, 2026
**Provider:** AgentRouter (`https://agentrouter.org`)
**Configured Model:** `deepseek-v4-flash`

---

## 1. Executive Summary & Configuration

Paperplane PDF integrates AgentRouter as its primary external LLM provider to power document intelligence features (Executive Summarization, Smart Metadata Extraction, and Document Question Answering).

### Environment Configuration (`.env`)
The server environment has been configured with the verified provider parameters:

```env
# AgentRouter AI Provider Configuration
AGENTROUTER_API_KEY=sk-opqF...[REDACTED_FOR_SECURITY]
AGENTROUTER_BASE_URL=https://agentrouter.org
AGENTROUTER_MODEL=deepseek-v4-flash
AGENTROUTER_TIMEOUT_SECONDS=45
AGENTROUTER_MAX_RETRIES=2
AGENTROUTER_MAX_OUTPUT_TOKENS=4096

# Public Developer REST API Quotas (Free Tier Defaults)
PAPERPLANE_FREE_API_CALLS_PER_DAY=10
PAPERPLANE_FREE_AI_CALLS_PER_DAY=3
PAPERPLANE_FREE_MAX_FILE_SIZE_MB=10
PAPERPLANE_FREE_CONCURRENT_JOBS=2
```

> [!IMPORTANT]
> **Strict Credential Isolation:**
> `AGENTROUTER_API_KEY` is a private, server-side credential stored strictly in `.env` (gitignored). It is never returned in API responses, never exposed in `/openapi.json` or Swagger UI, never logged, and never shared with client-side JavaScript. Customer-facing Paperplane API keys (`sk_live_...`) are completely isolated from this provider key.

---

## 2. API Contract & Live Verification Findings

### Protocol & Endpoint Verification
AgentRouter operates an OpenAI-compatible gateway. While the candidate base URL was provided as `https://agentrouter.org`, the OpenAI-compatible chat completions specification requires the `/v1` path:
- **Verified Protocol:** OpenAI-compatible Chat Completions
- **Verified Endpoint:** `https://agentrouter.org/v1/chat/completions`
- **Request Method:** `POST`
- **Payload Schema:**
  ```json
  {
    "model": "deepseek-v4-flash",
    "messages": [
      {"role": "system", "content": "..."},
      {"role": "user", "content": "..."}
    ],
    "temperature": 0.2,
    "max_tokens": 4096
  }
  ```

### Live Test Diagnostic Probe
During end-to-end connectivity verification with the provided testing key (`sk-opqFzZdg...`), the live gateway returned:

```json
HTTP/1.1 401 Unauthorized
{
  "error": {
    "message": "unauthorized client detected, contact support for assistance at https://discord.gg/HgekCyHJqB"
  },
  "message": "UNAUTHENTICATED",
  "success": false,
  "type": "unauthorized_client_error"
}
```

### Root Cause Analysis
1. **WAF & Client Allowlist:** AgentRouter routes requests through an anti-scraping reverse proxy (utilizing Alibaba Cloud `acw_tc` cookies and strict user-agent / client-fingerprint filtering).
2. **Key / Client Whitelisting:** Programmatic HTTP clients are blocked by policy until the client ID or API key is specifically authorized by the AgentRouter team via their Discord support server.
3. **No Impersonation Policy:** In compliance with security engineering standards, Paperplane PDF sends legitimate, authentic application headers (`User-Agent: Paperplane-PDF/1.0`) and does not attempt client impersonation or access-control evasion.

### Actionable Resolution
To enable live external inference with this key:
1. Join the official AgentRouter Discord server at: **https://discord.gg/HgekCyHJqB**
2. Submit your testing key prefix (`sk-opqF...`) to support and request client authorization for the `Paperplane-PDF/1.0` application client.
3. Test connectivity at any time via Paperplane's diagnostic endpoint:
   ```bash
   curl -X GET "http://127.0.0.1:8501/api/v1/ai/test-connection" \
     -H "Authorization: Bearer YOUR_PAPERPLANE_API_KEY"
   ```

---

## 3. Resilience, Fallback & Security Controls

To ensure that external network failures or provider outages **never** break deterministic PDF operations:

### Multi-Tier Fallback Architecture
1. **Tier 1 (Primary):** AgentRouter (`deepseek-v4-flash`).
2. **Tier 2 (Secondary):** Google Gemini (`gemini-1.5-flash`) if `GEMINI_API_KEY` is configured.
3. **Tier 3 (Local Offline RAG):** Pure Python BM25 vector retrieval engine that indexes PDF page text chunks locally and extracts exact supporting passages with verified page citations.
4. **Deterministic PDF Operations Untouched:** All 37 standard transformations (Merge, Compress, Split, Convert, Protect, Sign, Redact, OCR) execute locally using PyMuPDF and pypdf without making external network calls.

### AI Kill Switch
Setting `PAPERPLANE_AI_KILL_SWITCH=true` in `.env` immediately halts all outbound AI HTTP calls, ensuring compliance during maintenance windows or network isolation testing.

### Bounded Text Extraction & Data Privacy
- **No Raw File Transmission:** The application extracts text locally using PyMuPDF and sends only relevant text chunks (bounded to 8,000 characters). Complete binary PDF files, account credentials, and passwords are never transmitted to external AI providers.
- **Privacy Disclosure:** The Privacy Policy clearly informs users that AI-assisted features transmit extracted text to external inference providers.
