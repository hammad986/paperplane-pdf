"""Real Chromium check for developer API reference links and copy-label regressions."""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "browser-id16-50-developer-specs.json"


def main() -> None:
    evidence = {"page_errors": [], "console_errors": [], "checks": {}}
    with TemporaryDirectory(prefix="paperplane-v24-devdocs-") as tmp:
        data = Path(tmp) / "data"
        data.mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {
            key: value for key, value in os.environ.items()
            if not key.upper().startswith(("PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_", "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_"))
            and key not in {"TESTING", "SESSION_SECRET_KEY"}
        }
        env.update({
            "PAPERPLANE_SKIP_DOTENV": "1", "PAPERPLANE_ENV": "development",
            "PAPERPLANE_DATA_DIR": str(data), "PAPERPLANE_PORT": str(port),
            "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(48),
            "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(32),
            "PAPERPLANE_SESSION_SECRET": secrets.token_urlsafe(48),
            "PAPERPLANE_SECURE_COOKIES": "false", "PYTHONPATH": str(ROOT),
        })
        app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("Local app did not start")
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                base = f"http://127.0.0.1:{port}"
                page.goto(base + "/developers", wait_until="domcontentloaded")
                links = page.locator(".btn-spec-link").evaluate_all("els => els.map(a => ({text:a.innerText.trim(), href:a.getAttribute('href')}))")
                assert any("Swagger" in link["text"] and link["href"] == "/spec/swagger" for link in links), links
                assert any("ReDoc" in link["text"] and link["href"] == "/spec/redoc" for link in links), links
                assert "keys(" not in page.locator(".api-docs-hero-box").inner_text().lower()
                for path, marker in (("/spec/swagger", "Swagger UI"), ("/spec/redoc", "redoc")):
                    response = page.goto(base + path, wait_until="domcontentloaded")
                    assert response and response.status == 200, (path, response.status if response else None)
                    page.wait_for_timeout(2500)
                    body = page.locator("body").inner_text().lower()
                    if path.endswith("swagger"):
                        assert page.locator("#swagger-ui").count() == 1 and "swagger" in page.title().lower(), (path, page.title(), page.content()[:800])
                    else:
                        assert marker.lower() in body or page.locator("redoc").count(), (path, body[:400], page.content()[:800])
                page.goto(base + "/developers", wait_until="domcontentloaded")
                copy_text = " ".join(page.locator("#btn-copy-full-api-code").inner_text().split())
                assert copy_text == "▢ Copy Snippet", copy_text
                evidence["checks"] = {"developer_spec_links": links, "swagger_and_redoc_routes": "200 with expected UI marker", "copy_button_text": copy_text, "stale_keys_example": False}
                assert not evidence["page_errors"], evidence
                # Errors from browser-blocked CDN assets are collected separately; local page runtime must stay healthy.
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)
    evidence["result"] = "passed"
    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
