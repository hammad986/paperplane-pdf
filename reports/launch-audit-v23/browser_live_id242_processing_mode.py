import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://paperplane.qd.je"
OUT = Path(__file__).resolve().parent
ROUTES = ["merge-pdf", "split-pdf", "remove-pages-pdf", "rotate-pdf"]

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    rounds = []
    for round_no in (1, 2):
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        routes = []
        for slug in ROUTES:
            response = page.goto(f"{BASE}/{slug}", wait_until="domcontentloaded", timeout=45000)
            page.locator("#client-privacy-toggle").wait_for(state="attached", timeout=30000)
            control = page.locator("#client-privacy-toggle")
            routes.append({
                "slug": slug,
                "http_status": response.status if response else None,
                "checked_on_fresh_context": control.is_checked(),
                "label": control.get_attribute("aria-label"),
                "mode_text": page.locator("#processing-mode-label").inner_text() if page.locator("#processing-mode-label").count() else None,
                "help_text": page.locator("#processing-mode-description").inner_text() if page.locator("#processing-mode-description").count() else None,
                "stored_mode": page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')"),
            })
            assert response and response.status == 200
        # Toggle one route to server mode; verify reload and cross-route state.
        page.goto(f"{BASE}/merge-pdf", wait_until="domcontentloaded")
        toggle = page.locator("#client-privacy-toggle")
        if toggle.is_checked():
            toggle.evaluate("el => el.click()")
        toggle.wait_for(state="attached")
        page.wait_for_function("localStorage.getItem('paperplane-pdf-processing-mode') === 'server'")
        page.reload(wait_until="domcontentloaded")
        page.locator("#client-privacy-toggle").wait_for(state="attached")
        reload_server = not page.locator("#client-privacy-toggle").is_checked()
        page.goto(f"{BASE}/rotate-pdf", wait_until="domcontentloaded")
        page.locator("#client-privacy-toggle").wait_for(state="attached")
        cross_route_server = not page.locator("#client-privacy-toggle").is_checked()
        assert reload_server and cross_route_server
        assert not errors, errors
        rounds.append({"round": round_no, "fresh_routes": routes,
                       "server_choice_survives_reload": reload_server,
                       "server_choice_survives_route_change": cross_route_server,
                       "page_errors": errors})
        context.close()
    browser.close()

result = {"base": BASE, "rounds": rounds}
(OUT / "browser-live-id242-processing-mode.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
