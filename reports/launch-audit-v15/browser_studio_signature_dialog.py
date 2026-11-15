"""Verify Studio Digital Signatures opens only its dialog and stays on route."""
from __future__ import annotations
import importlib.util, json, socket, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(r"C:\Users\mdham\Downloads\edited_notes-69page.pdf")
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("signature_dialog_helpers", HELPER)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)

def main() -> None:
    rounds = []
    with helpers.TemporaryDirectory(prefix="paperplane-signature-dialog-") as temp:
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
                    page.goto(base + "/studio", wait_until="domcontentloaded")
                    page.locator("#studio-file-input").set_input_files(str(SOURCE))
                    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '68'", timeout=30000)
                    page.locator("#btn-more-tools-trigger").click()
                    page.locator("#studio-sign-btn").click()
                    page.locator("#digital-sign-modal:not([hidden])").wait_for(state="visible", timeout=10000)
                    assert page.url.endswith("/studio"), page.url
                    assert not errors, errors
                    rounds.append({"round": n, "path": page.url, "signature_dialog_visible": True, "page_errors": errors})
                    page.close()
                browser.close()
        finally:
            app.terminate(); app.wait(timeout=10)
    out = ROOT / "reports" / "launch-audit-v15" / "browser-studio-signature-dialog.json"
    out.write_text(json.dumps(rounds, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rounds, indent=2))

if __name__ == "__main__": main()
