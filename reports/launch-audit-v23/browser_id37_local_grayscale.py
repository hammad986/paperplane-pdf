"""Verify browser-local Grayscale downloads and color/text behavior in Chromium."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def make_pdf(path: Path, colors: list[tuple[float, float, float]], prefix: str) -> None:
    with fitz.open() as document:
        for page_number, color in enumerate(colors, 1):
            page = document.new_page(width=360, height=480)
            page.insert_text((40, 50), f"{prefix}-PAGE-{page_number}", fontsize=16, color=color)
            page.draw_rect(fitz.Rect(40, 90, 300, 300), color=color, fill=color)
        document.save(path)


def inspect_gray_pdf(path: Path) -> dict:
    with fitz.open(path) as document:
        counts = []
        max_difference = 0
        for page in document:
            pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
            samples = memoryview(pix.samples)
            differences = [max(samples[i], samples[i + 1], samples[i + 2])
                           - min(samples[i], samples[i + 1], samples[i + 2])
                           for i in range(0, len(samples), 3)]
            counts.append(len(differences))
            max_difference = max(max_difference, max(differences, default=0))
        return {"pages": document.page_count, "pixels_checked": sum(counts),
                "max_rgb_channel_difference": max_difference,
                "text": "\n".join(page.get_text() for page in document)}


with TemporaryDirectory(prefix="paperplane-id37-local-grayscale-") as temporary:
    root = Path(temporary)
    colored = root / "colored.pdf"
    already_gray = root / "already-gray.pdf"
    make_pdf(colored, [(1, 0, 0), (0, 0.2, 1)], "ID37-COLOR")
    make_pdf(already_gray, [(0.35, 0.35, 0.35), (0.65, 0.65, 0.65)], "ID37-GRAY")
    originals = {"colored": hashlib.sha256(colored.read_bytes()).hexdigest(),
                 "gray": hashlib.sha256(already_gray.read_bytes()).hexdigest()}

    app, base, _identity = helper.start_server(root / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local app did not start")

        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_number, width in ((1, 1366), (2, 390)):
                context = browser.new_context(viewport={"width": width, "height": 844}, accept_downloads=True)
                page = context.new_page()
                errors: list[str] = []
                job_posts: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)[:300]))
                page.on("request", lambda request: job_posts.append(request.url)
                        if request.method == "POST" and request.url.endswith("/api/jobs") else None)
                response = page.goto(base + "/convert-pdf-to-grayscale", wait_until="domcontentloaded", timeout=15000)
                assert response and response.status == 200
                page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=15000)
                if width < 700:
                    page.locator("#mobile-menu-btn").click()
                toggle = page.locator("#client-privacy-toggle")
                if not toggle.is_checked():
                    toggle.check(force=True)
                assert toggle.is_checked()
                if width < 700:
                    page.locator("#mobile-menu-btn").click()
                    page.locator("#mobile-backdrop").wait_for(state="hidden")
                    assert page.locator("#mobile-menu-btn").get_attribute("aria-expanded") == "false"

                round_data = {"round": round_number, "viewport": width, "local_mode": True, "downloads": []}
                for case_name, source in (("colored", colored), ("already_gray", already_gray)):
                    if case_name == "already_gray":
                        page.reload(wait_until="domcontentloaded")
                        page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=15000)
                        if width < 700:
                            page.locator("#mobile-menu-btn").click()
                            page.locator("#mobile-backdrop").wait_for(state="visible")
                        toggle = page.locator("#client-privacy-toggle")
                        if not toggle.is_checked():
                            toggle.check(force=True)
                        if width < 700:
                            page.locator("#mobile-menu-btn").click()
                            page.locator("#mobile-backdrop").wait_for(state="hidden")
                            assert page.locator("#mobile-menu-btn").get_attribute("aria-expanded") == "false"
                    page.locator("#file-input").set_input_files(str(source))
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
                    page.locator("#result-download-link").evaluate("element => element.scrollIntoView({block: 'center'})")
                    page.wait_for_timeout(200)
                    with page.expect_download(timeout=20000) as download_wait:
                        page.locator("#result-download-link").click()
                    download = download_wait.value
                    output = root / f"{case_name}-round-{round_number}.pdf"
                    download.save_as(output)
                    checked = inspect_gray_pdf(output)
                    assert checked["max_rgb_channel_difference"] == 0, checked
                    assert checked["pages"] == 2, checked
                    if case_name == "colored":
                        assert "ID37-COLOR-PAGE-1" not in checked["text"], checked["text"]
                        assert "150 DPI" in page.locator("#result").inner_text()
                    else:
                        assert originals["gray"] == hashlib.sha256(output.read_bytes()).hexdigest()
                        assert "ID37-GRAY-PAGE-1" in checked["text"] and "ID37-GRAY-PAGE-2" in checked["text"]
                        assert "already grayscale" in page.locator("#result").inner_text().lower()
                    round_data["downloads"].append({"case": case_name, "pages": checked["pages"],
                        "pixels_checked": checked["pixels_checked"],
                        "max_rgb_channel_difference": checked["max_rgb_channel_difference"],
                        "searchable_text_preserved": bool(checked["text"].strip()),
                        "byte_identical_to_source": originals["gray"] == hashlib.sha256(output.read_bytes()).hexdigest()
                            if case_name == "already_gray" else False})
                assert not job_posts, job_posts
                assert not errors, errors
                round_data.update({"server_job_posts": job_posts, "page_errors": errors})
                rounds.append(round_data)
                context.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=10)

report = {"operation": "grayscale", "rounds": rounds,
          "result": "PASS" if len(rounds) == 2 else "FAIL"}
path = OUT / "browser-id37-local-grayscale.json"
path.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
assert report["result"] == "PASS"
