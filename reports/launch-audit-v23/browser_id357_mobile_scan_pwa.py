"""Mobile Chromium checks camera capture input, Scan-to-PDF output, PWA metadata/install UI."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import base64
import os

import fitz
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
BASE = os.environ.get("PAPERPLANE_TEST_BASE", "http://127.0.0.1:8766")
results = []

with TemporaryDirectory(prefix="paperplane-id357-") as temp:
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
            assert "paperplane-shell-v18" in worker_source
            assert "'/assets/app.js?v=91'" in worker_source
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
            page.wait_for_function("document.querySelector('#result') && !document.querySelector('#result').hidden", timeout=60000)
            assert jobs, "Scan-to-PDF UI did not submit a server job"
            job = jobs[-1].json()
            assert jobs[-1].status == 202, (jobs[-1].status, job)
            downloaded = page.evaluate("""async urls => {
              let state;
              for (let i=0;i<240;i++) {
                const response = await fetch(urls.status, {credentials:'same-origin'});
                if (!response.ok) throw new Error(`status ${response.status}`);
                state = await response.json();
                if (state.status === 'completed') break;
                if (state.status === 'failed') throw new Error(state.error || 'scan job failed');
                await new Promise(resolve => setTimeout(resolve, 250));
              }
              if (state?.status !== 'completed') throw new Error('scan job timed out');
              const response = await fetch(urls.download, {credentials:'same-origin'});
              if (!response.ok) throw new Error(`download ${response.status}`);
              const data = new Uint8Array(await response.arrayBuffer()); let binary='';
              for(let i=0;i<data.length;i+=8192) binary += String.fromCharCode(...data.subarray(i,i+8192));
              return {state, data:btoa(binary)};
            }""", {"status": job["status_url"], "download": job["download_url"]})
            output = OUT / f"id357-mobile-camera-scan-round{round_no}.pdf"
            output.write_bytes(base64.b64decode(downloaded["data"]))
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
                "cached_offline_shell_http": offline_response.status,
                "horizontal_overflow": False,
                "page_errors": errors,
            })
            context.close()
        browser.close()

(OUT / "browser-id357-mobile-scan-pwa.json").write_text(json.dumps({"base": BASE, "rounds": results}, indent=2), encoding="utf-8")
print(json.dumps({"rounds": len(results), "results": results}, indent=2))
