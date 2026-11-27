from pathlib import Path
from tempfile import TemporaryDirectory
import json, os, secrets, socket, subprocess, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"

with TemporaryDirectory(prefix="paperplane-id107-revenue-") as tmp:
    data_dir = Path(tmp) / "data"
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = candidate.getsockname()[1]
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_", "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_")) and k not in {"TESTING", "SESSION_SECRET_KEY"}}
    env.update({"PAPERPLANE_SKIP_DOTENV": "1", "PAPERPLANE_ENV": "development", "PAPERPLANE_DATA_DIR": str(data_dir), "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(64), "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(30), "PAPERPLANE_PORT": str(port), "PAPERPLANE_SECURE_COOKIES": "false", "PYTHONPATH": str(ROOT), "TESTING": "True"})
    seed = r'''import json,secrets
from persistence import init_db,create_admin_session,create_user,set_user_tier,record_billing_event
from server import ADMIN_OWNER_EMAILS
init_db()
owner=sorted(ADMIN_OWNER_EMAILS)[0]
def add(tag, amount, source=None, active=False):
 uid=create_user(f"{tag}@example.test",secrets.token_urlsafe(20))
 if active: set_user_tier(uid,tier="pro",status="active",cashfree_order_id=f"order-{tag}")
 if source: record_billing_event(f"order-{tag}","cashfree.order_created",uid,{"tier":"pro","gateway_environment":source})
 record_billing_event(f"verified-{tag}","cashfree.order_verified",uid,{"gateway_environment":source,"order":{"order_id":f"order-{tag}","order_amount":amount,"order_currency":"INR","order_status":"PAID"}})
add("prod",299,"PROD",True)
add("test",3750,"TEST")
add("unknown",125,None)
print(json.dumps({"admin":create_admin_session(owner)}))'''
    seeded = subprocess.run([sys.executable, "-c", seed], cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    admin_token = json.loads(seeded.stdout)["admin"]
    app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no, width in enumerate((1440, 390, 320), start=1):
                page = browser.new_page(viewport={"width": width, "height": 1000})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                def tamper_revenue(route):
                    response = route.fetch()
                    body = response.json()
                    body["recent_transactions"].append({
                        "email": "injected@example.test", "tier": "pro", "order_id": "xss-probe",
                        "amount": '0<img id="pp-admin-amount-xss" src="x" onerror="window.__adminXss++">',
                        "gateway_environment": "UNKNOWN", "created_at": 1, "status": "Paid",
                    })
                    route.fulfill(response=response, json=body)
                page.route("**/api/admin/revenue", tamper_revenue)
                page.add_init_script("window.__adminXss = 0")
                page.add_init_script("sessionStorage.setItem('pp_admin_session'," + json.dumps(admin_token) + ")")
                page.goto(f"http://127.0.0.1:{port}/admin", wait_until="domcontentloaded")
                page.locator("#tab-revenue-btn").wait_for(state="visible")
                page.locator("#tab-revenue-btn").click()
                page.wait_for_function("document.querySelector('#rev-gross-revenue')?.textContent.trim() !== '-'", timeout=15000)
                gross = page.locator("#rev-gross-revenue").inner_text().strip()
                basis = page.locator("#rev-revenue-basis").inner_text().strip()
                headers = page.locator("#panel-revenue thead").inner_text()
                rows = page.locator("#revenue-tbody tr").all_inner_texts()
                assert gross == "₹299", gross
                assert "Sandbox: ₹3,750" in basis and "Unclassified: ₹125" in basis, basis
                assert "Gateway environment" in headers
                assert any("PROD" in row and "₹299" in row for row in rows), rows
                assert any("TEST" in row and "₹3,750" in row for row in rows), rows
                assert any("UNKNOWN" in row and "₹125" in row for row in rows), rows
                assert any("₹0" in row for row in rows), rows
                assert page.locator("#pp-admin-amount-xss").count() == 0
                assert page.evaluate("window.__adminXss") == 0
                assert page.locator("#bar-chart-container").get_attribute("role") == "region"
                assert page.locator("#bar-chart-container").get_attribute("tabindex") == "0"
                assert page.locator(".table-container[aria-label='Paying customers and recent transactions'][tabindex='0']").count() == 1
                overflow = page.evaluate("""() => ({
                  scrollWidth: document.documentElement.scrollWidth,
                  innerWidth: window.innerWidth,
                  boxes: ['header','main','.analytics-section','.chart-card','#bar-chart-container','body','html'].map(selector => {
                    const element = document.querySelector(selector);
                    if (!element) return {selector, missing:true};
                    const rect = element.getBoundingClientRect();
                    return {selector, left: Math.round(rect.left), right: Math.round(rect.right),
                      width: Math.round(rect.width), clientWidth: element.clientWidth, scrollWidth: element.scrollWidth,
                      overflowX: getComputedStyle(element).overflowX};
                  }),
                  elements: [...document.querySelectorAll('body *')].map(element => {
                    const rect = element.getBoundingClientRect();
                    return {tag: element.tagName, id: element.id, className: String(element.className).slice(0,100),
                      left: Math.round(rect.left), right: Math.round(rect.right), width: Math.round(rect.width)};
                  }).filter((item, index, all) => {
                    const element = [...document.querySelectorAll('body *')][index];
                    return !element.closest('#bar-chart-container') &&
                      (item.right > window.innerWidth + 1 || item.left < -1);
                  }).slice(0,20)
                })""")
                assert overflow["scrollWidth"] <= width, overflow
                assert not errors, errors
                results.append({"round": round_no, "viewport_width": width, "production_gross": gross, "source_subtotals": basis, "environment_column": True, "rows": rows, "overflow": overflow, "page_errors": errors})
                page.close()
            browser.close()
        (OUT / "browser-id107-revenue-source-split.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
