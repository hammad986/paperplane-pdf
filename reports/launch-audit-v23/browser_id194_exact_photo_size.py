from pathlib import Path
from tempfile import TemporaryDirectory
import json, random, socket, sys, time

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

with TemporaryDirectory(prefix="paperplane-id194-") as temp_name:
    temp_dir = Path(temp_name)
    source = temp_dir / "high-detail-429kb.jpg"
    pixels = random.Random(20261117).randbytes(1200 * 900 * 3)
    Image.frombytes("RGB", (1200, 900), pixels).save(source, format="JPEG", quality=52, optimize=True)
    assert 400 * 1024 <= source.stat().st_size <= 450 * 1024

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
                response = page.goto(base + "/compress-image-online", wait_until="domcontentloaded")
                assert response.status == 200
                page.locator("#file-input").set_input_files(str(source))
                page.locator("#target_kb").fill("50")
                page.locator("#run-button").click()
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
                with page.expect_download(timeout=20000) as download_event:
                    page.locator("#result-download-link").click()
                output = temp_dir / f"photo-50kb-round{round_number}.jpg"
                download_event.value.save_as(output)
                with Image.open(output) as compressed:
                    compressed.load()
                    assert compressed.format == "JPEG"
                    dimensions = compressed.size
                assert output.stat().st_size <= 50 * 1024
                assert dimensions[0] < 1200 and dimensions[1] < 900
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id194-50kb-round{round_number}.png"))
                rounds.append({"round": round_number, "status": response.status,
                               "source_bytes": source.stat().st_size, "target_bytes": 50 * 1024,
                               "output_bytes": output.stat().st_size, "output_dimensions": list(dimensions),
                               "target_met": True, "page_errors": errors})
                context.close()
            browser.close()
        evidence = {"route": "/compress-image-online", "rounds": rounds}
        (OUT / "browser-id194-exact-photo-size.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
