from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

with TemporaryDirectory(prefix="paperplane-id191-") as temp_name:
    temp_dir = Path(temp_name)
    colors = [(235, 25, 25), (25, 210, 25), (25, 25, 235), (240, 220, 25)]
    sources = []
    for index, color in enumerate(colors, start=1):
        path = temp_dir / f"grid-tile-{index}.png"
        Image.new("RGB", (2400, 1800), color).save(path)
        sources.append(path)

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
                response = page.goto(base + "/merge-photos-online", wait_until="domcontentloaded")
                assert response.status == 200
                page.locator("#file-input").set_input_files([str(path) for path in sources])
                page.locator("#layout").select_option("grid")
                page.locator("#run-button").click()
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
                with page.expect_download(timeout=20000) as download_event:
                    page.locator("#result-download-link").click()
                output = temp_dir / f"grid-round{round_number}.jpg"
                download_event.value.save_as(output)
                with Image.open(output) as merged:
                    merged.load()
                    assert merged.format == "JPEG" and merged.size == (4800, 3600), merged.size
                    observed = [merged.getpixel((x, y)) for x, y in
                                ((300, 300), (2700, 300), (300, 2100), (2700, 2100))]
                    for actual, expected in zip(observed, colors):
                        assert sum(abs(a - e) for a, e in zip(actual, expected)) < 45, (actual, expected)
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id191-grid-round{round_number}.png"))
                rounds.append({"round": round_number, "status": response.status, "input_dimensions": [2400, 1800],
                               "input_count": len(sources), "layout": "grid", "output_size": [4800, 3600],
                               "output_bytes": output.stat().st_size, "four_tile_colors_verified": True,
                               "page_errors": errors})
                context.close()
            browser.close()
        evidence = {"route": "/merge-photos-online", "rounds": rounds}
        (OUT / "browser-id191-variable-grid.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
