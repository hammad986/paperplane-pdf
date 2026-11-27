"""Check Studio worker output dimensions against intrinsic PDF rotations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": [], "rotations": []}
    with TemporaryDirectory(prefix="paperplane-v24-rotation-") as temp_name:
        temp = Path(temp_name)
        data_dir = temp / "data"
        data_dir.mkdir()
        fixture = temp / "four-rotations.pdf"
        doc = fitz.open()
        for index, rotation in enumerate((0, 90, 180, 270), 1):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 72), f"ROTATION {rotation} FIXTURE", fontsize=22)
            page.draw_circle(fitz.Point(160, 180), 55, color=(0, 0, 0), width=2)
            page.draw_rect(fitz.Rect(280, 120, 410, 200), color=(1, 0, 0), width=2)
            page.set_rotation(rotation)
        doc.save(fixture)
        doc.close()
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith((
            "PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_",
            "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_",
        )) and key not in {"TESTING", "SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV": "1", "PAPERPLANE_ENV": "development",
                    "PAPERPLANE_DATA_DIR": str(data_dir), "PAPERPLANE_PORT": str(port),
                    "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(48),
                    "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(32),
                    "PAPERPLANE_SESSION_SECRET": secrets.token_urlsafe(48),
                    "PAPERPLANE_SECURE_COOKIES": "false", "PYTHONPATH": str(ROOT)})
        app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda message: evidence["console_errors"].append(message.text)
                        if message.type == "error" else None)
                response = page.goto(base + "/studio", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.locator("#studio-file-input").set_input_files(str(fixture))
                page.wait_for_function("state.studio.pdfDoc && state.studio.totalCount === 4", timeout=20000)
                for number, rotation in enumerate((0, 90, 180, 270), 1):
                    page.evaluate("async n => await window.jumpToStudioPage(n)", number)
                    page.wait_for_function("n => document.querySelector(`#studio-page-stack .studio-page-sheet[data-page='${n}'] .pdf-page-canvas`)?.dataset.rendered === 'true'", arg=number, timeout=20000)
                    metrics = page.evaluate("""n => {
                      const slot = document.querySelector(`#studio-page-stack .studio-page-sheet[data-page='${n}']`);
                      const canvas = slot.querySelector('.pdf-page-canvas');
                      const page = window.state.studio.pdfDoc.getPage(n);
                      return page.then(pdfPage => {
                        const expected = pdfPage.getViewport({scale: 1});
                        const draw = slot.querySelector('.studio-draw-canvas, #pdf-draw-canvas');
                        const rect = draw?.getBoundingClientRect();
                        return {page:n, rotation:pdfPage.rotate, expected:[expected.width,expected.height],
                          base:[Number(slot.dataset.baseWidth),Number(slot.dataset.baseHeight)],
                          css:[parseFloat(canvas.style.width),parseFloat(canvas.style.height)],
                          bitmap:[canvas.width,canvas.height], scale:Number(slot.dataset.effectiveScale),
                          overlay:rect ? [rect.width,rect.height] : null};
                      });
                    }""", number)
                    expected_w, expected_h = metrics["expected"]
                    base_w, base_h = metrics["base"]
                    css_w, css_h = metrics["css"]
                    assert metrics["rotation"] == rotation, metrics
                    assert abs(base_w - expected_w) < 1 and abs(base_h - expected_h) < 1, metrics
                    assert abs(css_w - expected_w * metrics["scale"]) < 2, metrics
                    assert abs(css_h - expected_h * metrics["scale"]) < 2, metrics
                    evidence["rotations"].append(metrics)
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                evidence["versions"] = {"app_js": 186, "styles_css": 69, "shell": 136}
                evidence["result"] = "passed"
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)
    (OUT / "browser-studio-intrinsic-rotation.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
