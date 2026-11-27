"""Read-only live asset/health fingerprint; sends no account or job requests."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://paperplane.qd.je"
headers = {"User-Agent": "Paperplane deployment audit/1.0"}

with urlopen(Request(BASE + "/", headers=headers), timeout=30) as response:
    html = response.read().decode("utf-8", "replace")
    page = {"http_status": response.status, "final_url": response.geturl(), "content_length": len(html)}
    page["assets"] = sorted(set(re.findall(
        r'(?:src|href)="([^"]*(?:app\.js|page_organizer\.js|styles\.css)\?v=\d+)"', html
    )))

try:
    with urlopen(Request(BASE + "/api/health", headers=headers), timeout=15) as response:
        health = {"http_status": response.status, "body": json.loads(response.read())}
except Exception as error:
    health = {"error": type(error).__name__}

result = {"site": BASE, "read_only": True, "page": page, "health": health,
          "candidate_assets_present": all(value in page["assets"] for value in (
              "/assets/app.js?v=137", "/assets/page_organizer.js?v=19", "/assets/styles.css?v=61"))}
out = ROOT / "reports" / "launch-audit-v23" / "browser-live-assets-readonly-v137-2026-11-20.json"
out.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
