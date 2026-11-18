from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

with TemporaryDirectory(prefix="paperplane-id190-") as temp_name:
    temp_dir = Path(temp_name)
    source = temp_dir / "feedback-cta-source.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "Feedback must not cover the primary action.")
        document.save(source)

    app, base, identity = harness.start_server(temp_dir / "db")
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
                context = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
                context.add_cookies([{"name": "paperplane_token", "value": identity["accounts"][0][1], "url": base, "httpOnly": True}])
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                assert response.status == 200
                page.locator("#file-input").set_input_files(str(source))
                page.locator("#run-button").wait_for(state="visible")
                page.evaluate("""() => {
                  const launcher = document.querySelector('#pp-feedback-launcher');
                  if (launcher) launcher.hidden = false;
                  document.querySelector('#run-button').scrollIntoView({block:'center'});
                }""")
                page.wait_for_timeout(100)
                geometry = page.evaluate("""() => {
                  const button = document.querySelector('#run-button');
                  const launcher = document.querySelector('#pp-feedback-launcher');
                  const rect = element => { const r = element.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; };
                  const a = rect(button), b = rect(launcher);
                  return {viewport:{width:innerWidth,height:innerHeight}, run_button:a, feedback_launcher:b,
                    overlap:a.x < b.x+b.width && a.x+a.width > b.x && a.y < b.y+b.height && a.y+a.height > b.y,
                    run_disabled:button.disabled, launcher_visible:!launcher.hidden && getComputedStyle(launcher).display !== 'none'};
                }""")
                assert geometry["run_disabled"] is False and geometry["launcher_visible"] and not geometry["overlap"], geometry
                page.screenshot(path=str(OUT / f"id190-feedback-cta-round{round_number}.png"))
                page.locator("#run-button").click()
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=25000)
                with page.expect_download(timeout=15000) as download_event:
                    page.locator("#result-download-link").click()
                download_path = temp_dir / f"merge-round{round_number}.pdf"
                download_event.value.save_as(download_path)
                with fitz.open(download_path) as result:
                    assert len(result) == 1 and "Feedback must not cover" in result[0].get_text()
                assert not errors, errors
                rounds.append({"round": round_number, "status": response.status, **geometry,
                               "download_bytes": download_path.stat().st_size, "content_checked": True,
                               "page_errors": errors})
                context.close()
            browser.close()
        evidence = {"route": "/merge-pdf", "rounds": rounds}
        (OUT / "browser-id190-feedback-cta.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
