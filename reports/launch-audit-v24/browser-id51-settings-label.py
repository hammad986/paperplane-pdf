"""Measure the Storage & Privacy tab label against its selected control at common widths."""
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
OUT = Path(__file__).resolve().parent / "browser-id51-settings-label.json"


def main() -> None:
    evidence = {"widths": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-settings-") as tmp:
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
        env.update({"PAPERPLANE_SKIP_DOTENV": "1", "PAPERPLANE_ENV": "development", "PAPERPLANE_DATA_DIR": str(data), "PAPERPLANE_PORT": str(port), "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(48), "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(32), "PAPERPLANE_SESSION_SECRET": secrets.token_urlsafe(48), "PAPERPLANE_SECURE_COOKIES": "false", "PYTHONPATH": str(ROOT)})
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
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                page.locator("#sidebar-settings-gear-btn").click()
                page.locator("#settings-modal").wait_for(state="visible")
                page.locator("#settings-tab-btn-privacy").click()
                for width in (320, 390, 820, 1104, 1366):
                    page.locator("#close-settings-modal").click()
                    page.set_viewport_size({"width": width, "height": 900})
                    page.evaluate("window.openSettingsModal('privacy')")
                    page.locator("#settings-tab-btn-privacy.active").wait_for(state="visible")
                    page.wait_for_timeout(120)
                    metrics = page.locator("#settings-tab-btn-privacy").evaluate("el => { const b=el.getBoundingClientRect(), t=el.querySelector('small'), r=t.getBoundingClientRect(), m=document.querySelector('#settings-modal'), c=m.querySelector('.settings-modal-card'), mr=m.getBoundingClientRect(), cr=c.getBoundingClientRect(); return {selected:el.classList.contains('active'), label:t.innerText, button:{left:b.left,right:b.right,top:b.top,bottom:b.bottom,clientHeight:el.clientHeight,scrollHeight:el.scrollHeight}, modal:{left:mr.left,right:mr.right,width:mr.width,display:getComputedStyle(m).display,position:getComputedStyle(m).position}, card:{left:cr.left,right:cr.right,width:cr.width,computedWidth:getComputedStyle(c).width}, text:{left:r.left,right:r.right,top:r.top,bottom:r.bottom,scrollHeight:t.scrollHeight,clientHeight:t.clientHeight,display:getComputedStyle(t).display}, viewport:innerWidth, docWidth:document.documentElement.scrollWidth}; }")
                    assert metrics["selected"]
                    assert metrics["button"]["left"] >= -1 and metrics["button"]["right"] <= width + 1, (width, metrics)
                    assert metrics["text"]["display"] == "none" or metrics["text"]["bottom"] <= metrics["button"]["bottom"] + 1, (width, metrics)
                    evidence["widths"].append(metrics)
                assert not evidence["page_errors"], evidence
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
