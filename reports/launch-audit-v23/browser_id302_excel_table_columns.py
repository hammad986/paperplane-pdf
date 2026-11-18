from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time, io
from openpyxl import load_workbook
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id302-") as tmp:
    app, base, _ = helper.start_server(Path(tmp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        source = fitz.open()
        page = source.new_page()
        rows = [["Item", "Quantity", "Price", "Amount"], ["Pencils", "3", "2.50", "7.50"], ["Notebooks", "2", "5.00", "10.00"]]
        x_positions = [60, 190, 310, 420, 530]
        y_positions = [80, 120, 160, 200]
        for y in y_positions:
            for x in x_positions:
                pass
        shape = page.new_shape()
        for y in y_positions:
            shape.draw_line((x_positions[0], y), (x_positions[-1], y))
        for x in x_positions:
            shape.draw_line((x, y_positions[0]), (x, y_positions[-1]))
        shape.finish(color=(0, 0, 0), width=1)
        shape.commit()
        for row_no, row in enumerate(rows):
            for col_no, value in enumerate(row):
                page.insert_text((x_positions[col_no] + 5, y_positions[row_no] + 25), value, fontsize=12)
        pdf_bytes = source.tobytes()
        source.close()
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/pdf-to-excel", wait_until="networkidle")
                response = page.request.post(base + "/api/jobs", multipart={
                    "operation": "pdf_to_excel", "options": "{}",
                    "files": {"name": "inventory-table.pdf", "mimeType": "application/pdf", "buffer": pdf_bytes},
                })
                assert response.status == 202, (response.status, response.text())
                job_id = response.json()["job_id"]
                job = None
                for _ in range(100):
                    job = page.request.get(f"{base}/api/jobs/{job_id}").json()
                    if job.get("status") in ("completed", "failed"):
                        break
                    page.wait_for_timeout(100)
                assert job and job["status"] == "completed", job
                download = page.request.get(f"{base}/api/jobs/{job_id}/download")
                assert download.status == 200
                workbook = load_workbook(io.BytesIO(download.body()), data_only=True)
                sheet = workbook.active
                actual = [[sheet.cell(row=r, column=c).value for c in range(1, 5)] for r in range(1, 4)]
                assert actual == rows, actual
                assert not errors, errors
                results.append({"round": round_no, "status": job["status"], "rows": actual,
                                "download_bytes": len(download.body()), "page_errors": errors})
                page.close()
            browser.close()
        (OUT / "browser-id302-excel-table-columns.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
