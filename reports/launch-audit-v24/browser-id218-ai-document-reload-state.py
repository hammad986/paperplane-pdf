"""Verify restored AI PDFs never display the empty state as if no document were loaded."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id218-ai-document-reload-state.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id218-") as temp_name:
        temp = Path(temp_name)
        source = temp / "id218-restored-document.pdf"
        with fitz.open() as document:
            document.new_page().insert_text((72, 100), "ID218 restored AI document marker")
            document.save(source)
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
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                page = context.new_page()
                page.set_default_timeout(20000)
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: evidence["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                response = page.goto(base + "/ai-intelligence", wait_until="domcontentloaded")
                page.locator("#ai-file-input").set_input_files(str(source))
                page.wait_for_function("state.files.length === 1 && document.querySelector('#ai-doc-name')?.textContent === 'id218-restored-document.pdf'")
                page.wait_for_function("document.querySelector('#ai-active-doc-bar')?.hidden === false && document.querySelector('#ai-empty-state')?.hidden === true")
                evidence["before_reload"] = page.evaluate("""() => ({
                  file: state.files[0]?.name,
                  active_bar_visible: !document.querySelector('#ai-active-doc-bar').hidden,
                  empty_state_hidden: document.querySelector('#ai-empty-state').hidden,
                  greeting_visible: [...document.querySelectorAll('#chat-messages .chat-bubble')].some(b => b.textContent.includes('Your PDF is ready'))
                })""")
                page.reload(wait_until="domcontentloaded")
                page.wait_for_function("state.files.length === 1 && state.files[0].name === 'id218-restored-document.pdf'")
                page.wait_for_function("document.querySelector('#ai-active-doc-bar')?.hidden === false && document.querySelector('#ai-empty-state')?.hidden === true")
                evidence["after_reload"] = page.evaluate("""() => ({
                  file: state.files[0]?.name,
                  active_bar_visible: !document.querySelector('#ai-active-doc-bar').hidden,
                  displayed_file: document.querySelector('#ai-doc-name')?.textContent,
                  empty_state_hidden: document.querySelector('#ai-empty-state').hidden,
                  empty_copy_visible: getComputedStyle(document.querySelector('#ai-empty-state')).display !== 'none' && !document.querySelector('#ai-empty-state').hidden,
                  greeting_visible: [...document.querySelectorAll('#chat-messages .chat-bubble')].some(b => b.textContent.includes('Your PDF is ready')),
                  chat_enabled: document.querySelector('#chat-input')?.disabled === false
                })""")
                browser.close()
            evidence["http_status"] = response.status if response else None
        finally:
            app.terminate()
            app.wait(timeout=5)
        evidence["overall"] = "passed" if (
            evidence.get("http_status") == 200
            and evidence.get("before_reload", {}).get("active_bar_visible") is True
            and evidence.get("before_reload", {}).get("empty_state_hidden") is True
            and evidence.get("after_reload", {}).get("file") == "id218-restored-document.pdf"
            and evidence.get("after_reload", {}).get("displayed_file") == "id218-restored-document.pdf"
            and evidence.get("after_reload", {}).get("active_bar_visible") is True
            and evidence.get("after_reload", {}).get("empty_state_hidden") is True
            and evidence.get("after_reload", {}).get("empty_copy_visible") is False
            and evidence.get("after_reload", {}).get("greeting_visible") is True
            and evidence.get("after_reload", {}).get("chat_enabled") is True
            and not evidence["page_errors"] and not evidence["console_errors"]
        ) else "failed"
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        if evidence["overall"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
