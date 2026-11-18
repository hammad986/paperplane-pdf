from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

with TemporaryDirectory(prefix="paperplane-id193-") as temp_name:
    temp_dir = Path(temp_name)
    source = temp_dir / "studio-quota-source.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "Studio export quota error fixture")
        document.save(source)
    app, base, _ = harness.start_server(temp_dir / "db")
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.15)
        else:
            raise RuntimeError("Local Paperplane server did not start")

        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_number in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                page = context.new_page()
                errors, intercepted = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                def quota_response(route):
                    intercepted.append(route.request.url)
                    route.fulfill(status=402, content_type="application/json", body=json.dumps({
                        "detail": {"code": "TIER_LIMIT_REACHED",
                                   "message": "Daily operation limit reached. Upgrade your plan or use Local Processing where available."}
                    }))
                page.route("**/api/studio/apply-edits", quota_response)
                response = page.goto(base + "/studio", wait_until="domcontentloaded")
                assert response.status == 200
                page.locator("#studio-file-input").set_input_files(str(source))
                page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'", timeout=20000)
                page.locator("#save-studio-btn").click()
                page.locator("#upgrade-modal").wait_for(state="visible")
                message = page.locator("#upgrade-context-alert").inner_text()
                assert "Daily operation limit reached" in message and "[object Object]" not in page.locator("body").inner_text()
                assert len(intercepted) == 1, intercepted
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id193-studio-quota-round{round_number}.png"))
                rounds.append({"round": round_number, "status": response.status, "intercepted": intercepted,
                               "quota_modal_visible": True, "message": message,
                               "object_string_leaked": False, "page_errors": errors})
                context.close()
            browser.close()
        evidence = {"rounds": rounds}
        (OUT / "browser-id193-quota-export.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
