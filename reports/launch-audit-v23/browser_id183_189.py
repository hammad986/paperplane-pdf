from pathlib import Path
from tempfile import TemporaryDirectory
import ast, json, socket, sys, time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

slugs = next(
    ast.literal_eval(node.value)
    for node in ast.parse((ROOT / "server.py").read_text(encoding="utf-8")).body
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == "OPERATION_SLUGS" for target in node.targets)
)

with TemporaryDirectory(prefix="paperplane-id183-189-") as temp_dir:
    app, base, _ = harness.start_server(Path(temp_dir) / "db")
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.15)
        else:
            raise RuntimeError("Local Paperplane server did not start")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            errors = []
            results = {"id183": [], "id189": []}
            for round_number in (1, 2):
                context = browser.new_context(viewport={"width": 390, "height": 844})
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))

                response = page.goto(base + "/", wait_until="domcontentloaded")
                assert response.status == 200
                footer = page.locator(".app-global-footer")
                footer_text = footer.evaluate("el => el.textContent")
                footer_links = footer.locator("a").evaluate_all(
                    "els => els.map(el => ({text:el.textContent.trim(), href:el.getAttribute('href')}))"
                )
                home_text = page.locator("body").evaluate("el => el.textContent")
                assert "© 2026 Paperplane PDF" in footer_text
                assert all(any(link["text"].casefold() in item["text"].casefold() for item in footer_links)
                           for link in ({"text": "Tool Desk"}, {"text": "Pricing"}, {"text": "FAQ"}, {"text": "Dashboard"}))
                assert "100% Private Browser Processing" not in home_text

                privacy_claim = page.locator("body").evaluate("el => el.textContent")
                assert "when Local Processing is selected" in privacy_claim
                assert "100% locally" not in privacy_claim
                results["id183"].append({
                    "round": round_number,
                    "status": response.status,
                    "viewport": 390,
                    "footer_links": footer_links,
                    "privacy_claim": next(line.strip() for line in privacy_claim.splitlines()
                                           if "Browser processing for supported tools" in line),
                    "stale_absolute_privacy_claim": "100% Private Browser Processing" in home_text,
                })
                page.screenshot(path=str(OUT / f"id183-home-390-round{round_number}.png"))

                for width in (820, 1024):
                    page.set_viewport_size({"width": width, "height": 900})
                    for slug in slugs.values():
                        response = page.goto(base + "/" + slug, wait_until="domcontentloaded", timeout=15000)
                        assert response.status == 200, (width, slug, response.status)
                        page.wait_for_timeout(20)
                        measured = page.evaluate("""() => {
                          const visible = element => {
                            if (!element) return false;
                            const rect = element.getBoundingClientRect();
                            const style = getComputedStyle(element);
                            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                          };
                          const topbar = document.querySelector('.topbar');
                          const mobileBar = document.querySelector('.mobile-workspace-bar');
                          const sidebar = document.querySelector('.sidebar');
                          const toggle = document.querySelector('.mobile-menu-btn');
                          const rect = element => { const r = element.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; };
                          return {viewport:innerWidth, documentWidth:document.documentElement.scrollWidth,
                            topbarVisible:visible(topbar), topbar:rect(topbar), mobileBarVisible:visible(mobileBar), mobileBar:rect(mobileBar),
                            mobileToggleVisible:visible(toggle), sidebar:rect(sidebar), sidebarInsideViewport:rect(sidebar).x + rect(sidebar).width > 0 && rect(sidebar).x < innerWidth};
                        }""")
                        assert measured["documentWidth"] <= width + 2, (width, slug, measured)
                        assert measured["topbarVisible"] and measured["mobileToggleVisible"] == (width <= 900), (width, slug, measured)
                        assert measured["mobileBarVisible"] == (width <= 900), (width, slug, measured)
                        assert measured["sidebarInsideViewport"] == (width > 900), (width, slug, measured)
                        results["id189"].append({"round": round_number, "width": width, "route": slug, **measured})
                    if slug == "tool-desk":
                        page.screenshot(path=str(OUT / f"id189-tool-desk-{width}-round{round_number}.png"))

                context.close()

            assert not errors, errors
            payload = {"id183": results["id183"], "id189_route_views": len(results["id189"]),
                       "id189": results["id189"], "page_errors": errors}
            (OUT / "browser-id183-189.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(json.dumps({"id183_rounds": len(results["id183"]), "id189_route_views": len(results["id189"]),
                              "widths": [390, 820, 1024], "page_errors": errors}, indent=2))
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=5)
