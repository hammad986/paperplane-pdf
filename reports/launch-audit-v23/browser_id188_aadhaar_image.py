from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time

from PIL import Image, ImageDraw, ImageFont, ImageOps
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

with TemporaryDirectory(prefix="paperplane-id188-") as temp_name:
    temp_dir = Path(temp_name)
    source = temp_dir / "synthetic-aadhaar.png"
    font = next((ImageFont.truetype(path, 78) for path in
                 ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
                 if Path(path).is_file()), ImageFont.load_default(size=78))
    digits = "274163850729"
    marker = f"{digits[:4]} {digits[4:8]} {digits[8:]}"
    original = Image.new("RGB", (950, 210), "white")
    ImageDraw.Draw(original).text((40, 45), marker, fill="black", font=font)
    original.save(source)

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
                context = browser.new_context(accept_downloads=True, viewport={"width": 1366, "height": 900})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/mask-aadhaar-card-online", wait_until="domcontentloaded")
                assert response.status == 200
                file_input = page.locator("#file-input")
                assert "image/png" in file_input.get_attribute("accept")
                file_input.set_input_files(str(source))
                page.locator("#run-button").click()
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=45000)
                with page.expect_download(timeout=20000) as download_event:
                    page.locator("#result-download-link").click()
                download_path = temp_dir / f"masked-round{round_number}.png"
                download_event.value.save_as(download_path)
                with Image.open(download_path) as result:
                    result.load()
                    assert result.format == "PNG" and result.size == original.size
                    masked = result.convert("RGB")
                with Image.open(source) as original_image:
                    prefix = f"{digits[:4]} {digits[4:8]} "
                    suffix_start = int(40 + font.getlength(prefix))
                    suffix_box = original_image.crop((suffix_start, 30, 950, 190))
                    suffix_ink = ImageOps.invert(suffix_box).getbbox()
                    assert suffix_ink is not None
                    preserved = (suffix_start + suffix_ink[0], 30 + suffix_ink[1],
                                 suffix_start + suffix_ink[2], 30 + suffix_ink[3])
                    prefix_ink = ImageOps.invert(original_image.crop((36, 30, suffix_start, 190))).getbbox()
                    assert prefix_ink is not None
                    prefix_bounds = (36 + prefix_ink[0], 30 + prefix_ink[1],
                                     36 + prefix_ink[2], 30 + prefix_ink[3])
                    assert masked.crop(prefix_bounds).getextrema() == ((0, 0), (0, 0), (0, 0))
                    assert masked.crop(preserved).tobytes() == original_image.crop(preserved).tobytes()
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id188-aadhaar-image-round{round_number}.png"))
                rounds.append({"round": round_number, "status": response.status,
                               "accept": file_input.get_attribute("accept"), "download": download_path.name,
                               "download_bytes": download_path.stat().st_size,
                               "masked_first_eight": True, "last_four_preserved": True,
                               "page_errors": errors})
                context.close()
            browser.close()
        evidence = {"route": "/mask-aadhaar-card-online", "rounds": rounds}
        (OUT / "browser-id188-aadhaar-image.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
