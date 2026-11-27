"""Browser-check that sandbox receipts are not styled or labeled as production revenue."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id107-revenue-environment.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id107-") as temp:
        data_dir = Path(temp) / "data"
        app, base, identities = helper.start_server(data_dir)
        env = os.environ.copy()
        env.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_DATA_DIR=str(data_dir))
        seed = r"""
from persistence import create_user, set_user_tier, record_billing_event
prod = create_user('prod@example.test', 'test-password-123')
set_user_tier(prod, 'pro', status='active', cashfree_order_id='prod-100')
record_billing_event('event-prod', 'cashfree.order_verified', prod, {'gateway_environment':'PROD','order':{'order_id':'prod-100','order_amount':100,'order_currency':'INR','order_status':'PAID'}})
sandbox = create_user('sandbox@example.test', 'test-password-123')
set_user_tier(sandbox, 'pro', status='active', cashfree_order_id='sandbox-3750')
record_billing_event('event-sandbox', 'cashfree.order_verified', sandbox, {'gateway_environment':'TEST','order':{'order_id':'sandbox-3750','order_amount':3750,'order_currency':'INR','order_status':'PAID'}})
"""
        try:
            subprocess.run([sys.executable, "-c", seed], cwd=ROOT, env=env, check=True, capture_output=True, text=True)
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local Paperplane server exited before startup")
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            evidence = {"page_errors": [], "console_errors": []}
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                context.add_init_script(f"sessionStorage.setItem('pp_admin_session',{json.dumps(identities['admin'])})")
                page = context.new_page()
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: evidence["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                page.goto(base + "/admin", wait_until="domcontentloaded")
                page.wait_for_function("document.querySelector('#dashboard-view')?.style.display !== 'none'")
                page.locator("#tab-revenue-btn").click()
                page.wait_for_function("document.querySelector('#revenue-tbody')?.innerText.includes('Sandbox paid')")
                revenue = page.locator("#rev-gross-revenue").inner_text()
                sandbox_row = page.locator("#revenue-tbody tr").filter(has_text="sandbox-3750")
                prod_row = page.locator("#revenue-tbody tr").filter(has_text="prod-100")
                evidence.update({
                    "production_gross_label": revenue,
                    "sandbox_row": sandbox_row.inner_text(),
                    "sandbox_status": sandbox_row.locator("td:last-child").inner_text(),
                    "sandbox_status_color": sandbox_row.locator("td:last-child span").evaluate("el => getComputedStyle(el).color"),
                    "production_status": prod_row.locator("td:last-child").inner_text(),
                    "production_status_color": prod_row.locator("td:last-child span").evaluate("el => getComputedStyle(el).color"),
                    "sandbox_separate_total": "₹3,750" in page.locator("#rev-revenue-basis").inner_text(),
                })
                browser.close()
            evidence["overall"] = "passed" if (
                evidence["production_gross_label"] == "₹100"
                and "Sandbox paid" in evidence["sandbox_status"]
                and "Paid" in evidence["production_status"]
                and evidence["sandbox_status_color"] != evidence["production_status_color"]
                and evidence["sandbox_separate_total"]
                and not evidence["page_errors"] and not evidence["console_errors"]
            ) else "failed"
            OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if evidence["overall"] != "passed":
                raise SystemExit(1)
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
