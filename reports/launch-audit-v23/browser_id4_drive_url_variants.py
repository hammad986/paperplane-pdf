"""Check standard Google Drive download URL forms without persisting the ID."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import converters

SOURCE = ROOT / "reports" / "launch-audit-v23" / "browser_p0.py"
OUT = ROOT / "reports" / "launch-audit-v23" / "browser-id4-drive-url-variants-2026-11-19.json"

tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
owner_url = None
for node in ast.walk(tree):
    if not isinstance(node, ast.Dict):
        continue
    for key, value in zip(node.keys, node.values):
        if isinstance(key, ast.Constant) and key.value == "owner_drive_view" and isinstance(value, ast.Constant):
            owner_url = value.value
            break
    if owner_url:
        break
if not owner_url:
    raise RuntimeError("Owner test URL missing from the v23 source")
parsed = urllib.parse.urlsplit(owner_url)
path_match = re.fullmatch(r"/file/d/([A-Za-z0-9_-]+)/?(?:view|preview|edit)?/?", parsed.path)
if parsed.scheme != "https" or parsed.hostname != "drive.google.com" or not path_match:
    raise RuntimeError("Owner test URL is not the expected public Drive /file/d/.../view form")
file_id = path_match.group(1)
variants = {
    "drive_uc_export": "https://drive.google.com/uc?" + urllib.parse.urlencode({"export": "download", "id": file_id}),
    "drive_uc_export_confirm": "https://drive.google.com/uc?" + urllib.parse.urlencode({"export": "download", "id": file_id, "confirm": "t"}),
    "drive_uc_id_export": "https://drive.google.com/uc?" + urllib.parse.urlencode({"id": file_id, "export": "download"}),
    "drive_usercontent_without_confirm": "https://drive.usercontent.google.com/download?" + urllib.parse.urlencode({"export": "download", "id": file_id}),
    "drive_usercontent_confirm": "https://drive.usercontent.google.com/download?" + urllib.parse.urlencode({"export": "download", "id": file_id, "confirm": "t"}),
}
results = []
for label, candidate in variants.items():
    metadata: dict[str, str] = {}
    try:
        content, media_type = converters.safe_fetch_url(
            candidate, max_size=2_000_000, timeout=20, response_metadata=metadata
        )
        final = urllib.parse.urlsplit(metadata.get("final_url", ""))
        results.append({
            "variant": label,
            "mime_type": media_type,
            "byte_count": len(content),
            "pdf_signature": content.startswith(b"%PDF-"),
            "png_signature": content.startswith(b"\x89PNG\r\n\x1a\n"),
            "final_host": final.hostname,
            "final_path": final.path,
            "content_disposition_present": bool(metadata.get("content_disposition")),
        })
    except Exception as error:
        results.append({"variant": label, "error_type": type(error).__name__, "error": str(error)[:160]})

payload = {
    "source": "exact user-provided v23 Drive test URL; value and file ID redacted",
    "url_variants_tested": len(results),
    "results": results,
}
OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps(payload, indent=2))
