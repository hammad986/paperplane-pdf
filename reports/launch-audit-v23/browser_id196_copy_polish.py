from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

with TemporaryDirectory(prefix="paperplane-id196-") as temp_name:
    temp_dir = Path(temp_name)
    remove_pdf, split_pdf = temp_dir / "remove-source.pdf", temp_dir / "split-12pages.pdf"
    with fitz.open() as document:
        for number in range(1, 4):
            document.new_page().insert_text((72, 72), f"REMOVE PAGE MARKER {number}")
        document.save(remove_pdf)
    with fitz.open() as document:
        for number in range(1, 13):
            document.new_page().insert_text((72, 72), f"SPLIT PAGE MARKER {number}")
        document.save(split_pdf)
    image_path = temp_dir / "accepted.png"
    Image.new("RGB", (40, 40), "#8aaacc").save(image_path)

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
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))

                response = page.goto(base + "/remove-pages-pdf", wait_until="domcontentloaded")
                assert response.status == 200
                page.locator("#file-input").set_input_files(str(remove_pdf))
                page.locator("#pages").fill("2")
                page.locator("#run-button").click()
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=15000)
                result_name = page.locator("#result-filename").inner_text().strip() if page.locator("#result-filename").count() else ""
                with page.expect_download(timeout=15000) as download_event:
                    page.locator("#result-download-link").click()
                downloaded = temp_dir / f"removed-round{round_number}.pdf"
                download_event.value.save_as(downloaded)
                suggested_name = download_event.value.suggested_filename
                with fitz.open(downloaded) as result:
                    text = " ".join(item.get_text() for item in result)
                    assert len(result) == 2 and "MARKER 1" in text and "MARKER 3" in text and "MARKER 2" not in text
                assert suggested_name == "removed-pages.pdf", suggested_name

                response = page.goto(base + "/split-pdf", wait_until="domcontentloaded")
                assert response.status == 200
                page.locator("#file-input").set_input_files(str(split_pdf))
                page.wait_for_function("document.querySelector('#pages')?.placeholder.includes('8-12')", timeout=10000)
                range_placeholder = page.locator("#pages").get_attribute("placeholder")
                assert range_placeholder == "e.g. 1-3, 5, 8-12", range_placeholder

                response = page.goto(base + "/resize-image-dimensions", wait_until="domcontentloaded")
                assert response.status == 200
                accept = page.locator("#file-input").get_attribute("accept")
                assert accept == "image/jpeg,image/png,image/webp", accept
                page.locator("#file-input").set_input_files(str(image_path))

                assert not errors, errors
                page.screenshot(path=str(OUT / f"id196-remove-round{round_number}.png"))
                rounds.append({"round": round_number, "remove_status": 200, "remove_filename": suggested_name,
                               "remove_content_checked": True, "split_placeholder": range_placeholder,
                               "photo_accept": accept, "page_errors": errors})
                context.close()
            browser.close()
        evidence = {"rounds": rounds}
        (OUT / "browser-id196-copy-polish.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
