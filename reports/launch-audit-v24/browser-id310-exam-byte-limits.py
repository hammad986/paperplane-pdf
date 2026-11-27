from __future__ import annotations

import io
import json
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

PRESETS = {
    "ssc_photo": ((350, 450), 20_480, 50_000), "ssc_sign": ((400, 200), 10_240, 20_000),
    "upsc_photo": ((350, 350), 20_480, 300_000), "upsc_sign": ((350, 350), 20_480, 300_000),
    "ibps_photo": ((200, 230), 20_480, 50_000), "ibps_sign": ((140, 60), 10_240, 20_000),
}


def fixture() -> bytes:
    import random
    pixels = random.Random(310).randbytes(1200 * 900 * 3)
    image = Image.frombytes("RGB", (1200, 900), pixels)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=52, optimize=True)
    return output.getvalue()


def download_image(download, target: Path) -> dict:
    download.save_as(target)
    with Image.open(target) as image:
        image.verify()
    with Image.open(target) as image:
        return {"name": download.suggested_filename, "bytes": target.stat().st_size,
                "dimensions": list(image.size), "format": image.format}


def main() -> None:
    image_data = fixture()
    evidence: dict = {"source_bytes": len(image_data), "browser_presets": [],
                      "server_outputs": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id310-") as temp:
        root = Path(temp)
        app, base, _ = helper.start_server(root / "data")
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
                context = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
                page = context.new_page()
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)

                for round_no in (1, 2):
                    for preset, (dimensions, min_bytes, max_bytes) in PRESETS.items():
                        page.goto(base + "/ssc-photo-resizer", wait_until="domcontentloaded")
                        page.locator("#preset").select_option(preset)
                        page.locator("#format").select_option("jpg")
                        page.locator("#file-input").set_input_files({"name": "detailed-source.jpg", "mimeType": "image/jpeg", "buffer": image_data})
                        page.locator("#run-button").click()
                        page.wait_for_function("document.querySelector('#result-download-link') && !document.querySelector('#result-download-link').hidden", timeout=60000)
                        with page.expect_download(timeout=30000) as info:
                            page.locator("#result-download-link").click()
                        output = download_image(info.value, root / f"browser-{round_no}-{preset}.jpg")
                        result_text = page.locator("#result-meta").inner_text()
                        output.update({"round": round_no, "preset": preset, "expected_dimensions": list(dimensions),
                                       "min_bytes": min_bytes, "max_bytes": max_bytes,
                                       "visible_exact_bytes": f"{output['bytes']:,} bytes" in result_text,
                                       "result_text": result_text})
                        evidence["browser_presets"].append(output)
                        if preset == "ssc_photo" and round_no == 1:
                            page.screenshot(path=str(ROOT / "reports" / "launch-audit-v24" / "browser-id310-ssc-mobile.png"), full_page=True)

                api_results = context.request
                for round_no in (1, 2):
                  for output_format in ("jpg", "pdf"):
                    response = api_results.post(base + "/api/jobs", multipart={
                        "operation": "photo_resizer",
                        "options": json.dumps({"preset": "ssc_photo", "format": output_format}),
                        "files": {"name": "detailed-source.jpg", "mimeType": "image/jpeg", "buffer": image_data},
                    })
                    if response.status != 202:
                        raise AssertionError(f"Server-mode photo resizer submission failed: {response.status} {response.text()}")
                    job = response.json()
                    job_id = job["job_id"]
                    for _ in range(300):
                        status_response = api_results.get(base + f"/api/jobs/{job_id}")
                        status = status_response.json()
                        if status.get("status") in {"completed", "failed"}:
                            break
                        time.sleep(0.1)
                    if status.get("status") != "completed":
                        raise AssertionError(f"Server-mode resizer failed: {status}")
                    download_response = api_results.get(base + f"/api/jobs/{job_id}/download")
                    if download_response.status != 200:
                        raise AssertionError(f"Could not fetch server-mode output: {download_response.status}")
                    raw = download_response.body()
                    target = root / status["output_name"]
                    target.write_bytes(raw)
                    if output_format == "jpg":
                        with Image.open(target) as image:
                            image.verify()
                        with Image.open(target) as image:
                            actual_dimensions = list(image.size)
                    else:
                        import fitz
                        with fitz.open(target) as document:
                            assert document.page_count == 1
                            actual_dimensions = [round(document[0].rect.width), round(document[0].rect.height)]
                    evidence["server_outputs"].append({"round": round_no, "format": output_format, "bytes": len(raw),
                        "min_bytes": 20_480, "max_bytes": 50_000, "dimensions": actual_dimensions,
                        "output_name": status["output_name"]})
                browser.close()
        finally:
            app.terminate()
    evidence["passed"] = (
        len(evidence["browser_presets"]) == 2 * len(PRESETS)
        and all(x["dimensions"] == x["expected_dimensions"] and x["min_bytes"] <= x["bytes"] <= x["max_bytes"] and x["visible_exact_bytes"] for x in evidence["browser_presets"])
        and len(evidence["server_outputs"]) == 4
        and all(x["min_bytes"] <= x["bytes"] <= x["max_bytes"] for x in evidence["server_outputs"])
        and not evidence["page_errors"] and not evidence["console_errors"]
    )
    output = ROOT / "reports" / "launch-audit-v24" / "browser-id310-exam-byte-limits.json"
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
