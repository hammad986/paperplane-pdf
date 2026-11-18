from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id250-") as tmp:
    app, base, _ = helper.start_server(Path(tmp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)

        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Annual report body paragraph one.", fontsize=12)
        page.insert_text((72, 96), "Annual report body paragraph two.", fontsize=12)
        page.insert_text((72, 140), "Key Findings", fontsize=14)
        pdf_bytes = pdf.tobytes()
        pdf.close()

        evidence = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/pdf-to-markdown", wait_until="networkidle")
                response = page.request.post(
                    base + "/api/jobs",
                    multipart={
                        "operation": "pdf_to_markdown",
                        "options": "{}",
                        "files": {
                            "name": "Annual Report.pdf",
                            "mimeType": "application/pdf",
                            "buffer": pdf_bytes,
                        },
                    },
                )
                assert response.status == 202, (response.status, response.text())
                job_id = response.json()["job_id"]
                status = None
                for _ in range(100):
                    status = page.request.get(f"{base}/api/jobs/{job_id}").json()
                    if status.get("status") in ("completed", "failed"):
                        break
                    page.wait_for_timeout(100)
                assert status and status.get("status") == "completed", status
                download = page.request.get(f"{base}/api/jobs/{job_id}/download")
                assert download.status == 200, (download.status, download.text())
                content = download.body().decode("utf-8").replace("\r\n", "\n")
                assert content.startswith("# Annual Report\n"), content
                assert "Annual report body paragraph one." in content
                assert "## Annual report body" not in content
                assert "## Key Findings" in content
                assert not errors, errors
                evidence.append({
                    "round": round_no,
                    "job_status": status["status"],
                    "upload_name": "Annual Report.pdf",
                    "download_name": download.headers.get("content-disposition"),
                    "download_bytes": len(download.body()),
                    "markdown": content,
                    "page_errors": errors,
                })
                page.close()
            browser.close()
        (OUT / "browser-id250-markdown-upload.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        print(json.dumps(evidence, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
