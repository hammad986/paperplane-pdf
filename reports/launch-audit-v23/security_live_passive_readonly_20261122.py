"""Single-request passive HTTPS, header, and common exposed-path checks."""
from __future__ import annotations

import json
from pathlib import Path
import requests

BASE = "https://paperplane.qd.je"
CHECK_HEADERS = (
    "content-security-policy", "strict-transport-security", "x-content-type-options",
    "x-frame-options", "referrer-policy", "permissions-policy", "server", "x-powered-by",
)
EXPOSED_PATHS = ("/.env", "/.git/config", "/.git/HEAD", "/server-status", "/phpinfo.php")


def inspect(url: str) -> dict:
    response = requests.get(url, timeout=12, allow_redirects=True, stream=True)
    try:
        headers = {key.lower(): value for key, value in response.headers.items()}
        body = response.raw.read(4096, decode_content=True)
        text = body.decode("utf-8", errors="ignore").lower()
        return {
            "status": response.status_code,
            "final_scheme": response.url.split(":", 1)[0],
            "redirects": [{"status": item.status_code, "scheme": item.url.split(":", 1)[0]}
                          for item in response.history],
            "content_type": headers.get("content-type"),
            "sampled_bytes": len(body),
            "headers": {key: headers.get(key) for key in CHECK_HEADERS if key in headers},
            "sensitive_markers_in_sample": {
                "env_assignment": "paperplane_" in text or "secret_key=" in text,
                "git_config_section": "[core]" in text or "[remote \"" in text,
                "server_status_signature": "server uptime" in text or "server version" in text,
            },
        }
    finally:
        response.close()


results = {"http_root": inspect("http://paperplane.qd.je/"), "https_root": inspect(BASE + "/")}
results["exposed_paths"] = {path: inspect(BASE + path) for path in EXPOSED_PATHS}
report = {"site": BASE, "date": "2026-11-22", "read_only": True, "checks": results}
target = Path(__file__).with_name("security-live-passive-readonly-2026-11-22.json")
target.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
