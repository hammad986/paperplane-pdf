from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id256-") as tmp:
    app, base, _ = helper.start_server(Path(tmp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/repair-pdf", wait_until="networkidle")
                response = page.request.post(
                    base + "/api/jobs",
                    multipart={"operation": "repair", "options": "{}", "files": {
                        "name": "unrecoverable.pdf", "mimeType": "application/pdf",
                        "buffer": b"%PDF-1.7\ninvalid object with no trailer",
                    }},
                )
                assert response.status == 202, (response.status, response.text())
                job_id = response.json()["job_id"]
                state = None
                for _ in range(100):
                    state = page.request.get(f"{base}/api/jobs/{job_id}").json()
                    if state.get("status") in ("failed", "completed"):
                        break
                    page.wait_for_timeout(100)
                assert state and state["status"] == "failed", state
                message = state.get("error") or ""
                assert message == "This PDF is too damaged to repair automatically.", message
                assert "pikepdf" not in message.lower() and "code=4" not in message.lower()
                assert not errors, errors
                results.append({"round": round_no, "status": state["status"],
                                "visible_safe_error": message, "page_errors": errors})
                page.close()
            browser.close()
        (OUT / "browser-id256-repair-safe-error.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
