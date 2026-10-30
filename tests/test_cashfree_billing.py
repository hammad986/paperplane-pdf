from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi.testclient import TestClient

import persistence
import server


def _registered_client() -> tuple[TestClient, str, str]:
    client = TestClient(server.app)
    email = f"cashfree_{os.urandom(6).hex()}@paperplane.test"
    response = client.post(
        "/api/auth/register",
        data={"email": email, "password": "CashfreeSecure123!"},
    )
    assert response.status_code == 200
    payload = response.json()
    client.headers["Authorization"] = f"Bearer {payload['token']}"
    return client, payload["user_id"], payload["token"]


def test_cashfree_checkout_creates_inr_order_and_persists_order_id(monkeypatch):
    client, user_id, _ = _registered_client()
    captured: dict = {}

    monkeypatch.setattr(server, "CASHFREE_APP_ID", "sandbox-app")
    monkeypatch.setattr(server, "CASHFREE_SECRET_KEY", "sandbox-secret")
    monkeypatch.setattr(server, "CASHFREE_ENV", "TEST")
    monkeypatch.setattr(server, "PAPERPLANE_PUBLIC_URL", "https://paperplane.example")

    def fake_request(method: str, path: str, body: dict | None = None) -> dict:
        captured.update({"method": method, "path": path, "body": body})
        return {"payment_session_id": "session_test_123"}

    monkeypatch.setattr(server, "_cashfree_request", fake_request)

    response = client.post("/api/billing/checkout-session", json={"tier": "pro"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["payment_session_id"] == "session_test_123"
    assert payload["environment"] == "TEST"
    assert payload["order_id"].startswith(f"order_pp_{user_id[:8]}_")
    assert captured["method"] == "POST"
    assert captured["path"] == "/orders"
    assert captured["body"]["order_amount"] == 250
    assert captured["body"]["order_currency"] == "INR"
    assert captured["body"]["customer_details"]["customer_id"] == user_id
    assert "billing=success" in captured["body"]["order_meta"]["return_url"]
    assert persistence.get_user_by_payment_order(payload["order_id"])["id"] == user_id


def test_cashfree_paid_order_promotes_tier_from_audited_order(monkeypatch):
    client, user_id, _ = _registered_client()
    order_id = f"order_pp_{user_id[:8]}_{int(time.time())}_verify"

    monkeypatch.setattr(server, "CASHFREE_APP_ID", "sandbox-app")
    monkeypatch.setattr(server, "CASHFREE_SECRET_KEY", "sandbox-secret")
    persistence.set_user_tier(
        user_id,
        tier="free",
        status="inactive",
        cashfree_order_id=order_id,
        payment_method="cashfree",
    )
    persistence.record_billing_event(
        order_id,
        "cashfree.order_created",
        user_id,
        {"tier": "developer", "user_id": user_id},
    )

    monkeypatch.setattr(
        server,
        "_cashfree_request",
        lambda method, path, body=None: {
            "order_id": order_id,
            "order_status": "PAID",
            "customer_details": {"customer_id": user_id},
        },
    )

    response = client.get(f"/api/billing/verify-order/{order_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "paid"
    assert response.json()["tier"] == "developer"
    assert persistence.get_user(user_id)["tier"] == "developer"


def test_cashfree_webhook_signature_audits_payload_and_activates_tier(monkeypatch):
    _, user_id, token = _registered_client()
    order_id = f"order_pp_{user_id[:8]}_{int(time.time())}_webhook"
    secret = "webhook-secret"
    monkeypatch.setattr(server, "CASHFREE_SECRET_KEY", secret)
    persistence.set_user_tier(
        user_id,
        tier="free",
        status="inactive",
        cashfree_order_id=order_id,
        payment_method="cashfree",
    )
    persistence.record_billing_event(
        order_id,
        "cashfree.order_created",
        user_id,
        {"tier": "pro", "user_id": user_id},
    )

    event = {
        "type": "PAYMENT_SUCCESS_WEBHOOK",
        "data": {
            "order": {"order_id": order_id},
            "payment": {"order_id": order_id, "payment_status": "SUCCESS", "payment_method": {"upi": {}}},
            "customer_details": {"customer_id": user_id},
        },
    }
    raw_body = json.dumps(event, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time() * 1000))
    signature = base64.b64encode(
        hmac.new(secret.encode(), timestamp.encode() + raw_body, hashlib.sha256).digest()
    ).decode("ascii")

    webhook_client = TestClient(server.app)
    response = webhook_client.post(
        "/api/billing/cashfree-webhook",
        content=raw_body,
        headers={
            "x-webhook-timestamp": timestamp,
            "x-webhook-signature": signature,
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "OK"}
    assert persistence.get_user(user_id)["tier"] == "pro"
    with persistence.connect() as connection:
        audited = connection.execute(
            "SELECT event_type, payload FROM billing_events WHERE event_type = ? ORDER BY created_at DESC LIMIT 1",
            ("PAYMENT_SUCCESS_WEBHOOK",),
        ).fetchone()
    assert audited is not None
    assert json.loads(audited["payload"]) == event
