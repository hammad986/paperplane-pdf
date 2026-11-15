"""Chromium regression for warnings before extreme default compression downloads."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

import fitz
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = r'''
import persistence, server, uvicorn
persistence.init_db()
uvicorn.run(server.app, host="127.0.0.1", port=int(__import__("os").environ["PAPERPLANE_PORT"]), log_level="error")
'''


def build_image_pdf(path: Path) -> None:
    page_size = (1500, 2100)
    document = fitz.open()
    for page_number in range(8):
        image = Image.frombytes("RGB", page_size, os.urandom(page_size[0] * page_size[1] * 3))
        image_path = path.with_name(f"scan-{page_number}.jpg")
        image.save(image_path, "JPEG", quality=94, optimize=False)
        page = document.new_page(width=595, height=842)
        page.insert_image(page.rect, filename=str(image_path))
        image_path.unlink()
    document.save(path, garbage=0, deflate=False)
    document.close()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="paperplane-compress-warning-v18-") as temp:
        directory = Path(temp)
        source = directory / "image-heavy-8-page.pdf"
        build_image_pdf(source)
        source_size = source.stat().st_size
        assert source_size >= 18 * 1024 * 1024, f"fixture too small: {source_size} bytes"
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("PAPERPLANE_", "CASHFREE_", "OPENAI_", "GEMINI_", "BLUESMINDS_", "ADMIN_"))}
        env.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development",
                   PAPERPLANE_DATA_DIR=str(directory / "data"), PAPERPLANE_PORT=str(port),
                   PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(64),
                   PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(32))
        app = subprocess.Popen([sys.executable, "-c", BOOTSTRAP], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Isolated compression server exited")
                    time.sleep(.1)
            else:
                raise RuntimeError("Isolated compression server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(accept_downloads=True)
                page.goto(base + "/compress-pdf", wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files(str(source))
                page.locator("#run-button").click()
                page.locator("#result-download-link").wait_for(state="visible", timeout=180000)
                warning = page.locator("#result-meta").inner_text()
                assert "over 95% smaller" in warning, warning
                dialogs = []
                page.once("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.accept()))
                with page.expect_download(timeout=30000) as download_info:
                    page.locator("#result-download-link").click()
                download = download_info.value
                downloaded = directory / "compressed.pdf"
                download.save_as(downloaded)
                with fitz.open(downloaded) as output:
                    assert output.page_count == 8
                    image_coverage = []
                    for output_page in output:
                        pix = output_page.get_pixmap(matrix=fitz.Matrix(.25, .25), alpha=False)
                        image_coverage.append(len(pix.samples) > 0 and any(pix.samples))
                assert dialogs and "Review every page" in dialogs[0]
                assert all(image_coverage), image_coverage
                evidence = {"input_bytes": source_size, "output_bytes": downloaded.stat().st_size,
                            "result_warning": warning, "pre_download_dialog": dialogs[0],
                            "pages": len(image_coverage), "rendered_page_checks": image_coverage}
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
        report = Path(__file__).with_name("browser-compression-quality-warning.json")
        report.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
