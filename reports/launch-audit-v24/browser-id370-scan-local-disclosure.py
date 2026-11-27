from __future__ import annotations

import json
import io
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from PIL import Image, ImageDraw, ImageStat
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def make_scan(path: Path) -> None:
    image = Image.new("RGB", (1200, 800), (206, 206, 206))
    draw = ImageDraw.Draw(image)
    for y in range(80, 750, 42):
        draw.line((75, y, 1115, y), fill=(168, 168, 168), width=2)
    draw.text((84, 90), "LOW CONTRAST SCAN SAMPLE", fill=(136, 136, 136))
    draw.text((84, 138), "Server mode enhances contrast and sharpness", fill=(143, 143, 143))
    image.save(path)


def main() -> None:
    evidence: dict = {"rounds": [], "server_rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id370-") as temp:
        root = Path(temp)
        source = root / "low-contrast-scan.png"
        make_scan(source)
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
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                for round_no in (1, 2):
                    response = page.goto(f"{base}/scan-to-pdf", wait_until="domcontentloaded")
                    assert response and response.status == 200
                    options = page.locator("#options")
                    text = options.inner_text()
                    assert "browser mode keeps images on this device but skips automatic contrast and sharpness enhancement" in text.lower()
                    assert "switch browser processing off to use enhanced server processing" in text.lower()
                    page.locator("#file-input").set_input_files(str(source))
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=60000)
                    metadata = page.locator("#result-meta").inner_text()
                    assert "without automatic contrast or sharpness enhancement" in metadata
                    with page.expect_download(timeout=30000) as event:
                        page.locator("#result-download-link").click()
                    target = ROOT / "reports" / "launch-audit-v24" / f"id370-local-scan-round{round_no}.pdf"
                    event.value.save_as(target)
                    with fitz.open(target) as output:
                        assert output.page_count == 1
                        assert abs(output[0].rect.width - 841.89) < 1
                        assert abs(output[0].rect.height - 595.28) < 1
                        assert len(output[0].get_images(full=True)) == 1
                        assert not output[0].get_text().strip()
                    evidence["rounds"].append({"round": round_no, "source_dimensions": [1200, 800],
                        "output_pages": 1, "page_size": "A4 landscape", "image_based": True,
                        "processing_mode_disclosed_before_run": True,
                        "result_discloses_enhancement_skipped": True,
                        "result_text": metadata, "output_bytes": target.stat().st_size})
                    if round_no == 1:
                        page.screenshot(path=str(ROOT / "reports" / "launch-audit-v24" / "browser-id370-scan-mode-disclosure.png"), full_page=True)
                server_page = context.new_page()
                server_page.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode','server')")
                server_page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                server_page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                server_page.on("dialog", lambda dialog: dialog.accept())
                for round_no in (1, 2):
                    response = server_page.goto(f"{base}/scan-to-pdf", wait_until="domcontentloaded")
                    assert response and response.status == 200
                    assert "Server processing applies automatic contrast and sharpness enhancement" in response.text()
                    assert not server_page.locator("#client-privacy-toggle").is_checked()
                    server_page.locator("#file-input").set_input_files(str(source))
                    server_page.locator("#run-button").click()
                    server_page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=60000)
                    metadata = server_page.locator("#result-meta").inner_text()
                    with server_page.expect_download(timeout=30000) as event:
                        server_page.locator("#result-download-link").click()
                    target = ROOT / "reports" / "launch-audit-v24" / f"id370-server-scan-round{round_no}.pdf"
                    event.value.save_as(target)
                    with fitz.open(target) as output:
                        assert output.page_count == 1
                        image_xref = output[0].get_images(full=True)[0][0]
                        image_bytes = output.extract_image(image_xref)["image"]
                    with Image.open(source) as original, Image.open(io.BytesIO(image_bytes)) as enhanced:
                        source_stddev = ImageStat.Stat(original.convert("L")).stddev[0]
                        enhanced_stddev = ImageStat.Stat(enhanced.convert("L")).stddev[0]
                    assert enhanced_stddev > source_stddev * 2, (source_stddev, enhanced_stddev)
                    evidence["server_rounds"].append({"round": round_no, "temporary_server_mode_selected": True,
                        "source_luminance_stddev": round(source_stddev, 2), "output_luminance_stddev": round(enhanced_stddev, 2),
                        "contrast_increased": True, "output_pages": 1, "result_text": metadata,
                        "output_bytes": target.stat().st_size})
                browser.close()
        finally:
            app.terminate()
    evidence["passed"] = len(evidence["rounds"]) == 2 and len(evidence["server_rounds"]) == 2 and not evidence["page_errors"] and not evidence["console_errors"]
    out = ROOT / "reports" / "launch-audit-v24" / "browser-id370-scan-local-disclosure.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
