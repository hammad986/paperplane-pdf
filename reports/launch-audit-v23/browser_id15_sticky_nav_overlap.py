"""Inspect ID 15 at the exact 1104px viewport over scroll positions and queued tool files."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FIXTURE = OUT / "fixtures" / "totpdf-sample-5-pages.pdf"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix="paperplane-id15-") as temp:
    app, base, identities = helper.start_server(Path(temp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            if app.poll() is not None:
                raise RuntimeError(f"app exited during startup with code {app.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.15)
        results = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                context = browser.new_context(viewport={"width": 1104, "height": 760})
                context.add_cookies([{"name": "paperplane_token", "value": identities["accounts"][0][1], "url": base, "httpOnly": True}])
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                routes = []
                for route in ("/ocr-pdf", "/remove-pages-pdf"):
                    response = page.goto(base + route, wait_until="domcontentloaded")
                    assert response and response.status == 200, route
                    page.locator("#tool-title").wait_for(state="visible", timeout=10000)
                    if route == "/remove-pages-pdf" and page.locator("#file-input").is_enabled():
                        page.locator("#file-input").set_input_files(str(FIXTURE))
                        page.locator("#file-list .file-row-name").wait_for(state="visible", timeout=10000)
                    samples = []
                    for scroll_y in (0, 120, 240, 360, 480, 600):
                        page.evaluate("y => document.querySelector('.main-area').scrollTo(0,y)", scroll_y)
                        page.wait_for_timeout(80)
                        samples.append(page.evaluate("""() => {
                          const rect = selector => {const e=document.querySelector(selector); if(!e)return null; const r=e.getBoundingClientRect(); return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,visible:r.bottom>0&&r.top<innerHeight};};
                          const targets=['#tool-title','#dropzone h3','#file-list .file-row-name'];
                          const top=document.querySelector('.topbar')?.getBoundingClientRect();
                          const pill=document.querySelector('#mobile-view-pill')?.getBoundingClientRect();
                          const feedback=document.querySelector('#pp-feedback-launcher');
                          const feedbackRect=feedback?.getBoundingClientRect();
                          const feedbackStyle=feedback?getComputedStyle(feedback):null;
                          const intersects=(a,b)=>Boolean(a&&b&&a.bottom>0&&a.top<innerHeight&&a.top<b.bottom&&a.bottom>b.top&&a.left<b.right&&a.right>b.left);
                          const feedbackOverlaps=Array.from(document.querySelectorAll('.main-area h1, .main-area h2, .main-area h3, #file-list .file-row-card, .home-tool-title, .home-tool-desc')).some(e=>{const s=getComputedStyle(e);return s.display!=='none'&&s.visibility!=='hidden'&&intersects(e.getBoundingClientRect(),feedbackRect);});
                          return {mainScroll:document.querySelector('.main-area').scrollTop,topbar:top?{top:top.top,bottom:top.bottom}:null,mobilePill:pill?{top:pill.top,bottom:pill.bottom}:null,targets:Object.fromEntries(targets.map(s=>[s,rect(s)])),feedbackLauncher:{rect:feedbackRect?{top:feedbackRect.top,bottom:feedbackRect.bottom,left:feedbackRect.left,right:feedbackRect.right}:null,visible:Boolean(feedbackStyle&&feedbackStyle.visibility!=='hidden'&&feedbackStyle.display!=='none'),ariaHidden:feedback?.getAttribute('aria-hidden'),inert:Boolean(feedback?.inert),overlapsProtectedContent:feedbackOverlaps}};
                        }"""))
                    screenshot = OUT / f"id15-round{round_no}-{route.strip('/').replace('/', '-')}.png"
                    page.evaluate("document.querySelector('.main-area').scrollTo(0,360)")
                    page.wait_for_timeout(120)
                    page.screenshot(path=str(screenshot), full_page=False)
                    routes.append({"route": route, "status": response.status, "samples": samples, "screenshot": screenshot.name})
                home = page.goto(base + "/tool-desk", wait_until="domcontentloaded")
                assert home and home.status == 200
                grayscale = page.locator('#tool-desk-tools-catalog [data-select-operation="grayscale"] .home-tool-desc')
                grayscale.wait_for(state="visible", timeout=10000)
                grayscale_metrics = grayscale.evaluate("""e => {const s=getComputedStyle(e),r=e.getBoundingClientRect();return {text:e.innerText,clientHeight:e.clientHeight,scrollHeight:e.scrollHeight,overflowY:s.overflowY,display:s.display,lineClamp:s.webkitLineClamp,top:r.top,bottom:r.bottom,width:r.width};}""")
                page.evaluate("document.querySelector('.main-area').scrollTo(0, 360)")
                page.screenshot(path=str(OUT / f"id15-round{round_no}-grayscale-card.png"), full_page=False)
                routes.append({"route": "/tool-desk#grayscale-card", "status": home.status, "description": grayscale_metrics})
                assert not errors, errors
                for route_check in routes:
                    for sample in route_check.get("samples", []):
                        launcher = sample.get("feedbackLauncher")
                        if launcher and launcher["overlapsProtectedContent"]:
                            assert launcher["ariaHidden"] == "true" and launcher["inert"], (route_check["route"], sample)
                results.append({"round": round_no, "routes": routes, "page_errors": errors})
                context.close()
            mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True)
            mobile.add_cookies([{"name": "paperplane_token", "value": identities["accounts"][0][1], "url": base, "httpOnly": True}])
            mobile_page = mobile.new_page()
            mobile_errors = []
            mobile_page.on("pageerror", lambda error: mobile_errors.append(str(error)))
            mobile_response = mobile_page.goto(base + "/remove-pages-pdf", wait_until="domcontentloaded")
            assert mobile_response and mobile_response.status == 200
            mobile_page.locator("#file-input").set_input_files(str(FIXTURE))
            mobile_page.locator("#file-list .file-row-name").wait_for(state="visible", timeout=10000)
            mobile_samples = []
            for scroll_y in (0, 180, 360, 540, 720):
                mobile_page.evaluate("y => window.scrollTo(0,y)", scroll_y)
                mobile_page.wait_for_timeout(250)
                mobile_samples.append(mobile_page.evaluate("""() => {
                  const launcher=document.querySelector('#pp-feedback-launcher'),r=launcher?.getBoundingClientRect();
                  const inter=(a,b)=>Boolean(a&&b&&a.bottom>0&&a.top<innerHeight&&a.top<b.bottom&&a.bottom>b.top&&a.left<b.right&&a.right>b.left);
                  const targets=document.querySelectorAll('.main-area h1,.main-area h2,.main-area h3,#file-list .file-row-card,.home-tool-title,.home-tool-desc');
                  const overlap=[...targets].some(e=>{const s=getComputedStyle(e);return s.display!=='none'&&s.visibility!=='hidden'&&inter(e.getBoundingClientRect(),r)});
                  return {scrollY,feedbackVisible:Boolean(launcher&&getComputedStyle(launcher).visibility!=='hidden'&&getComputedStyle(launcher).display!=='none'),ariaHidden:launcher?.getAttribute('aria-hidden'),inert:Boolean(launcher?.inert),overlapsProtectedContent:overlap};
                }"""))
            for sample in mobile_samples:
                if sample["overlapsProtectedContent"]:
                    assert sample["ariaHidden"] == "true" and sample["inert"], sample
            assert not mobile_errors, mobile_errors
            results.append({"round": 3, "viewport": "390x844 touch", "routes": [{"route": "/remove-pages-pdf", "status": mobile_response.status, "samples": mobile_samples}], "page_errors": mobile_errors})
            mobile.close()
            browser.close()
        (OUT / "browser-id15-sticky-nav-overlap.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        if sys.platform == "win32" and app.poll() is None:
            subprocess.run(["taskkill", "/PID", str(app.pid), "/T", "/F"], capture_output=True, text=True)
        if app.poll() is None:
            app.terminate()
        app.wait(timeout=5)
