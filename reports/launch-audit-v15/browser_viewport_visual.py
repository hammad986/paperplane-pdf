"""Capture local route screenshots at the disputed widths for visual review."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import socket
import time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("viewport_helpers", HELPER)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)

def main() -> None:
    out = ROOT / "reports" / "launch-audit-v15" / "viewport-screenshots"
    out.mkdir(exist_ok=True)
    with helpers.TemporaryDirectory(prefix="paperplane-viewport-") as temp:
        app, base, _ = helpers.start_server(Path(temp))
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2): break
                except OSError:
                    if app.poll() is not None: raise RuntimeError("Local app exited")
                    time.sleep(0.1)
            else: raise RuntimeError("Local app did not become ready")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                for width in (390, 820, 1024, 1104):
                    page = browser.new_page(viewport={"width": width, "height": 844}, device_scale_factor=1)
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                    page.locator("#tool-title").wait_for(state="visible")
                    page.wait_for_timeout(1000)
                    page.screenshot(path=str(out / f"merge-{width}.png"), full_page=True)
                    state = page.evaluate("""() => ({
                      width: innerWidth, height: innerHeight,
                      sidebarDisplay: getComputedStyle(document.querySelector('#sidebar')).display,
                      sidebarRect: (() => {const r=document.querySelector('#sidebar').getBoundingClientRect();return [r.x,r.width,r.right]})(),
                      mobileBrandDisplay: getComputedStyle(document.querySelector('.mobile-brand')).display,
                      menuDisplay: getComputedStyle(document.querySelector('#mobile-menu-btn')).display,
                      topbarRightDisplay: getComputedStyle(document.querySelector('.topbar-right')).display,
                      workspaceTabsDisplay: getComputedStyle(document.querySelector('.workspace-tabs')).display,
                      pillPosition: getComputedStyle(document.querySelector('.workspace-tabs')).position,
                      overflow: document.documentElement.scrollWidth > innerWidth
                    })""")
                    print({"width": width, "state": state, "page_errors": errors})
                    page.close()
                browser.close()
        finally:
            app.terminate(); app.wait(timeout=10)

if __name__ == "__main__": main()
