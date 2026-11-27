"""Current-candidate browser checks for mobile feedback widget collisions."""
import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v24"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id115-") as tmp:
        temp = Path(tmp)
        source = temp / "organize-mobile.pdf"
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((72, 72), "MOBILE ORGANIZE THUMBNAIL CHECK")
            document.save(source)
        app, base, _ = helper.start_server(temp / "data")
        try:
            parsed = urlparse(base)
            for _ in range(150):
                try:
                    with socket.create_connection((parsed.hostname, parsed.port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError(f"Local server did not start at {base}")
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/", wait_until="domcontentloaded")
                page.wait_for_selector("#pp-feedback-launcher", state="attached", timeout=20000)
                page.evaluate("document.querySelector('#pp-feedback-launcher').hidden = false")
                page.wait_for_timeout(200)
                launcher = page.locator("#pp-feedback-launcher")
                visible_before = launcher.evaluate("e => getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden'")
                rect = launcher.bounding_box()
                # Confirm active application modals suppress both launcher and popover.
                checks = []
                for modal_id, open_action in [("auth-modal", "auth"), ("upgrade-modal", "upgrade")]:
                    if open_action == "auth":
                        await_auth = page.locator("#login-btn")
                        if await_auth.count() == 0:
                            await_auth = page.locator("#mobile-login-btn")
                        if await_auth.count() == 0:
                            page.evaluate("document.querySelector('#auth-modal').hidden = false")
                        else:
                            await_auth.first.click()
                    else:
                        page.evaluate("document.querySelector('#upgrade-modal').hidden = false")
                    page.wait_for_timeout(150)
                    modal_hidden = page.locator("#pp-feedback-container").evaluate("e => getComputedStyle(e).display === 'none'")
                    checks.append({"modal": modal_id, "widget_container_hidden": modal_hidden})
                    page.evaluate(f"document.querySelector('#{modal_id}').hidden = true")
                # Studio mobile controls must not be covered by a visible launcher.
                page.goto(base + "/studio", wait_until="domcontentloaded")
                page.wait_for_timeout(300)
                page.locator("#studio-file-input").set_input_files(str(source))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '1' && document.querySelector('#studio-loading-overlay')?.hidden === true", timeout=20000)
                page.wait_for_selector(".organizer-thumb-card", state="attached", timeout=15000)
                page.evaluate("document.querySelector('#pp-feedback-launcher').hidden = false")
                page.wait_for_timeout(150)
                page.locator("#btn-mode-organize").click()
                page.wait_for_timeout(200)
                organize_drawer = page.evaluate("""() => {
                  const shell = document.querySelector('#app-shell');
                  const panel = document.querySelector('#studio-thumbnails-bar');
                  const rect = panel.getBoundingClientRect();
                  return {open: shell.classList.contains('studio-pages-open'), visible: rect.width > 0 && rect.height > 0 && getComputedStyle(panel).display !== 'none', thumbnail_count: document.querySelectorAll('.organizer-thumb-card').length, box: {x:rect.x,y:rect.y,width:rect.width,height:rect.height}};
                }""")
                overlap = page.evaluate("""() => {
                  const a = document.querySelector('#pp-feedback-launcher').getBoundingClientRect();
                  const selectors = ['#zoom-in-btn', '#zoom-out-btn', '#page-prev-btn', '#page-next-btn'];
                  return selectors.map(selector => {
                    const e = document.querySelector(selector);
                    if (!e || getComputedStyle(e).display === 'none') return {selector, visible:false, overlap:false};
                    const b = e.getBoundingClientRect();
                    return {selector, visible:true, overlap:a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top};
                  });
                }""")
                result = {
                    "viewport": {"width": 390, "height": 844},
                    "launcher_visible_on_home": visible_before,
                    "launcher_box": rect,
                    "modal_checks": checks,
                    "organize_mode_opens_mobile_pages_drawer": organize_drawer,
                    "studio_control_overlap": overlap,
                    "page_errors": errors,
                    "result": "passed" if visible_before and all(c["widget_container_hidden"] for c in checks) and organize_drawer["open"] and organize_drawer["visible"] and organize_drawer["thumbnail_count"] >= 1 and not any(x["overlap"] for x in overlap) and not errors else "failed",
                }
                (OUT / "browser-id115-mobile-feedback.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                print(json.dumps(result, indent=2))
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
