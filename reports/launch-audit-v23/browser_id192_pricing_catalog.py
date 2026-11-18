from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

with TemporaryDirectory(prefix="paperplane-id192-") as temp_dir:
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

        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_number in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                assert response.status == 200
                page.wait_for_timeout(400)
                nav_copy = page.locator("#sidebar-upgrade-btn, #topbar-upgrade-btn").evaluate_all(
                    "els => els.filter(el => getComputedStyle(el).display !== 'none').map(el => el.textContent.trim())"
                )
                page.locator("#sidebar-upgrade-btn").click()
                page.locator("#upgrade-modal").wait_for(state="visible")
                modal = page.locator("#upgrade-modal").inner_text()
                catalog = page.evaluate("""async () => {
                  const response = await fetch('/api/billing/status', {credentials:'same-origin'});
                  return {status:response.status, body:await response.json()};
                }""")
                assert catalog["status"] == 200
                prices = {item["tier"]: item["price"] for item in
                          page.locator("#upgrade-modal .pricing-tier-card").evaluate_all("""cards => cards.map(card => ({
                            tier:card.dataset.planTier,
                            price:card.querySelector('.tier-price-val')?.textContent.trim()
                          }))""")}
                public_catalog = catalog["body"]["pricing"]
                expected = {tier: f"₹{data['inr']}" for tier, data in public_catalog.items()}
                assert prices == expected, {"ui": prices, "api": expected}
                combined = " ".join(nav_copy) + " " + modal
                for obsolete in ("Pro Power User", "Rs 250/mo", "₹250", "Rs 750/mo", "₹750"):
                    assert obsolete not in combined, obsolete
                assert set(public_catalog) == {"free", "exam_pass", "student_pro", "cyber_cafe"}
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id192-pricing-round{round_number}.png"))
                rounds.append({"round": round_number, "status": response.status, "navigation_copy": nav_copy,
                               "api_catalog": public_catalog, "modal_prices": prices,
                               "prices_match_api": True, "obsolete_claims_found": [], "page_errors": errors})
                context.close()
            browser.close()
        evidence = {"rounds": rounds}
        (OUT / "browser-id192-pricing-catalog.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
