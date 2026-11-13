from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import fitz
import httpx


BASE = os.getenv("PAPERPLANE_AUDIT_BASE", "http://127.0.0.1:8502")
public = os.getenv("V7_CLOUD_PUBLIC_SHARE", "")
restricted = os.getenv("V7_CLOUD_RESTRICTED_SHARE", "")
sources = [
    ("public_share_attempt_1", public),
    ("public_share_attempt_2", public),
    ("restricted_share", restricted),
    ("invalid_drive_id", "https://drive.google.com/file/d/V7_AUDIT_INVALID_FILE_ID_000000000000000000/view"),
]
parsed = urlparse(public)
file_id = ""
match = re.search(r"/file/d/([A-Za-z0-9_-]+)", parsed.path)
if match:
    file_id = match.group(1)
else:
    file_id = parse_qs(parsed.query).get("id", [""])[0]
if file_id:
    sources.insert(1, ("public_direct_download", f"https://drive.google.com/uc?export=download&id={file_id}"))

results = []
with httpx.Client(timeout=50.0) as client:
    for name, share_url in sources:
        if not share_url:
            results.append({"source": name, "skipped": "URL was not supplied"})
            continue
        started = time.monotonic()
        try:
            response = client.post(f"{BASE}/api/cloud/sync", data={"file_url": share_url, "provider": "Google Drive"})
            row = {"source": name, "status": response.status_code, "elapsed_seconds": round(time.monotonic() - started, 3)}
            payload = response.json()
            if response.is_success and payload.get("data_url", "").startswith("data:application/pdf;base64,"):
                pdf_bytes = base64.b64decode(payload["data_url"].split(",", 1)[1])
                imported = fitz.open(stream=pdf_bytes, filetype="pdf")
                row.update({
                    "filename": payload.get("filename"),
                    "reported_size_bytes": payload.get("size"),
                    "actual_size_bytes": len(pdf_bytes),
                    "page_count": imported.page_count,
                    "opens_as_pdf": imported.page_count > 0,
                    "content_type": payload.get("content_type"),
                })
                imported.close()
            else:
                detail = payload.get("detail", "")
                row["error"] = re.sub(r"https?://\S+", "[URL redacted]", str(detail))[:240]
            results.append(row)
        except Exception as exc:
            results.append({"source": name, "elapsed_seconds": round(time.monotonic() - started, 3), "error_type": type(exc).__name__})

print(json.dumps(results, ensure_ascii=False, indent=2))
(Path(__file__).resolve().parent / "cloud-import-final.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
)
