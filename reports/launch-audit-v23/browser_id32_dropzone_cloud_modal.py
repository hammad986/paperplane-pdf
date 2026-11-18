"""Reproduce ID 32 with real Chromium DataTransfer file drops on its three named tools."""
from pathlib import Path
from tempfile import TemporaryDirectory
import base64
import json
import socket
import sys
import subprocess
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FIXTURE = OUT / "fixtures" / "totpdf-sample-5-pages.pdf"
ROUTES = ["/summarize-pdf", "/compare-pdf", "/edit-pdf"]
PDF_B64 = base64.b64encode(FIXTURE.read_bytes()).decode("ascii")
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix="paperplane-id32-") as temp:
    app, base, identities = helper.start_server(Path(temp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            if app.poll() is not None:
                raise RuntimeError(f"local app exited during startup with code {app.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.15)
        else:
            raise RuntimeError("local app did not become ready")
        email, token = identities["accounts"][0]
        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                context.add_cookies([{"name": "paperplane_token", "value": token, "url": base, "httpOnly": True}])
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                route_results = []
                def advertise_local_ai_service(route):
                    response = route.fetch()
                    catalog = response.json()
                    catalog["summarize"].update({"available": True, "status": "AVAILABLE", "prerequisite": ""})
                    route.fulfill(response=response, json=catalog)

                page.route("**/api/operations", advertise_local_ai_service)
                for route in ROUTES:
                    response = page.goto(base + route, wait_until="domcontentloaded")
                    assert response and response.status == 200, (route, response.status if response else None)
                    page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=10000)
                    page.wait_for_function("() => !document.querySelector('#file-input')?.disabled", timeout=5000)
                    assert page.locator("#cloud-modal").is_hidden(), route
                    page.locator("#dropzone").dispatch_event("dragenter", {"dataTransfer": None})
                    page.locator("#dropzone").dispatch_event("dragover", {"dataTransfer": None})
                    page.evaluate(
                        """({pdfB64, filename}) => {
                          const bytes = Uint8Array.from(atob(pdfB64), c => c.charCodeAt(0));
                          const file = new File([bytes], filename, {type: 'application/pdf'});
                          const transfer = new DataTransfer();
                          transfer.items.add(file);
                          const zone = document.querySelector('#dropzone');
                          zone.dispatchEvent(new DragEvent('drop', {bubbles:true,cancelable:true,dataTransfer:transfer}));
                        }""",
                        {"pdfB64": PDF_B64, "filename": "id32-drop-fixture.pdf"},
                    )
                    page.wait_for_timeout(250)
                    try:
                        page.locator("#file-list .file-row-name").filter(has_text="id32-drop-fixture.pdf").wait_for(state="visible", timeout=3000)
                    except Exception as error:
                        diagnostic = page.evaluate("""() => ({operation: typeof state !== 'undefined' ? state.operation : null, files: document.querySelector('#file-list')?.innerText, modalHidden: document.querySelector('#cloud-modal')?.hidden, bodyText: document.body.innerText.slice(-800), dropzone: document.querySelector('#dropzone')?.outerHTML.slice(0,500)})""")
                        raise AssertionError({"route": route, "drop_diagnostic": diagnostic}) from error
                    assert page.locator("#cloud-modal").is_hidden(), (route, page.locator("#cloud-modal").get_attribute("hidden"))
                    names = page.locator("#file-list .file-row-name").all_text_contents()
                    assert "id32-drop-fixture.pdf" in names, (route, names)
                    route_results.append({"route": route, "status": response.status, "file_dropped_and_listed": True, "cloud_modal_open": False})
                assert not errors, errors
                rounds.append({"round": round_no, "account": email, "routes": route_results, "page_errors": errors})
                context.close()
            browser.close()
        result = {"fixture": FIXTURE.name, "rounds": rounds}
        (OUT / "browser-id32-dropzone-cloud-modal.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        if sys.platform == "win32" and app.poll() is None:
            subprocess.run(["taskkill", "/PID", str(app.pid), "/T", "/F"], capture_output=True, text=True)
        if app.poll() is None:
            app.terminate()
        app.wait(timeout=5)
