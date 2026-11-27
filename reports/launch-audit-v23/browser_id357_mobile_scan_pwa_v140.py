"""Mobile Chromium checks camera capture input, Scan-to-PDF output, PWA metadata/install UI."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import base64
import os
import atexit
import socket
import sys
import time

import fitz
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
INDEX_HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
SERVICE_WORKER = (ROOT / "web" / "assets" / "service-worker.js").read_text(encoding="utf-8")
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper
results = []

with TemporaryDirectory(prefix="paperplane-id357-") as temp:
    app, BASE, _ = helper.start_server(Path(temp) / "data")
    atexit.register(lambda: app.terminate() if app.poll() is None else None)
    port = int(BASE.rsplit(":", 1)[1])
    for _ in range(600):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.2)
    else:
        raise RuntimeError("isolated Paperplane server did not start")
    source = Path(temp) / "camera-page.jpg"
    image = Image.new("RGB", (900, 1200), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((45, 45, 855, 1155), outline="#172126", width=10)
    draw.text((110, 130), "MOBILE CAMERA SCAN FIXTURE", fill="#172126", stroke_width=1)
    draw.text((110, 190), "Page captured by the camera upload control.", fill="#172126")
    image.save(source, quality=92)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for round_no in (1, 2):
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                device_scale_factor=1,
                is_mobile=True,
                has_touch=True,
                accept_downloads=True,
            )
            page = context.new_page()
            errors = []
            jobs = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: jobs.append(response) if response.url.endswith("/api/jobs") and response.request.method == "POST" else None)

            response = page.goto(f"{BASE}/scan-to-pdf", wait_until="domcontentloaded")
            assert response and response.status == 200
            manifest_response = page.request.get(f"{BASE}/manifest.webmanifest")
            assert manifest_response.status == 200
            assert "application/manifest+json" in manifest_response.headers.get("content-type", "")
            manifest = manifest_response.json()
            assert manifest["id"] == "/" and manifest["display"] == "standalone"
            for icon in manifest["icons"]:
                icon_response = page.request.get(BASE + icon["src"])
                assert icon_response.status == 200 and icon_response.body().startswith(b"\x89PNG\r\n\x1a\n")
            worker = page.request.get(f"{BASE}/service-worker.js")
            assert worker.status == 200 and worker.headers.get("service-worker-allowed") == "/"
            worker_source = worker.text()
            assert "paperplane-shell-v63" in worker_source
            assert "'/assets/app.js?v=129'" in worker_source
            assert "src=\"/assets/app.js?v=129\"" in INDEX_HTML
            page.wait_for_function("navigator.serviceWorker && navigator.serviceWorker.ready.then(() => true)", timeout=15000)

            camera = page.locator("#scan-camera-input")
            assert camera.get_attribute("capture") == "environment"
            assert camera.get_attribute("accept") == "image/*"
            assert page.locator("#install-app-btn").is_hidden()
            camera_button = page.locator("#scan-camera-btn")
            assert camera_button.is_visible()
            assert camera_button.evaluate("el => { const r=el.getBoundingClientRect(); return r.width >= 44 && r.height >= 44; }")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            if round_no == 1:
                page.screenshot(path=OUT / "id357-scan-mobile-390.png", full_page=True)

            # The browser-controlled install event is simulated because Playwright's
            # headless browser does not expose its native install prompt UI.
            install_outcome = "accepted" if round_no == 1 else "dismissed"
            page.evaluate("""outcome => {
              const event = new Event('beforeinstallprompt', {cancelable:true});
              event.prompt = async () => {};
              event.userChoice = Promise.resolve({outcome});
              window.dispatchEvent(event);
            }""", install_outcome)
            assert page.locator("#install-app-btn").is_visible()
            page.locator("#install-app-btn").click()
            page.wait_for_function("document.querySelector('#install-app-btn').hidden")
            expected_install_status = "installed" if install_outcome == "accepted" else "canceled"
            assert expected_install_status in page.locator("#install-app-status").inner_text().lower()

            with page.expect_file_chooser() as chooser:
                camera_button.click()
            chooser.value.set_files(str(source))
            page.wait_for_function("document.querySelectorAll('#file-list .file-item, #file-list .file-card, #file-list > *').length > 0")
            assert page.locator("#file-input").get_attribute("accept")
            assert page.locator("#file-hint").is_visible()
            page.locator("#page_size").select_option("letter")

            page.locator("#run-button").click()
            output = OUT / f"id357-mobile-camera-scan-round{round_no}.pdf"
            page.wait_for_function("document.querySelector('#result-download-link:not([hidden])')", timeout=60000)
            with page.expect_download(timeout=30000) as download_event:
                page.locator("#result-download-link").click()
            download_event.value.save_as(output)
            assert not jobs, "Browser-local Scan-to-PDF unexpectedly submitted a server job"
            with fitz.open(output) as pdf:
                assert len(pdf) == 1
                assert (round(pdf[0].rect.width), round(pdf[0].rect.height)) == (612, 792)
                pix = pdf[0].get_pixmap(matrix=fitz.Matrix(0.3, 0.3), alpha=False)
                assert len(set(pix.samples)) > 8
            offline_page = context.new_page()
            context.set_offline(True)
            offline_response = offline_page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=15000)
            assert offline_response and offline_response.status == 200
            assert offline_page.locator("#app-shell").count() == 1
            assert offline_page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            context.set_offline(False)
            assert not errors, errors
            results.append({
                "round": round_no,
                "viewport": "390x844 touch emulation",
                "camera_capture": "environment",
                "manifest_content_type": manifest_response.headers.get("content-type"),
                "service_worker_scope_header": worker.headers["service-worker-allowed"],
                "install_prompt": f"shown only after browser event; {install_outcome} mock hides consumed button",
                "pdf_download": output.name,
                "pdf_pages": 1,
                "page_size_points": [612, 792],
                "processing": "browser local, zero server jobs",
                "cached_offline_shell_http": offline_response.status,
                "horizontal_overflow": False,
                "page_errors": errors,
            })
            context.close()
        browser.close()
    app.terminate()
    app.wait(timeout=15)

(OUT / "browser-id357-mobile-scan-pwa-v140.json").write_text(json.dumps({"base": BASE, "rounds": results,
    "cache_name": "paperplane-shell-v63", "app_asset": "/assets/app.js?v=129"}, indent=2), encoding="utf-8")
print(json.dumps({"rounds": len(results), "results": results}, indent=2))

