from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

with TemporaryDirectory(prefix="paperplane-id195-") as temp_name:
    temp_dir = Path(temp_name)
    source = temp_dir / "resize-source.png"
    Image.new("RGB", (120, 80), (120, 180, 220)).save(source)
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
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page = context.new_page()
                errors, operations = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: operations.append(request.url)
                        if request.method == "POST" and "/api/jobs" in request.url else None)
                response = page.goto(base + "/resize-image-dimensions", wait_until="domcontentloaded")
                assert response.status == 200
                page.locator("#file-input").set_input_files(str(source))
                page.wait_for_function("document.querySelector('#run-button')?.disabled === true")
                state = page.evaluate("""() => ({
                  preset:document.querySelector('#preset')?.value,
                  width:document.querySelector('#width')?.value,
                  height:document.querySelector('#height')?.value,
                  scale:document.querySelector('#scale_percent')?.value,
                  runDisabled:document.querySelector('#run-button')?.disabled,
                  runLabel:document.querySelector('#run-button')?.innerText.trim(),
                  fileName:document.querySelector('#file-list')?.innerText.trim()
                })""")
                assert state["preset"] == "custom" and not state["width"] and not state["height"] and not state["scale"]
                assert state["fileName"] and "resize-source.png" in state["fileName"]
                assert state["runDisabled"] and "Enter a size or scale" in state["runLabel"]
                assert not page.locator("#result-download-link").is_visible()
                page.locator("#run-button").evaluate("button => button.click()")
                page.wait_for_timeout(150)
                assert not page.locator("#result-download-link").is_visible()
                assert not operations and not errors, {"operations": operations, "errors": errors}
                page.screenshot(path=str(OUT / f"id195-resize-validation-round{round_number}.png"))
                rounds.append({"round": round_number, "status": response.status, **state,
                               "server_job_submissions": len(operations), "page_errors": errors})
                context.close()
            browser.close()
        evidence = {"route": "/resize-image-dimensions", "rounds": rounds}
        (OUT / "browser-id195-resize-validation.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
