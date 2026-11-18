from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id301-") as tmp:
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
        for n in range(1, 25):
            pdf.new_page().insert_text((72, 72), f"Photo {n}")
        data = pdf.tobytes()
        pdf.close()
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/ai-intelligence", wait_until="networkidle")
                response = page.request.post(base + "/api/ai/chat", multipart={
                    "question": "What is this document about?",
                    "file": {"name": "sparse-photo-gallery.pdf", "mimeType": "application/pdf", "buffer": data},
                })
                assert response.status == 200, (response.status, response.text())
                payload = response.json()
                answer = payload["answer"]
                assert "very little searchable text" in answer and "OCR" in answer, payload
                assert "No relevant information found" not in answer
                assert payload["retrieval_method"] == "Sparse PDF Text Check"
                assert not errors, errors
                results.append({"round": round_no, "page_count": 24, "answer": answer,
                                "retrieval_method": payload["retrieval_method"], "page_errors": errors})
                page.close()
            browser.close()
        (OUT / "browser-id301-sparse-pdf-message.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
