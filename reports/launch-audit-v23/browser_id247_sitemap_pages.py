from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from urllib.parse import urlparse
from xml.etree import ElementTree
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

LANDINGS = {"/compress-pdf-to-100kb", "/compress-pdf-to-200kb", "/convert-pdf", "/pdf-security"}
CHECKS = ("/compress-pdf-to-100kb", "/compress-pdf-to-200kb", "/convert-pdf", "/pdf-security",
          "/download", "/apps", "/privacy", "/terms", "/developers", "/reset-password")

with TemporaryDirectory(prefix="paperplane-id247-sitemap-") as temp:
    app, base, _identity = helper.start_server(Path(temp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            sitemap_response = page.request.get(base + "/sitemap.xml")
            assert sitemap_response.status == 200
            root = ElementTree.fromstring(sitemap_response.body())
            paths = {urlparse(node.text).path for node in root.findall(".//{*}loc") if node.text}
            landings_in_sitemap = sorted(paths & LANDINGS)
            for round_no in (1, 2):
                page.set_viewport_size({"width": 1366, "height": 900} if round_no == 1 else {"width": 390, "height": 844})
                for path in CHECKS:
                    response = page.goto(base + path, wait_until="domcontentloaded")
                    assert response and response.status == 200, (path, response.status if response else None)
                    visible_h1 = page.locator("h1:visible").all_inner_texts()
                    visible_h1 = [text.strip() for text in visible_h1 if text.strip()]
                    assert len(visible_h1) == 1, (path, visible_h1)
                    assert visible_h1[0].lower() != "tool desk", (path, visible_h1)
                    body = page.locator("body").inner_text()
                    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                    assert not overflow, (path, "horizontal overflow", page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]"))
                    if path == "/reset-password":
                        assert page.locator("#reset-password-modal").is_visible()
                        assert page.locator("#reset-password-modal input[type=password]").count() >= 1
                        assert page.get_by_role("dialog", name="Reset Account Password").is_visible()
                    results.append({"round": round_no, "path": path, "status": response.status,
                                    "viewport": "desktop" if round_no == 1 else "mobile",
                                    "h1": visible_h1[0], "horizontal_overflow": overflow,
                                    "reset_modal_visible": page.locator("#reset-password-modal").is_visible() if path == "/reset-password" else None,
                                    "body_chars": len(body)})
                if round_no == 1:
                    download_text = page.request.get(base + "/download").text()
                    apps_text = page.request.get(base + "/apps").text()
                    assert download_text != apps_text
                    results.append({"round": round_no, "download_apps_identical_html": download_text == apps_text,
                                    "both_in_sitemap": "/download" in paths and "/apps" in paths,
                                    "sitemap_path_count": len(paths)})
                    page.goto(base + "/privacy", wait_until="domcontentloaded")
                    page.get_by_role("button", name="Terms of Service").click()
                    assert page.locator("#legal-page-title").inner_text() == "Terms of Service"
                    results.append({"round": round_no, "legal_tab_heading_updates": True})
                page.goto(base + "/reset-password", wait_until="domcontentloaded")
                assert page.locator("#reset-password-modal").is_visible()
                page.screenshot(path=str(OUT / f"id247-reset-password-no-token-round{round_no}.png"))
                page.locator("#close-reset-modal").click()
                assert not page.locator("#reset-password-modal").is_visible()
                assert page.locator("h1:visible").inner_text().strip() == "Tool Desk"
                results.append({"round": round_no, "reset_modal_close_returns_to_workspace": True})
            assert not errors, errors
            browser.close()
        result = {"implemented_landing_paths_in_sitemap": landings_in_sitemap, "sitemap_path_count": len(paths),
                  "paths_checked": list(CHECKS), "rounds": results, "browser_errors": errors}
        (OUT / "browser-id247-sitemap-pages.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
