from __future__ import annotations

import io
import json
import random
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def make_source() -> bytes:
    rng = random.Random(194)
    image = Image.new("RGB", (1600, 1200))
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            base = (x * 13 + y * 7) % 256
            pixels[x, y] = (base, (base + rng.randrange(100)) % 256, rng.randrange(256))
    image = image.resize((870, 650), Image.Resampling.LANCZOS)
    best: tuple[int, bytes] | None = None
    for quality in range(20, 96):
        output = io.BytesIO()
        image.save(output, "JPEG", quality=quality, optimize=True)
        data = output.getvalue()
        if best is None or abs(len(data) - 429_000) < abs(best[0] - 429_000):
            best = (len(data), data)
    assert best is not None
    return best[1]


def main() -> None:
    source_data = make_source()
    evidence: dict = {"source_bytes": len(source_data), "target_kb": 50,
                      "page_errors": [], "console_errors": [], "rounds": []}
    with TemporaryDirectory(prefix="paperplane-v24-id194-") as temp:
        app, base, _ = helper.start_server(Path(temp) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                for round_no in (1, 2):
                    page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                    page.set_default_timeout(30000)
                    page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                    page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                    response = page.goto(base + "/compress-image-online", wait_until="domcontentloaded", timeout=20000)
                    page.locator("#file-input").set_input_files({"name": "photo-429kb.jpg", "mimeType": "image/jpeg", "buffer": source_data})
                    page.wait_for_function("window.state?.files?.length === 1")
                    page.locator("#target_kb").fill("50")
                    page.locator("#run-button").click()
                    page.wait_for_function("!document.querySelector('#result')?.hidden && !document.querySelector('#result-download-link')?.hidden", timeout=60000)
                    warning = page.locator("#result-message").inner_text() if page.locator("#result-message").count() else ""
                    with page.expect_download(timeout=30000) as download_info:
                        page.locator("#result-download-link").click()
                    download = download_info.value
                    output = Path(temp) / f"round-{round_no}-{download.suggested_filename}"
                    download.save_as(output)
                    evidence["rounds"].append({"round": round_no, "http_status": response.status if response else None,
                                               "output_name": download.suggested_filename,
                                               "output_bytes": output.stat().st_size,
                                               "warning": warning,
                                               "result_text": page.locator("#result").inner_text()})
                    page.close()
                browser.close()
        finally:
            app.terminate()
    for round_data in evidence["rounds"]:
        round_data["target_met"] = round_data["output_bytes"] <= 50 * 1024
        round_data["miss_explained"] = round_data["target_met"] or (
            "Could only reach" in round_data["warning"]
            and f"{round_data['output_bytes'] / 1024:.1f} KB" in round_data["warning"]
        )
    evidence["passed"] = (len(evidence["rounds"]) == 2 and abs(evidence["source_bytes"] - 429_000) <= 10_000
                           and all(x["http_status"] == 200 and x["miss_explained"] for x in evidence["rounds"])
                           and not evidence["page_errors"] and not evidence["console_errors"])
    path = ROOT / "reports" / "launch-audit-v24" / "browser-id194-photo-target.json"
    path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
