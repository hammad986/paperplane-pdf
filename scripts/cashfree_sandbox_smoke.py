"""Create one Cashfree sandbox order to verify credentials and API wiring.

This creates an unpaid INR 1.00 sandbox order and never attempts a payment.
It intentionally refuses to run against the production Cashfree host.

Usage:
    python scripts/cashfree_sandbox_smoke.py
"""
from __future__ import annotations

import json
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
    print("Cashfree sandbox order-generation smoke test")
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

    print(f"PASS: order_id={order_id}")
    print("PASS: payment_session_id returned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
