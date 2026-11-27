"""Measure active-page editor attachments while opening the real 69-page Studio fixture."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = Path("C:/Users/mdham/Downloads/notes.pdf")
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "probe"
    results = []
    with TemporaryDirectory(prefix="paperplane-studio-attach-") as temporary:
        app, base, _ = helper.start_server(Path(temporary) / "data")
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Studio test server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                for round_number in (1, 2):
                    context = browser.new_context(viewport={"width": 390, "height": 844},
                                                  is_mobile=True, has_touch=True)
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    cdp = context.new_cdp_session(page)
                    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
                    response = page.goto(f"{base}/studio", wait_until="domcontentloaded", timeout=30000)
                    assert response and response.status == 200
                    page.evaluate("""() => {
                      const editor = window.PaperplaneEditor;
                      editor.__attachmentProbe = [];
                      const original = editor.onPageRendered;
                      editor.onPageRendered = function(...args) {
                        this.__attachmentProbe.push({page: args[4], time: performance.now()});
                        return original.apply(this, args);
                      };
                    }""")
                    started = time.perf_counter()
                    page.locator("#studio-file-input").set_input_files(str(SOURCE))
                    page.wait_for_function("""() => document.querySelector('#page-total-indicator')?.textContent.trim() === '69'
                      && document.querySelector('.studio-page-sheet[data-page="1"] .pdf-page-canvas')?.dataset.rendered === 'true'
                      && document.querySelector('#studio-loading-overlay')?.hidden === true""", timeout=90000)
                    calls = page.evaluate("window.PaperplaneEditor.__attachmentProbe")
                    results.append({"round": round_number, "first_page_seconds": round(time.perf_counter() - started, 2),
                                    "attachment_calls": calls, "page_errors": errors})
                    assert not errors
                    context.close()
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=8)
            except Exception:
                app.kill()
    evidence = {"label": label, "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                "source_bytes": SOURCE.stat().st_size, "rounds": results}
    (OUT / f"browser-id122-editor-attachment-{label}.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
