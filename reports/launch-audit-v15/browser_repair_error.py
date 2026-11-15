"""Check the repair tool presents a safe error for an unrecoverable PDF."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import socket
import time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("repair_error_helpers", HELPER)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)


def main() -> None:
    records = []
    with helpers.TemporaryDirectory(prefix="paperplane-repair-error-") as temp:
        folder = Path(temp)
        corrupt = folder / "unrecoverable.pdf"
        corrupt.write_bytes(b"%PDF-1.7\ninvalid object with no trailer")
        app, base, _ = helpers.start_server(folder)
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local app exited during startup")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local app did not become ready")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                for n in (1, 2):
                    page = browser.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(base + "/repair-pdf", wait_until="domcontentloaded")
                    with page.expect_file_chooser() as chooser:
                        page.locator("#browse").click()
                    chooser.value.set_files(str(corrupt))
                    page.locator("#run-button").click()
                    page.locator("#result").wait_for(state="visible", timeout=30000)
                    page.wait_for_function("document.querySelector('#result').textContent.includes('too damaged to repair')", timeout=30000)
                    message = page.locator("#result").inner_text()
                    assert "This PDF is too damaged to repair automatically." in message, message
                    assert "not a dict" not in message and "pikepdf" not in message, message
                    assert not errors, errors
                    records.append({"round": n, "safe_message": message.strip(), "page_errors": errors})
                    page.close()
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=10)
    out = ROOT / "reports" / "launch-audit-v15" / "browser-repair-error.json"
    out.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
