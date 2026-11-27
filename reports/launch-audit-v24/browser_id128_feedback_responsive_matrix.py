"""Sweep the signed-in feedback launcher across phone, tablet, and desktop sizes."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id128-feedback-responsive-matrix.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    dimensions = [(320, 568), (360, 640), (390, 844), (768, 900), (820, 900), (1024, 768), (1366, 900)]
    with TemporaryDirectory(prefix="paperplane-id128-responsive-") as temp_name:
        app, base, _ = helper.start_server(Path(temp_name) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            evidence = {"dimensions": dimensions, "checks": [], "page_errors": [], "console_errors": []}
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
                page.goto(base + "/", wait_until="domcontentloaded")
                page.locator("#pp-feedback-launcher").wait_for(state="attached")
                page.wait_for_timeout(300)
                page.evaluate("document.dispatchEvent(new CustomEvent('paperplane:auth-changed', {detail:{userId:'synthetic-id128-responsive-user'}}))")
                page.wait_for_function("document.querySelector('#pp-feedback-launcher')?.hidden === false")
                for width, height in dimensions:
                    page.set_viewport_size({"width": width, "height": height})
                    page.wait_for_timeout(120)
                    item = page.evaluate("""() => {
                      const launcher=document.querySelector('#pp-feedback-launcher'), a=launcher.getBoundingClientRect();
                      const colliding=[...document.querySelectorAll('.main-area h1,.main-area h2,.main-area h3,#file-list .file-row-card,.home-tool-title,.home-tool-desc')].filter(e=>{
                        const s=getComputedStyle(e),b=e.getBoundingClientRect();
                        return s.display!=='none'&&s.visibility!=='hidden'&&b.width>0&&b.height>0&&b.bottom>0&&b.top<innerHeight&&b.left<a.right&&b.right>a.left&&b.top<a.bottom&&b.bottom>a.top;
                      }).map(e=>(e.innerText||e.tagName).slice(0,80));
                      return {visible:!launcher.hidden&&getComputedStyle(launcher).visibility==='visible',rect:{x:a.x,y:a.y,width:a.width,height:a.height},viewport:{width:innerWidth,height:innerHeight},verticalOffset:getComputedStyle(launcher).getPropertyValue('--pp-feedback-offset-y').trim(),colliding};
                    }""")
                    item["result"] = "passed" if item["visible"] and item["rect"]["x"] >= 0 and item["rect"]["y"] >= 0 and item["rect"]["x"] + item["rect"]["width"] <= width and item["rect"]["y"] + item["rect"]["height"] <= height and not item["colliding"] else "failed"
                    evidence["checks"].append(item)
                browser.close()
            evidence["result"] = "passed" if all(item["result"] == "passed" for item in evidence["checks"]) and not evidence["page_errors"] and not evidence["console_errors"] else "failed"
            OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if evidence["result"] != "passed":
                raise SystemExit(1)
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
