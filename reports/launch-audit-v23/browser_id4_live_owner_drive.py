"""Check the exact user-provided v23 Drive PDF through the deployed Cloud Import UI.

The source URL and imported filename are intentionally not written to evidence.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import urllib.parse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://paperplane.qd.je"
SOURCE = ROOT / "reports" / "launch-audit-v23" / "browser_p0.py"
OUT = ROOT / "reports" / "launch-audit-v23" / "browser-id4-live-owner-drive-2026-11-19.json"

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
    raise RuntimeError("The user-provided owner Drive test URL was not found in the v23 audit source.")
parts = urllib.parse.urlsplit(owner_url)
if parts.scheme != "https" or parts.hostname != "drive.google.com" or parts.username or parts.password:
    raise RuntimeError("The supplied owner Drive test URL did not match the expected public HTTPS Drive host.")

api_responses: list[dict] = []
page_errors: list[str] = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1366, "height": 900})
    page = context.new_page()
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    def record_sync(response):
        if "/api/cloud/sync" not in response.url:
            return
        item = {"http_status": response.status}
        try:
            payload = response.json()
            item.update({
                "provider": payload.get("provider"),
                "filename_present": bool(payload.get("filename")),
                "content_type": payload.get("content_type"),
                "size_bytes": payload.get("size"),
                "page_count": payload.get("page_count"),
                "data_url_present": bool(payload.get("data_url")),
                "error": payload.get("detail") if response.status >= 400 else None,
            })
        except Exception:
            item["response_json_readable"] = False
        api_responses.append(item)

    page.on("response", record_sync)
    home = page.goto(BASE + "/merge-pdf", wait_until="domcontentloaded", timeout=45000)
    page.locator("#topbar-cloud-btn").click(timeout=15000)
    page.locator("#cloud-url").fill(owner_url)
    page.locator("#cloud-submit-btn").click()
    page.wait_for_function("""() => {
      const modal=document.querySelector('#cloud-modal');
      const error=document.querySelector('#cloud-error');
      return (modal && modal.hidden) || (error && !error.hidden);
    }""", timeout=90000)
    outcome = page.evaluate(r"""() => {
      const error=document.querySelector('#cloud-error');
      const modal=document.querySelector('#cloud-modal');
      const toast=document.querySelector('.toast-notice');
      const toastText=toast?.innerText||'';
      const pageMatch=toastText.match(/·\s*([0-9]+)\s+pages?/i);
      return {
        modal_hidden:Boolean(modal?.hidden),
        error_visible:Boolean(error&&!error.hidden),
        error_text:error&&!error.hidden?error.innerText:null,
        imported_file_rows:document.querySelectorAll('#file-list .file-row-card').length,
        imported_size_labels:[...document.querySelectorAll('#file-list .file-row-size')].map(el=>el.innerText),
        toast_reports_import:/Imported\s/i.test(toastText),
        toast_page_count:pageMatch?Number(pageMatch[1]):null,
        toast_present:Boolean(toast)
      };
    }""")
    result = {
        "site": BASE,
        "source": "exact user-provided v23 owner Drive test link; value redacted",
        "route_http_status": home.status if home else None,
        "api_responses": api_responses,
        "ui": outcome,
        "page_errors": page_errors,
    }
    context.close()
    browser.close()

OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
