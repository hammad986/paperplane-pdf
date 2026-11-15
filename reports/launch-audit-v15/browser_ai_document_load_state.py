"""Check AI Intelligence switches atomically from empty to document-ready state."""
from __future__ import annotations
import fitz, importlib.util, json, socket, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(r"C:\Users\mdham\Downloads\edited_notes-69page.pdf")
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("ai_load_helpers", HELPER)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)

def main() -> None:
    with fitz.open(SOURCE) as source:
        pages = source.page_count
    results = []
    with helpers.TemporaryDirectory(prefix="paperplane-ai-load-state-") as temp:
        app, base, _ = helpers.start_server(Path(temp))
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2): break
                except OSError:
                    if app.poll() is not None: raise RuntimeError("Local app exited")
                    time.sleep(0.1)
            else: raise RuntimeError("Local app did not become ready")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                for n in (1, 2):
                    page = browser.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(base + "/ai-intelligence", wait_until="domcontentloaded")
                    page.locator("#ai-empty-state").wait_for(state="visible")
                    page.locator("#ai-file-input").set_input_files(str(SOURCE))
                    page.locator("#ai-active-doc-bar").wait_for(state="visible", timeout=15000)
                    assert page.locator("#ai-empty-state").is_hidden()
                    page.locator(".chat-bubble.ai").filter(has_text="Your PDF is ready").wait_for(state="visible", timeout=15000)
                    page.wait_for_function("document.querySelector('#ai-doc-meta')?.textContent.includes('68 pages')", timeout=20000)
                    assert page.locator("#ai-empty-state").is_hidden()
                    assert page.locator("#ai-upload-zone").is_hidden()
                    assert page.locator("#chat-input").is_enabled()
                    assert not errors, errors
                    results.append({"round": n, "input_pages": pages, "active_doc_visible": True,
                                    "empty_state_hidden": True, "greeting_visible": True,
                                    "metadata_text": page.locator("#ai-doc-meta").inner_text(),
                                    "page_errors": errors})
                    page.close()
                browser.close()
        finally:
            app.terminate(); app.wait(timeout=10)
    out = ROOT / "reports" / "launch-audit-v15" / "browser-ai-document-load-state.json"
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))

if __name__ == "__main__": main()
