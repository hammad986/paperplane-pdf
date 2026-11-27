"""Installed Chrome check for mobile workspace labels at compact widths."""
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
OUT = Path(__file__).resolve().parent


def main() -> None:
    evidence = {"rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id42-nav-") as name:
        temp = Path(name)
        data = temp / "data"
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
            "PAPERPLANE_SKIP_DOTENV": "1",
            "PAPERPLANE_ENV": "development",
            "PAPERPLANE_DATA_DIR": str(data),
            "PAPERPLANE_PORT": str(port),
            "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(48),
            "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(32),
            "PAPERPLANE_SESSION_SECRET": secrets.token_urlsafe(48),
            "PAPERPLANE_SECURE_COOKIES": "false",
            "PYTHONPATH": str(ROOT),
        })
        app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
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
                for width in (320, 390):
                    page = browser.new_page(viewport={"width": width, "height": 844})
                    page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                    page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
                    response = page.goto(f"http://127.0.0.1:{port}/ai-intelligence", wait_until="networkidle")
                    page.wait_for_selector("#mob-nav-ai span")
                    result = page.evaluate("""() => {
                      const nav = document.querySelector('.mobile-workspace-bar');
                      const ids = ['mob-nav-desk', 'mob-nav-studio', 'mob-nav-ai', 'mob-nav-download'];
                      return {
                        navVisible: !!nav && getComputedStyle(nav).display !== 'none',
                        labels: ids.map(id => {
                          const button = document.getElementById(id);
                          const label = button?.querySelector('span');
                          const labelStyle = label && getComputedStyle(label);
                          return {
                            id,
                            text: label?.textContent.trim() || '',
                            ariaLabel: button?.getAttribute('aria-label') || '',
                            fits: !!label && label.scrollWidth <= label.clientWidth + 1,
                            ellipsis: labelStyle?.textOverflow === 'ellipsis' && label.scrollWidth > label.clientWidth + 1
                          };
                        }),
                        overflow: document.documentElement.scrollWidth > innerWidth
                      };
                    }""")
                    targets = (
                        ("mob-nav-desk", "#view-tool-desk-directory"),
                        ("mob-nav-studio", "#view-pdf-studio"),
                        ("mob-nav-ai", "#view-ai-studio"),
                        ("mob-nav-download", "#view-download"),
                    )
                    result["navigation"] = []
                    for button_id, view_selector in targets:
                        page.locator(f"#{button_id}").click()
                        page.wait_for_function(
                            "([buttonId, selector]) => document.getElementById(buttonId)?.classList.contains('active') "
                            "&& !!document.querySelector(selector) && !document.querySelector(selector).hidden",
                            arg=[button_id, view_selector],
                        )
                        result["navigation"].append({"button": button_id, "view_visible": True})
                    page.screenshot(path=str(OUT / f"browser-id42-mobile-nav-{width}.png"), full_page=True)
                    evidence["rounds"].append({"width": width, "http_status": response.status if response else None, **result})
                    page.close()
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)

    evidence["passed"] = (
        len(evidence["rounds"]) == 2
        and all(round_["http_status"] == 200 and round_["navVisible"] and not round_["overflow"]
                and all(label["fits"] and not label["ellipsis"] for label in round_["labels"])
                and len(round_["navigation"]) == 4
                for round_ in evidence["rounds"])
        and not evidence["page_errors"]
        and not evidence["console_errors"]
    )
    (OUT / "browser-id42-mobile-nav-fit.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
