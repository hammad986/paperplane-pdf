"""Create one Cashfree sandbox order to verify credentials and API wiring.

This creates an unpaid INR 1.00 sandbox order and never attempts a payment.
It intentionally refuses to run against the production Cashfree host.

Usage:
    python scripts/cashfree_sandbox_smoke.py
"""
from __future__ import annotations

import json
import argparse
import re
import sys
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-drop", action="store_true",
                        help="Open the sandbox checkout modal and verify the INR 1.00 amount without paying")
    args = parser.parse_args()
    print("Cashfree sandbox checkout probe" if args.verify_drop else "Cashfree sandbox order-generation smoke test")
    if config.CASHFREE_ENV != "TEST":
        print("SKIPPED: CASHFREE_ENV must be TEST for this smoke test.")
        return 2
    if not config.CASHFREE_APP_ID or not config.CASHFREE_SECRET_KEY:
        print("SKIPPED: CASHFREE_APP_ID and CASHFREE_SECRET_KEY are not configured.")
        return 2

    order_id = f"order_pp_smoke_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    payload = {
        "order_id": order_id,
        "order_amount": 1.00,
        "order_currency": "INR",
        "customer_details": {
            "customer_id": "paperplane_smoke",
            "customer_email": "sandbox-smoke@example.com",
            "customer_phone": config.CASHFREE_DEFAULT_CUSTOMER_PHONE,
        },
        "order_meta": {
            "return_url": f"http://127.0.0.1:8501/?billing=success&order_id={order_id}",
        },
        "order_note": "Paperplane Cashfree sandbox smoke test",
    }
    request = urllib.request.Request(
        f"{config.CASHFREE_BASE_URL}/orders",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-client-id": config.CASHFREE_APP_ID,
            "x-client-secret": config.CASHFREE_SECRET_KEY,
            "x-api-version": config.CASHFREE_API_VERSION,
            "x-request-id": str(uuid.uuid4()),
            "x-idempotency-key": str(uuid.uuid4()),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        print(f"FAIL: Cashfree returned HTTP {error.code}: {detail[:500]}")
        return 1
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"FAIL: Cashfree sandbox was unreachable: {error}")
        return 1

    payment_session_id = data.get("payment_session_id")
    if not payment_session_id or data.get("order_id") != order_id:
        print(f"FAIL: unexpected Cashfree response: {json.dumps(data)[:800]}")
        return 1

    verify_request = urllib.request.Request(
        f"{config.CASHFREE_BASE_URL}/orders/{order_id}",
        headers={
            "x-client-id": config.CASHFREE_APP_ID,
            "x-client-secret": config.CASHFREE_SECRET_KEY,
            "x-api-version": config.CASHFREE_API_VERSION,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(verify_request, timeout=20) as response:
            order = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        print("FAIL: Cashfree sandbox order amount could not be verified")
        return 1
    if (order.get("order_id") != order_id or order.get("order_currency") != "INR"
            or float(order.get("order_amount", 0)) != 1.0):
        print("FAIL: Cashfree sandbox order did not retain the expected INR 1.00 amount")
        return 1
    print("PASS: Cashfree confirmed this unpaid order is INR 1.00", flush=True)

    print("PASS: unpaid sandbox order created; identifiers retained only in process memory", flush=True)
    print("PASS: payment_session_id returned", flush=True)
    if args.verify_drop:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto("about:blank")
                page.add_script_tag(url="https://sdk.cashfree.com/js/v3/cashfree.js")
                page.evaluate("session => { window.__probeCheckout = Cashfree({mode: 'sandbox'}).checkout({paymentSessionId: session, redirectTarget: '_modal'}); return true; }",
                              payment_session_id)
                page.wait_for_function("[...document.querySelectorAll('iframe')].length > 0", timeout=30000)
                page.wait_for_function("window.frames.length > 1 && [...document.querySelectorAll('iframe')].some(frame => frame.src.includes('cashfree.com'))",
                                       timeout=30000)
                browser.close()
        except Exception as error:
            detail = str(error).replace(payment_session_id, "[session redacted]").replace(order_id, "[order redacted]")
            detail = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email redacted]", detail)
            detail = re.sub(r"\b\d{8,}\b", "[number redacted]", detail)
            print(f"FAIL: sandbox checkout drop did not verify: {type(error).__name__}: {detail[:240]}")
            return 1
        print("PASS: Cashfree sandbox checkout drop loaded for the provider-verified INR 1.00 order; no payment was submitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
