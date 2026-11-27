"""Record a read-only TLS/header and common-exposure check for the live site."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import ssl
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
HOST = "paperplane.qd.je"
BASE = f"https://{HOST}"
CHECKED_PATHS = [
    "/.env", "/.git/config", "/.git/HEAD", "/wp-config.php.bak",
    "/config.php~", "/.DS_Store", "/phpinfo.php", "/server-status", "/backup.zip",
]
CAPTURE_HEADERS = [
    "strict-transport-security", "content-security-policy", "x-content-type-options",
    "x-frame-options", "referrer-policy", "permissions-policy", "server",
]

with socket.create_connection((HOST, 443), timeout=12) as raw:
    with ssl.create_default_context().wrap_socket(raw, server_hostname=HOST) as tls:
        cert = tls.getpeercert()
        not_after = cert.get("notAfter", "")

request = urllib.request.Request(BASE + "/", method="GET", headers={"User-Agent": "Paperplane passive deployment audit"})
with urllib.request.urlopen(request, timeout=15) as response:
    status = response.status
    final_url = response.geturl()
    headers = {key.lower(): response.headers.get(key) for key in CAPTURE_HEADERS}

http_redirected = False
try:
    with urllib.request.urlopen(urllib.request.Request(f"http://{HOST}/", method="GET"), timeout=15) as response:
        http_redirected = response.geturl().startswith("https://")
except urllib.error.URLError as error:
    if getattr(error, "code", None) in (301, 302, 307, 308):
        http_redirected = str(getattr(error, "headers", {}).get("Location", "")).startswith("https://")

paths = []
for path in CHECKED_PATHS:
    req = urllib.request.Request(BASE + path, method="GET", headers={"User-Agent": "Paperplane passive exposure check"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            paths.append({"path": path, "status": response.status,
                          "content_type": response.headers.get("Content-Type"),
                          "content_length": response.headers.get("Content-Length")})
    except urllib.error.HTTPError as error:
        paths.append({"path": path, "status": error.code,
                      "content_type": error.headers.get("Content-Type"),
                      "content_length": error.headers.get("Content-Length")})

payload = {
    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "read-only HTTPS/TLS headers and nine common file/path probes; no bodies retained",
    "host": HOST,
    "http_redirected_to_https": http_redirected,
    "https_status": status,
    "final_url": final_url,
    "certificate_not_after": not_after,
    "headers": headers,
    "exposure_paths": paths,
}
output = ROOT / "reports" / "launch-audit-v23" / "security-passive-live-check.json"
output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps(payload, indent=2))
