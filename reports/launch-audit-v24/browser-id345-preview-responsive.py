from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    evidence: dict = {"checks": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-id345-responsive-") as temp:
        app, base, _ = helper.start_server(Path(temp) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
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
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                for width in (320, 390, 768, 1366):
                    awaitable = page.set_viewport_size({"width": width, "height": 844})
                    for slug, expected in (("watermark-pdf", "is-watermark"),
                                           ("add-page-numbers-to-pdf", "footer-center"),
                                           ("sign-pdf", "is-signature")):
                        response = page.goto(f"{base}/{slug}", wait_until="domcontentloaded")
                        assert response and response.status == 200
                        mark = page.locator("#mark_preview .mark-preview-mark")
                        mark.wait_for(state="visible")
                        checks = page.evaluate("""() => {
                          const preview=document.querySelector('#mark_preview');
                          const paper=preview?.querySelector('.mark-preview-page');
                          const mark=preview?.querySelector('.mark-preview-mark');
                          const caption=preview?.querySelector('.mark-preview-caption');
                          const rect=(x)=>{const r=x.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}};
                          const p=rect(paper),m=rect(mark),c=rect(caption),v=document.documentElement.clientWidth;
                          return {viewport:v, page:p, mark:m, caption:c, rootScrollWidth:document.documentElement.scrollWidth,
                            markInsidePage:m.left>=p.left-1&&m.right<=p.right+1&&m.top>=p.top-1&&m.bottom<=p.bottom+1,
                            previewFitsViewport:rect(preview).right<=v+1,captionFitsViewport:c.right<=v+1,
                            className:mark.className,background:preview.dataset.pageBackground};
                        }""")
                        assert expected in checks["className"], checks
                        assert checks["markInsidePage"] and checks["previewFitsViewport"] and checks["captionFitsViewport"], checks
                        assert checks["rootScrollWidth"] <= width + 1, checks
                        evidence["checks"].append({"width": width, "route": slug, **checks})
                        if width == 390 and slug == "add-page-numbers-to-pdf":
                            page.locator("#position").select_option("Header right")
                            assert "header-right" in mark.get_attribute("class")
                            evidence["checks"][-1]["selected_position"] = mark.get_attribute("class")
                    if width == 390:
                        page.goto(f"{base}/watermark-pdf", wait_until="domcontentloaded")
                        page.locator("#text").fill("REVIEW COPY")
                        assert page.locator("#mark_preview .mark-preview-mark").inner_text() == "REVIEW COPY"
                        page.locator("#mark_preview").scroll_into_view_if_needed()
                        preview_box = page.locator("#mark_preview").bounding_box()
                        nav_box = page.locator(".mobile-workspace-bar").bounding_box()
                        assert preview_box and nav_box and preview_box["y"] + preview_box["height"] <= nav_box["y"]
                        page.screenshot(path=str(ROOT / "reports" / "launch-audit-v24" / "browser-id345-preview-mobile.png"), full_page=False)
                browser.close()
        finally:
            app.terminate()
    evidence["passed"] = (len(evidence["checks"]) == 12 and not evidence["page_errors"] and not evidence["console_errors"])
    out = ROOT / "reports" / "launch-audit-v24" / "browser-id345-preview-responsive.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
