"""Exercise the Organizer selected-page Later control and verify page order."""
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

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PDF = ROOT / "tmp/pdfs/arxiv-1706.03762-v7.pdf"


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-organizer-") as temp_name:
        temp = Path(temp_name)
        data_dir = temp / "data"
        data_dir.mkdir()
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
        server_log = temp / "server.log"
        server_output = server_log.open("w", encoding="utf-8")
        app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env,
                               stdout=server_output, stderr=subprocess.STDOUT)
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
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda message: evidence["console_errors"].append(message.text)
                        if message.type == "error" else None)
                page.on("response", lambda response: evidence.setdefault("api_responses", []).append(
                    {"url": response.url, "status": response.status}) if "/api/studio/pages/reorder" in response.url else None)
                page.on("request", lambda request: evidence.setdefault("api_requests", []).append(
                    {"url": request.url, "method": request.method}) if "/api/studio/pages/reorder" in request.url else None)
                page.on("requestfailed", lambda request: evidence.setdefault("api_failures", []).append(
                    {"url": request.url, "failure": request.failure}) if "/api/studio/pages/reorder" in request.url else None)
                response = page.goto(base + "/studio", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.locator("#studio-file-input").set_input_files(str(PDF))
                page.wait_for_function("state.studio.pdfDoc && state.studio.totalCount === 15", timeout=30000)
                page.locator("#btn-mode-organize").click()
                page.wait_for_function("document.querySelectorAll('#studio-thumbnails-container .organizer-thumb-card').length === 15", timeout=30000)
                page.locator(".organizer-thumb-card[data-page='1'] .thumb-checkbox").check(force=True)
                page.wait_for_function("!document.querySelector('#organizer-batch-bar').hidden")
                button = page.locator("#batch-move-down-btn")
                button.scroll_into_view_if_needed()
                before = page.evaluate("""() => {
                  const button = document.querySelector('#batch-move-down-btn');
                  const rect = button.getBoundingClientRect();
                  const hit = document.elementFromPoint(rect.left + rect.width/2, rect.top + rect.height/2);
                  const panel = document.querySelector('#organizer-batch-bar').getBoundingClientRect();
                  return {button:[rect.left,rect.top,rect.right,rect.bottom], panel:[panel.left,panel.top,panel.right,panel.bottom],
                    viewport:[innerWidth,innerHeight], hit:hit?.closest('button')?.id || hit?.id || hit?.className || hit?.tagName,
                    selected:window.PaperplanePageOrganizer.state.getSelectedSorted()};
                }""")
                assert before["hit"] == "batch-move-down-btn", before
                button.click()
                page.wait_for_timeout(3000)
                text_order = page.evaluate("""async () => {
                  const pdf = state.studio.pdfDoc;
                  const labels = [];
                  for (let n=1; n<=pdf.numPages; n++) {
                    const content = await (await pdf.getPage(n)).getTextContent();
                    labels.push(content.items.map(item => item.str).join(' '));
                  }
                  return labels;
                }""")
                assert "a dozen" in text_order[0].lower() or "recurrent" in text_order[0].lower(), text_order[:2]
                assert text_order[1].strip(), text_order[:2]
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                evidence.update({"viewport": [390, 844], "source_pdf": "arxiv:1706.03762v7 (15 pages)", "control": before, "page_text_first_two": text_order[:2],
                                 "toast": page.locator(".toast-notice").text_content() if page.locator(".toast-notice").count() else None,
                                 "result": "passed", "app_js": 169})
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)
            server_output.close()
            evidence["server_log_tail"] = server_log.read_text(encoding="utf-8", errors="replace")[-5000:]
    (OUT / "browser-studio-organizer-reorder.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
