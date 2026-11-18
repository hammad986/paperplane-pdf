"""Verify Page Organizer exposes page-order controls and exports that order."""
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
import json
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix="paperplane-id70-organizer-") as temp:
    root = Path(temp)
    fixture = root / "id70-organizer-order.pdf"
    with fitz.open() as document:
        for number in range(1, 4):
            page = document.new_page()
            page.insert_text((72, 72), f"PAGE MARKER {number}")
        document.save(fixture)

    app, base, _ = helper.start_server(root / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            if app.poll() is not None:
                raise RuntimeError(f"app exited with {app.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.15)

        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for number in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/organize-pdf", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.locator("#file-input").set_input_files(str(fixture))
                page.locator('#organizer-order-grid .organizer-order-card[data-page="2"]').wait_for(state="visible", timeout=10000)
                control = page.locator('#organizer-order-grid .organizer-order-card[data-page="2"] [data-order-move="up"]')
                assert control.is_visible() and control.is_enabled()
                control.click()
                order = page.locator("#pages").input_value()
                assert order == "2,1,3", order
                page.screenshot(path=str(OUT / f"id70-organizer-controls-round{number}.png"), full_page=True)
                page.locator("#run-button").click()
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=20000)
                with page.expect_download(timeout=20000) as download_event:
                    page.locator("#result-download-link").click()
                download_path = root / f"id70-organized-round{number}.pdf"
                download_event.value.save_as(download_path)
                with fitz.open(download_path) as output:
                    output_text = [p.get_text().strip() for p in output]
                assert output_text == ["PAGE MARKER 2", "PAGE MARKER 1", "PAGE MARKER 3"], output_text
                assert not errors, errors
                rounds.append({"round": number, "route_status": response.status, "page_order_input": order, "download": download_event.value.suggested_filename, "output_pages": output_text, "page_errors": errors})
                context.close()
            browser.close()
        result = {"route": "/organize-pdf", "rounds": rounds}
        (OUT / "browser-id70-organizer-controls-output.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        if sys.platform == "win32" and app.poll() is None:
            subprocess.run(["taskkill", "/PID", str(app.pid), "/T", "/F"], capture_output=True, text=True)
        if app.poll() is None:
            app.terminate()
        app.wait(timeout=5)
