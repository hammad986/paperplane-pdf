from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time, io, secrets
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id294-") as tmp:
    app, base, _ = helper.start_server(Path(tmp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        noise = Image.frombytes("RGB", (1600, 1000), secrets.token_bytes(1600 * 1000 * 3))
        image_buffer = io.BytesIO()
        noise.save(image_buffer, format="PNG", optimize=False)
        image_bytes = image_buffer.getvalue()
        source = fitz.open()
        for page_no in range(1, 70):
            page = source.new_page()
            page.insert_text((40, 60), f"Large tool audit page {page_no} marker {page_no}")
            if page_no == 1:
                page.insert_image(fitz.Rect(40, 90, 550, 410), stream=image_bytes)
        pdf_bytes = source.tobytes()
        source.close()
        assert 4 * 1024 * 1024 <= len(pdf_bytes) <= 7 * 1024 * 1024, len(pdf_bytes)
        rounds = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/compress-pdf", wait_until="networkidle")

            def run_job(operation, options):
                response = page.request.post(base + "/api/jobs", multipart={
                    "operation": operation, "options": json.dumps(options),
                    "files": {"name": "notes-test-69page.pdf", "mimeType": "application/pdf", "buffer": pdf_bytes},
                })
                assert response.status == 202, (operation, response.status, response.text())
                jid = response.json()["job_id"]
                job = None
                for _ in range(300):
                    job = page.request.get(f"{base}/api/jobs/{jid}").json()
                    if job.get("status") in ("completed", "failed"):
                        break
                    page.wait_for_timeout(150)
                assert job and job["status"] == "completed", (operation, job)
                result = page.request.get(f"{base}/api/jobs/{jid}/download")
                assert result.status == 200
                return job, result.body()

            for operation, options in (
                ("compress", {"preset": "balanced"}),
                ("watermark", {"text": "CONFIDENTIAL"}),
                ("page_numbers", {"format": "page_of_total", "start_number": 1}),
            ):
                start = time.monotonic()
                job, output = run_job(operation, options)
                with fitz.open(stream=output, filetype="pdf") as result:
                    page_count = result.page_count
                    texts = "\n".join(p.get_text() for p in result)
                assert page_count == 69, (operation, page_count)
                if operation == "watermark":
                    assert "CONFIDENTIAL" in texts
                if operation == "page_numbers":
                    assert "Page 1 of 69" in texts and "Page 69 of 69" in texts, texts[-500:]
                rounds.append({"operation": operation, "status": job["status"], "source_bytes": len(pdf_bytes),
                               "output_bytes": len(output), "pages": page_count,
                               "content_marker_checked": operation != "compress" or "Large tool audit page 1" in texts,
                               "elapsed_seconds": round(time.monotonic() - start, 2)})
            assert not errors, errors
            browser.close()
        (OUT / "browser-id294-large-server-tools.json").write_text(json.dumps(rounds, indent=2), encoding="utf-8")
        print(json.dumps(rounds, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
