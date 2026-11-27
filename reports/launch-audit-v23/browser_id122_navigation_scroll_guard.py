"""Check Studio navigation clears real scroll offsets and skips no-op scroll calls."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

rounds = []
with TemporaryDirectory(prefix="paperplane-id122-scroll-guard-") as temporary:
    app, base, _ = helper.start_server(Path(temporary) / "data")
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local Paperplane app failed to start")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_number in (1, 2):
                page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(f"{base}/studio", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.wait_for_function("typeof window.switchWorkspaceView === 'function'")
                result = page.evaluate("""() => {
                  const area=document.querySelector('.main-area');
                  const originalWindowScroll=window.scrollTo.bind(window);
                  const counts={main:0,window:0};
                  area.style.setProperty('height','180px','important');
                  area.style.setProperty('max-height','180px','important');
                  area.style.setProperty('overflow','auto','important');
                  const spacer=document.createElement('div');
                  spacer.style.setProperty('height','1200px','important');
                  spacer.style.setProperty('min-height','1200px','important');
                  spacer.style.setProperty('display','block','important');
                  area.appendChild(spacer);
                  document.body.style.minHeight='2200px'; document.documentElement.style.overflowY='auto';
                  area.scrollTop=420; window.scrollTo(0,260);
                  const before={main:area.scrollTop,window:window.scrollY};
                  const originalMainScroll=area.scrollTo.bind(area);
                  area.scrollTo=(...args)=>{counts.main++;return originalMainScroll(...args)};
                  window.scrollTo=(...args)=>{counts.window++;return originalWindowScroll(...args)};
                  switchWorkspaceView('tool-desk','',false);
                  const afterScrolled={main:area.scrollTop,window:window.scrollY};
                  counts.main=0; counts.window=0;
                  switchWorkspaceView('studio','',false);
                  const afterTop={main:area.scrollTop,window:window.scrollY};
                  const noOpCalls={...counts};
                  return {before,afterScrolled,afterTop,noOpCalls};
                }""")
                assert result["before"]["main"] > 0, result
                assert result["afterScrolled"]["main"] == 0 and result["afterScrolled"]["window"] == 0, result
                assert result["afterTop"]["main"] == 0 and result["afterTop"]["window"] == 0, result
                assert result["noOpCalls"] == {"main": 0, "window": 0}, result
                assert not errors, errors
                rounds.append({"round": round_number, **result, "page_errors": errors})
                page.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=10)

report = {"base": base, "rounds": rounds}
(OUT / "browser-id122-navigation-scroll-guard.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
