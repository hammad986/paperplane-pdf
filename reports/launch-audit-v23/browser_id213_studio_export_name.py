from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

with TemporaryDirectory(prefix="paperplane-id213-") as temp_name:
    temp_dir = Path(temp_name)
    source = temp_dir / "studio-export-name-fixture.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "Studio export filename evidence.")
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
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/studio", wait_until="domcontentloaded")
                assert response.status == 200
                page.locator("#studio-file-input").set_input_files(str(source))
                page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'", timeout=20000)
                with page.expect_download(timeout=20000) as download_event:
                    page.locator("#save-studio-btn").click()
                download = download_event.value
                output = temp_dir / f"studio-export-round{round_number}.pdf"
                download.save_as(output)
                expected_name = "edited_studio-export-name-fixture.pdf"
                assert download.suggested_filename == expected_name, download.suggested_filename
                toast = page.locator(".toast-notice").inner_text()
                assert expected_name in toast and "exported successfully" in toast.casefold(), toast
                with fitz.open(output) as result:
                    assert len(result) == 1 and "Studio export filename evidence." in result[0].get_text()
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id213-studio-export-name-round{round_number}.png"))
                rounds.append({"round": round_number, "status": response.status,
                               "download_name": download.suggested_filename, "toast": toast,
                               "pdf_pages": 1, "content_checked": True, "page_errors": errors})
                context.close()
            browser.close()
        evidence = {"rounds": rounds}
        (OUT / "browser-id213-studio-export-name.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
