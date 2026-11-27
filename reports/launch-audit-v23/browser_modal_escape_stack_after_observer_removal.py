"""Ensure Escape still dismisses visible overlays topmost-first after removing the DOM-wide observer."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

rounds = []
with TemporaryDirectory(prefix="paperplane-overlay-escape-") as temporary:
    app, base, _ = helper.start_server(Path(temporary) / "data")
    try:
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        else:
            raise RuntimeError("Local app failed to start")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.evaluate("""() => {
                  document.querySelector('#settings-modal').hidden = false;
                  document.querySelector('#auth-modal').hidden = false;
                }""")
                visible = page.evaluate("""() => [...document.querySelectorAll(
                  '.modal-backdrop:not([hidden]), dialog[open], #sidebar.mobile-open, .studio-mobile-properties-panel:not([hidden])'
                )].filter(element => {
                  const style=getComputedStyle(element);
                  return style.display !== 'none' && style.visibility !== 'hidden';
                }).map((element,domOrder)=>({id:element.id,domOrder,zIndex:Number.parseInt(getComputedStyle(element).zIndex,10)||0}))
                  .sort((a,b)=>a.zIndex-b.zIndex||a.domOrder-b.domOrder).map(element=>element.id)""")
                assert "settings-modal" in visible and "auth-modal" in visible, visible
                topmost, remaining = visible[-1], visible[-2]
                page.keyboard.press("Escape")
                page.wait_for_function("id => document.getElementById(id)?.hidden === true", arg=topmost)
                assert page.locator(f"#{remaining}").is_visible(), {"topmost": topmost, "visible": visible}
                page.keyboard.press("Escape")
                page.wait_for_function("id => document.getElementById(id)?.hidden === true", arg=remaining)
                assert not errors, errors
                rounds.append({"round": round_no, "overlay_order": visible, "closed_first": topmost,
                               "closed_second": remaining, "page_errors": errors})
                context.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=10)

evidence = {"rounds": rounds, "verdict": "PASS"}
(OUT / "browser-id122-overlay-escape-stack-v133.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps(evidence, indent=2))
