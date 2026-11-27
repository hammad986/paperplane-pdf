"""Verify the result action resets the current tool for a genuinely new file."""
from __future__ import annotations

import base64
import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id158-process-another-file.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id158-") as temp_name:
        temp = Path(temp_name)
        first = temp / "id158-first.pdf"
        second = temp / "id158-second.pdf"
        for target, text in ((first, "ID158 first result"), (second, "ID158 second input")):
            with fitz.open() as document:
                document.new_page().insert_text((72, 100), text)
                document.save(target)
        app, base, _identities = helper.start_server(temp / "data")
        evidence = {"page_errors": [], "console_errors": []}
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local Paperplane server exited before startup")
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.set_default_timeout(20000)
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: evidence["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                response = page.goto(base + "/rotate-pdf", wait_until="domcontentloaded")
                source_b64 = base64.b64encode(first.read_bytes()).decode("ascii")
                page.evaluate("""b64 => {
                  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                  const blob = new Blob([bytes], {type: 'application/pdf'});
                  window.showDownloadResult({output_name: 'id158-result.pdf', output_size: blob.size, page_count: 1}, URL.createObjectURL(blob), {blob});
                }""", source_b64)
                page.locator("#result:not([hidden])").wait_for()
                result_url = page.url
                page.locator("#result-restart-btn").click()
                page.wait_for_function("document.querySelector('#result')?.hidden && state.files.length === 0")
                evidence["after_reset"] = page.evaluate("""() => ({
                  url: location.pathname,
                  result_hidden: document.querySelector('#result').hidden,
                  upload_visible: !!document.querySelector('#dropzone') && getComputedStyle(document.querySelector('#dropzone')).display !== 'none',
                  file_count: state.files.length,
                  selected_file_name: document.querySelector('#file-input').files[0]?.name || null,
                  restart_label: document.querySelector('#result-restart-btn span')?.textContent.trim(),
                  run_disabled: document.querySelector('#run-button')?.disabled
                })""")
                page.locator("#file-input").set_input_files(str(second))
                page.wait_for_function("state.files.length === 1")
                evidence["next_file"] = page.evaluate("""() => ({
                  result_hidden: document.querySelector('#result').hidden,
                  file_count: state.files.length,
                  file_name: state.files[0]?.name,
                  run_enabled: document.querySelector('#run-button')?.disabled === false,
                  path_unchanged: location.pathname === '/rotate-pdf'
                })""")
                evidence["same_tool_route_after_action"] = result_url.endswith("/rotate-pdf")
                page.goto(base + "/compress-pdf", wait_until="domcontentloaded")
                page.evaluate("""b64 => {
                  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                  const blob = new Blob([bytes], {type: 'application/pdf'});
                  window.showDownloadResult({output_name: 'id158-compress-result.pdf', output_size: blob.size, page_count: 1}, URL.createObjectURL(blob), {blob});
                }""", source_b64)
                page.locator("#result:not([hidden])").wait_for()
                page.locator("#result-restart-btn").click()
                page.wait_for_function("document.querySelector('#result')?.hidden && state.files.length === 0")
                page.locator("#file-input").set_input_files(str(second))
                page.wait_for_function("state.files.length === 1")
                evidence["other_tool"] = page.evaluate("""() => ({
                  path: location.pathname,
                  result_hidden: document.querySelector('#result').hidden,
                  file_count: state.files.length,
                  file_name: state.files[0]?.name,
                  run_enabled: document.querySelector('#run-button')?.disabled === false
                })""")
                browser.close()
            evidence["http_status"] = response.status if response else None
        finally:
            app.terminate()
            app.wait(timeout=5)
        evidence["overall"] = "passed" if (
            evidence.get("http_status") == 200
            and evidence.get("same_tool_route_after_action") is True
            and evidence.get("after_reset", {}).get("result_hidden") is True
            and evidence.get("after_reset", {}).get("file_count") == 0
            and evidence.get("after_reset", {}).get("upload_visible") is True
            and evidence.get("next_file", {}).get("file_count") == 1
            and evidence.get("next_file", {}).get("file_name") == "id158-second.pdf"
            and evidence.get("next_file", {}).get("run_enabled") is True
            and evidence.get("next_file", {}).get("path_unchanged") is True
            and evidence.get("other_tool", {}).get("path") == "/compress-pdf"
            and evidence.get("other_tool", {}).get("result_hidden") is True
            and evidence.get("other_tool", {}).get("file_name") == "id158-second.pdf"
            and evidence.get("other_tool", {}).get("run_enabled") is True
            and not evidence["page_errors"] and not evidence["console_errors"]
        ) else "failed"
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        if evidence["overall"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
