from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
import secrets
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import ai_engine
import email_service
import persistence
import server


@pytest.fixture
def admin_audit_db(tmp_path, monkeypatch):
    database = tmp_path / "admin-audit.sqlite3"
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    monkeypatch.setattr(persistence, "DATABASE", database)
    monkeypatch.setattr(server, "JOBS", jobs)
    persistence.init_db()
    return database, jobs


def _admin_headers():
    return {"X-Admin-Session": persistence.create_admin_session(server.PRIMARY_ADMIN_EMAIL)}


def _password():
    return secrets.token_urlsafe(24)


def _credential():
    return secrets.token_urlsafe(32)


def test_admin_routes_reject_direct_keys_and_url_credentials_and_hide_contact(admin_audit_db, monkeypatch):
    admin_key = _credential()
    monkeypatch.setattr(server, "ADMIN_SECRET_KEY", admin_key)
    client = TestClient(server.app, raise_server_exceptions=False)

    assert client.get("/api/admin/dashboard", headers={"X-Admin-Key": admin_key}).status_code == 401
    assert client.get("/api/admin/dashboard", params={"key": admin_key}).status_code == 401
    token = persistence.create_admin_session(server.PRIMARY_ADMIN_EMAIL)
    assert client.get("/api/admin/dashboard", params={"session": token}).status_code == 401

    status = client.get("/api/admin/auth/status")
    assert status.status_code == 200
    assert "alert_email" not in status.json()
    assert client.get("/api/admin/dashboard", headers={"X-Admin-Session": token}).status_code == 200


def test_public_admin_shell_does_not_embed_owner_contact():
    response = TestClient(server.app).get("/admin")
    assert response.status_code == 200
    assert "configured owner email address" in response.text
    assert re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", response.text, re.IGNORECASE) is None


def test_waitlist_alert_does_not_use_a_source_coded_recipient(monkeypatch):
    monkeypatch.delenv("ADMIN_ALERT_EMAIL", raising=False)
    with patch.object(email_service, "_dispatch_email") as dispatch:
        assert email_service.send_waitlist_alert("customer@example.test") is False
    dispatch.assert_not_called()


def test_waitlist_rejects_malformed_data_and_escapes_email_fields(admin_audit_db, monkeypatch):
    client = TestClient(server.app, raise_server_exceptions=False)
    malformed = client.post(
        "/api/waitlist",
        json={"email": "<img src=x>@example.test", "platform": "windows"},
    )
    malformed_platform = client.post(
        "/api/waitlist",
        json={"email": "visitor@example.test", "platform": ["windows"]},
    )
    assert malformed.status_code == 422
    assert malformed_platform.status_code == 422
    assert persistence.get_waitlist_count() == 0

    monkeypatch.setenv("ADMIN_ALERT_EMAIL", "admin@example.test")
    with patch.object(email_service, "_dispatch_email", return_value=True) as dispatch:
        assert email_service.send_waitlist_alert(
            "<img src=x>@example.test", platform="<script>", ip_address="<b>"
        ) is True
    html_body = dispatch.call_args.args[2]
    assert "<img src=x>" not in html_body
    assert "&lt;img src=x&gt;" in html_body
    assert "<script>" not in html_body
    assert "&lt;script&gt;" in html_body


def test_ai_provider_redirects_are_not_followed_with_credentials():
    request = ai_engine.urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": _credential()},
    )
    handler = ai_engine._NoRedirectHandler()
    assert handler.redirect_request(
        request,
        None,
        307,
        "Temporary Redirect",
        {},
        "https://attacker.example/collect",
    ) is None


def test_three_factor_admin_flow_issues_only_mfa_session(admin_audit_db, monkeypatch):
    delivered: list[str] = []
    monkeypatch.setattr(server, "ADMIN_SECRET_KEY", secrets.token_hex(32))
    monkeypatch.setattr(server, "ADMIN_SECRET_CODE", _credential())
    monkeypatch.setattr(server, "ADMIN_ALERT_EMAIL", "owner@example.invalid")
    monkeypatch.setattr(
        server,
        "send_admin_login_otp",
        lambda **kwargs: delivered.append(kwargs["otp_code"]) or True,
    )
    client = TestClient(server.app, raise_server_exceptions=False)

    bad = client.post("/api/admin/auth/step1", json={"admin_key": _credential(), "admin_code": server.ADMIN_SECRET_CODE})
    assert bad.status_code == 401
    unicode_bad = client.post("/api/admin/auth/step1", json={"admin_key": "🔒", "admin_code": "🔑"})
    assert unicode_bad.status_code == 401
    start = client.post(
        "/api/admin/auth/step1",
        json={"admin_key": server.ADMIN_SECRET_KEY, "admin_code": server.ADMIN_SECRET_CODE},
    )
    assert start.status_code == 200
    assert "email" not in start.json()
    assert len(delivered) == 1
    finish = client.post("/api/admin/auth/step2", json={"otp": delivered[0], "challenge": start.json()["challenge"]})

    assert finish.status_code == 200
    session_token = finish.json()["session_token"]
    assert client.get("/api/admin/dashboard", headers={"X-Admin-Session": session_token}).status_code == 200
    assert client.get("/api/admin/dashboard", params={"session": session_token}).status_code == 401


def test_admin_step_one_fails_closed_when_otp_delivery_fails(admin_audit_db, monkeypatch):
    monkeypatch.setattr(server, "ADMIN_SECRET_KEY", secrets.token_hex(32))
    monkeypatch.setattr(server, "ADMIN_SECRET_CODE", _credential())
    monkeypatch.setattr(server, "ADMIN_ALERT_EMAIL", "owner@example.invalid")
    monkeypatch.setattr(server, "send_admin_login_otp", lambda **kwargs: False)
    client = TestClient(server.app, raise_server_exceptions=False)

    response = client.post(
        "/api/admin/auth/step1",
        json={"admin_key": server.ADMIN_SECRET_KEY, "admin_code": server.ADMIN_SECRET_CODE},
    )

    assert response.status_code == 503
    with persistence.connect() as db:
        remaining = db.execute("SELECT count(*) FROM admin_challenges").fetchone()[0]
    assert remaining == 0
    assert "session_token" not in response.json()


def test_otp_codes_are_absent_from_subjects_and_delivery_logs(monkeypatch):
    monkeypatch.setattr(email_service, "SMTP_ENABLED", False)
    monkeypatch.setattr(email_service, "SMTP_HOST", "")
    monkeypatch.setattr(email_service, "RESEND_API_KEY", _credential())
    code = f"{secrets.randbelow(1_000_000):06d}"
    sent_payloads = []
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = email_service.logger
    old_handlers, old_level, old_propagate = logger.handlers[:], logger.level, logger.propagate
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    class FakeResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def read(self): return b'{"id":"synthetic-message"}'

    def fake_urlopen(request, timeout=10):
        sent_payloads.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse()

    try:
        with patch("email_service.urllib.request.urlopen", side_effect=fake_urlopen):
            assert email_service.send_otp_email("qa@example.test", code, "login") is True
            assert email_service.send_admin_login_otp("owner@example.test", code, "198.51.100.7") is True
        output = stream.getvalue()
    finally:
        logger.handlers = old_handlers
        logger.setLevel(old_level)
        logger.propagate = old_propagate
        handler.close()

    assert len(sent_payloads) == 2
    for payload in sent_payloads:
        assert code not in payload["subject"]
        assert code in payload["text"]
        assert code in payload["html"]
    assert code not in output


def test_transactional_email_templates_escape_untrusted_html_fields(monkeypatch):
    delivered = []

    def capture(to_email, subject, html_body, text_body, **kwargs):
        delivered.append((subject, html_body))
        return True

    monkeypatch.setattr(email_service, "PAPERPLANE_PUBLIC_URL", "https://paperplane.example.test")
    with patch.object(email_service, "_dispatch_email", side_effect=capture):
        assert email_service.send_login_notification(
            "<b>person@example.test</b>", "<script>ip</script>", "<img src=x onerror=alert(1)>")
        assert email_service.send_admin_login_otp(
            "owner@example.test", _credential(), "<svg onload=alert(1)>")
        assert email_service.send_admin_lockout_alert(
            "owner@example.test", "<svg onload=alert(1)>", "<script>reason</script>")
        assert email_service.send_password_reset_email(
            "<b>person@example.test</b>", _credential(), "https://paperplane.example.test/<script>")
        assert email_service.send_password_changed_notification(
            "<b>person@example.test</b>", "<script>ip</script>")

    assert len(delivered) == 5
    joined_html = "\n".join(html_body for _, html_body in delivered)
    assert "<script>" not in joined_html
    assert "<svg" not in joined_html
    assert "<img src=x" not in joined_html
    assert "&lt;script&gt;" in joined_html
    assert "&lt;svg" in joined_html
    assert "&lt;img" in joined_html


def test_admin_otp_is_single_use(admin_audit_db):
    generated_otp = f"{secrets.randbelow(1_000_000):06d}"
    challenge = persistence.set_admin_pending_otp(generated_otp, server.PRIMARY_ADMIN_EMAIL, "127.0.0.1")
    with persistence.connect() as db:
        stored_digest = db.execute(
            "SELECT otp_hash AS pending_otp_hash FROM admin_challenges WHERE id = ?", (challenge,)
        ).fetchone()[0]
    assert stored_digest != hashlib.sha256(generated_otp.encode()).hexdigest()
    assert stored_digest == persistence._admin_otp_digest(generated_otp)
    assert persistence.verify_admin_otp(generated_otp, challenge, "127.0.0.1") == server.PRIMARY_ADMIN_EMAIL
    assert persistence.verify_admin_otp(generated_otp, challenge, "127.0.0.1") is None


def test_admin_lockout_is_per_ip_and_proxy_header_is_overwritten(admin_audit_db):
    source_a = TestClient(server.app, client=("198.51.100.10", 50100), raise_server_exceptions=False)
    source_b = TestClient(server.app, client=("198.51.100.11", 50101), raise_server_exceptions=False)
    assert persistence.record_admin_failed_attempt("198.51.100.10") == (1, False)
    assert persistence.record_admin_failed_attempt("198.51.100.10") == (2, False)
    attempts, locked = persistence.record_admin_failed_attempt("198.51.100.10")
    assert attempts == 3 and locked
    assert persistence.get_admin_lockout_remaining("198.51.100.10") > 0
    assert persistence.get_admin_lockout_remaining("198.51.100.11") == 0
    assert source_a.get("/api/admin/auth/status").json()["locked"] is True
    assert source_b.get("/api/admin/auth/status").json()["locked"] is False

    nginx = (Path(__file__).resolve().parents[1] / "deploy" / "nginx.conf.template").read_text(encoding="utf-8")
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in nginx
    assert "$proxy_add_x_forwarded_for" not in nginx
    assert "proxy_hide_header" not in nginx
    for header in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy", "Content-Security-Policy"):
        assert f"add_header {header} " in nginx


def test_application_does_not_duplicate_edge_security_headers(admin_audit_db):
    response = TestClient(server.app).get("/")
    for header in ("x-content-type-options", "x-frame-options", "referrer-policy", "permissions-policy"):
        assert response.headers.get_list(header) == []
    assert response.headers.get_list("content-security-policy") == []

    server_source = (Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8")
    assert "SecurityHeadersMiddleware" not in server_source


def test_admin_audit_summary_is_owner_only(admin_audit_db):
    user_id = persistence.create_user("pro-audit@example.test", _password())
    persistence.set_user_tier(user_id, tier="pro", status="active")
    user_token = persistence.create_session_for_user(user_id)["token"]
    persistence.record_audit_event("synthetic_probe", user_id=user_id, email="target@example.test", details="scratch record")
    client = TestClient(server.app, raise_server_exceptions=False)

    pro_response = client.get("/api/admin/audit-summary", headers={"Authorization": f"Bearer {user_token}"})
    owner_response = client.get("/api/admin/audit-summary", headers=_admin_headers())

    assert pro_response.status_code == 401
    assert owner_response.status_code == 200
    assert owner_response.json()["total_records"] >= 1


def test_admin_ai_connection_reports_native_provider_success(admin_audit_db, monkeypatch):
    monkeypatch.setattr(
        ai_engine,
        "test_bluesminds_connectivity",
        lambda: {"status": "inference_succeeded", "http_status": 200, "message": "AI connected successfully."},
    )
    response = TestClient(server.app, raise_server_exceptions=False).post(
        "/api/admin/ai-test", headers=_admin_headers()
    )

    assert response.status_code == 200
    assert response.json()["result"]["status"] == "inference_succeeded"
    admin_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "admin.js").read_text(encoding="utf-8")
    assert '["ok", "inference_succeeded"].includes(data.result.status)' in admin_js


def test_feedback_validation_rejects_bad_fields_and_oversized_body(admin_audit_db):
    client = TestClient(server.app, client=("198.51.100.12", 50102), raise_server_exceptions=False)

    assert client.post("/api/feedback", json={"rating": "bad", "message": "hello"}).status_code == 422
    assert client.post("/api/feedback", json={"rating": 6, "message": "hello"}).status_code == 422
    assert client.post("/api/feedback", json={"rating": 5, "category": "other", "message": "hello"}).status_code == 422
    assert client.post("/api/feedback", json={"rating": 5, "email": "bad", "message": "hello"}).status_code == 422
    assert client.post("/api/feedback", json={"rating": 5, "message": "x" * 9000}).status_code == 413
    assert client.post("/api/feedback", json={"rating": 5, "message": "x" * 1001}).status_code == 422

    with persistence.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM user_feedbacks").fetchone()[0] == 0

    valid = client.post("/api/feedback", json={"rating": 5, "category": "bug", "message": "A concise synthetic note."})
    assert valid.status_code == 200


def test_feedback_submissions_are_visible_to_admin_after_each_write(admin_audit_db):
    client = TestClient(server.app)
    headers = _admin_headers()

    for index in range(3):
        response = client.post(
            "/api/feedback",
            json={"rating": 5, "category": "general", "message": f"Synthetic persistence check {index + 1}."},
        )
        assert response.status_code == 200
        feedback_id = response.json()["feedback_id"]
        visible = client.get("/api/admin/feedback", headers=headers)
        assert visible.status_code == 200
        assert feedback_id in {item["id"] for item in visible.json()["feedbacks"]}


def test_probe_cleanup_requires_review_and_protects_configured_owner(admin_audit_db):
    owner_email = "owner@example.com"
    probe_id = persistence.create_user("support-probe@customer.invalid", _password())
    owner_id = persistence.create_user(owner_email, _password())

    preview = persistence.admin_cleanup_probe_accounts(protected_emails={owner_email})
    assert preview["preview"] is True
    assert probe_id in {item["id"] for item in preview["candidates"]}
    assert owner_id not in {item["id"] for item in preview["candidates"]}
    assert persistence.get_user(probe_id) is not None

    result = persistence.admin_cleanup_probe_accounts(
        confirm=True,
        candidate_ids=[probe_id],
        protected_emails={owner_email},
    )
    assert result["deleted_count"] == 1
    assert persistence.get_user(probe_id) is None
    assert persistence.get_user(owner_id) is not None


def test_probe_cleanup_only_matches_explicit_test_markers(admin_audit_db):
    expected = {
        persistence.create_user("support-probe@customer.invalid", _password()),
        persistence.create_user("qa+test@example.com", _password()),
    }
    legitimate_domains = {
        persistence.create_user("member@mail.tab.bot", _password()),
        persistence.create_user("reviewer@mail.instinct.com", _password()),
        persistence.create_user("customer@sharklasers.com", _password()),
        persistence.create_user("customer@example.com", _password()),
    }

    preview = persistence.admin_cleanup_probe_accounts()
    candidate_ids = {item["id"] for item in preview["candidates"]}
    candidate_emails = {item["email"] for item in preview["candidates"]}

    assert candidate_ids == expected
    assert candidate_emails == {"support-probe@customer.invalid", "qa+test@example.com"}
    assert candidate_ids.isdisjoint(legitimate_domains)
    assert all(persistence.get_user(user_id) is not None for user_id in expected | legitimate_domains)


def test_user_delete_removes_files_and_anonymizes_retained_financial_records(admin_audit_db, monkeypatch):
    _, jobs = admin_audit_db
    owner_email = "owner@example.test"
    monkeypatch.setattr(server, "ADMIN_ALERT_EMAIL", owner_email)
    user_id = persistence.create_user("delete-me@example.test", _password())
    persistence.set_user_tier(user_id, tier="pro", status="active", customer_id="provider-customer-id")
    job_id, _ = persistence.create_job("compress", user_id, ttl=3600)
    persistence.update_job(job_id, status="completed")
    job_dir = jobs / job_id
    job_dir.mkdir()
    (job_dir / "synthetic-output.txt").write_text("scratch output", encoding="utf-8")
    persistence.record_billing_event(
        "synthetic-order-event",
        "cashfree.order_verified",
        user_id,
        {"user_id": user_id, "customer_email": "delete-me@example.test", "order": {"order_id": "order-synthetic", "order_amount": 100}},
    )

    response = TestClient(server.app, raise_server_exceptions=False).post(
        "/api/admin/users/delete",
        headers={"Content-Type": "application/json", **_admin_headers()},
        json={"user_id": user_id},
    )

    assert response.status_code == 200
    assert persistence.get_user(user_id) is None
    assert not job_dir.exists()
    assert response.json()["financial_ledger_anonymized"] is True
    with persistence.connect() as db:
        event = db.execute("SELECT customer_id, payload FROM billing_events WHERE id = ?", ("synthetic-order-event",)).fetchone()
    assert event["customer_id"] is None
    assert "order_amount" in event["payload"]
    assert "delete-me@example.test" not in event["payload"]
    assert user_id not in event["payload"]

    protected_id = persistence.create_user(owner_email, _password())
    blocked = TestClient(server.app, raise_server_exceptions=False).post(
        "/api/admin/users/delete",
        headers={"Content-Type": "application/json", **_admin_headers()},
        json={"user_id": protected_id},
    )
    assert blocked.status_code == 409
    assert persistence.get_user(protected_id) is not None


def test_csv_exports_escape_spreadsheet_formulas(admin_audit_db):
    with persistence.connect() as db:
        db.execute(
            "INSERT INTO app_waitlist (id,email,platform,created_at,ip_address) VALUES (?,?,?,?,?)",
            ("formula-row", "normal@example.test", "\t=1+1", time.time(), "192.0.2.20"),
        )
        db.commit()
    client = TestClient(server.app, raise_server_exceptions=False)
    response = client.get("/api/admin/waitlist/export.csv", headers=_admin_headers())

    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[1][2] == "'\t=1+1"
    assert server._safe_csv_cell("ordinary") == "ordinary"
    for prefix in ("=", "+", "-", "@"):
        assert server._safe_csv_cell(prefix + "1+1").startswith("'")


def test_revenue_uses_verified_deduplicated_inr_orders_and_configured_fees(admin_audit_db, monkeypatch):
    monkeypatch.setattr(persistence, "PAYMENT_GATEWAY_FEE_PERCENT", 2.0)
    monkeypatch.setattr(persistence, "PAYMENT_GATEWAY_FEE_GST_PERCENT", 18.0)
    paid_user = persistence.create_user("paid-customer@example.test", _password())
    persistence.set_user_tier(
        paid_user, tier="pro", status="active", cashfree_order_id="verified-order"
    )
    demo_user = persistence.create_user("demo-customer@example.test", _password())
    persistence.set_user_tier(
        demo_user, tier="developer", status="active", cashfree_order_id="demo-order", payment_method="cashfree_demo"
    )
    unverified_user = persistence.create_user("unverified-customer@example.test", _password())
    persistence.set_user_tier(unverified_user, tier="pro", status="active")
    verified_payload = {
        "gateway_environment": "PROD",
        "order": {
            "order_id": "verified-order", "order_amount": 100,
            "order_currency": "INR", "order_status": "PAID",
        }
    }
    persistence.record_billing_event("verified-event-1", "cashfree.order_verified", paid_user, verified_payload)
    persistence.record_billing_event("verified-event-2", "cashfree.order_verified", paid_user, verified_payload)
    persistence.record_billing_event(
        "pending-event", "cashfree.order_verified", demo_user,
        {"order": {"order_id": "pending-order", "order_amount": 500, "order_currency": "INR", "order_status": "PENDING"}},
    )
    persistence.record_billing_event(
        "foreign-event", "cashfree.order_verified", paid_user,
        {"order": {"order_id": "foreign-order", "order_amount": 500, "order_currency": "USD", "order_status": "PAID"}},
    )
    persistence.record_billing_event(
        "uncurrency-event", "cashfree.order_verified", paid_user,
        {"order": {"order_id": "unknown-currency", "order_amount": 500, "order_status": "PAID"}},
    )

    result = persistence.admin_get_revenue_analytics()

    assert result["paying_users_count"] == 1
    assert result["gross_revenue_inr"] == 100.0
    assert result["gateway_fee_rate_percent"] == 2.36
    assert result["estimated_gateway_fees_inr"] == 2.36
    assert result["net_bank_payout_inr"] == 97.64
    assert len(result["recent_transactions"]) == 1
    assert all("user_id" not in row for row in result["recent_transactions"])


def test_admin_ai_credential_is_encrypted_and_provider_route_is_native(admin_audit_db, monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    api_key = _credential()
    monkeypatch.setattr(persistence, "AI_SETTINGS_ENCRYPTION_KEY", key)
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    public = persistence.admin_set_ai_config(
        "anthropic", "claude-test-model", "https://api.anthropic.com/v1", api_key
    )
    assert public["has_key"] is True
    assert not secrets.compare_digest(api_key.encode(), public["api_key_masked"].encode())
    with persistence.connect() as db:
        stored = db.execute("SELECT value FROM admin_system_settings WHERE key='AI_API_KEY__anthropic'").fetchone()[0]
    assert stored.startswith("fernet:v1:")
    assert not secrets.compare_digest(api_key, stored)
    assert secrets.compare_digest(persistence.get_runtime_ai_credentials()["api_key"], api_key)

    class FakeResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def read(self): return b'{"content":[{"type":"text","text":"native response"}]}'

    with patch("ai_engine._open_ai_request", return_value=FakeResponse()) as open_url:
        assert ai_engine.call_llm("system text", "user text") == "native response"
    req = open_url.call_args.args[0]
    assert req.full_url == "https://api.anthropic.com/v1/messages"
    assert secrets.compare_digest(str(req.get_header("X-api-key") or ""), api_key)
    assert req.get_header("Authorization") is None
    payload = json.loads(req.data)
    assert payload["system"] == "system text"
    assert payload["messages"][0]["content"] == "user text"


def test_ai_provider_keys_are_isolated_and_masked_values_are_not_saved(admin_audit_db, monkeypatch):
    monkeypatch.setattr(persistence, "AI_SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    bluesminds_key = _credential()
    saved = persistence.admin_set_ai_config(
        "bluesminds", "test-model", "https://api.bluesminds.com/v1", bluesminds_key
    )
    persistence.admin_set_ai_config(
        "bluesminds", "test-model", "https://api.bluesminds.com/v1", saved["api_key_masked"]
    )
    assert secrets.compare_digest(persistence.get_runtime_ai_credentials()["api_key"], bluesminds_key)

    persistence.admin_set_ai_config("anthropic", "test-model", "https://api.anthropic.com/v1")
    assert persistence.get_runtime_ai_credentials()["api_key"] == ""
    persistence.admin_set_ai_config("bluesminds", "test-model", "https://api.bluesminds.com/v1")
    assert secrets.compare_digest(persistence.get_runtime_ai_credentials()["api_key"], bluesminds_key)


@pytest.mark.parametrize(
    ("provider", "endpoint_base_url", "expected_url", "response_body", "auth_header"),
    [
        (
            "openai_compatible", "https://gateway.example/v1", "https://gateway.example/v1/chat/completions",
            b'{"choices":[{"message":{"content":"compatible response"}}]}', "Authorization",
        ),
        (
            "bluesminds", "https://api.bluesminds.com/v1", "https://api.bluesminds.com/v1/chat/completions",
            b'{"choices":[{"message":{"content":"bluesminds response"}}]}', "Authorization",
        ),
        (
            "openrouter", "https://openrouter.ai/api/v1", "https://openrouter.ai/api/v1/chat/completions",
            b'{"choices":[{"message":{"content":"openrouter response"}}]}', "Authorization",
        ),
        (
            "deepseek", "https://api.deepseek.com/v1", "https://api.deepseek.com/v1/chat/completions",
            b'{"choices":[{"message":{"content":"deepseek response"}}]}', "Authorization",
        ),
        (
            "anthropic", "https://api.anthropic.com/v1", "https://api.anthropic.com/v1/messages",
            b'{"content":[{"type":"text","text":"anthropic response"}]}', "X-api-key",
        ),
        (
            "gemini", "https://generativelanguage.googleapis.com", "https://generativelanguage.googleapis.com/v1beta/models/test-model:generateContent",
            b'{"candidates":[{"content":{"parts":[{"text":"gemini response"}]}}]}', "X-goog-api-key",
        ),
    ],
)
def test_legacy_ai_entrypoint_dispatches_every_provider(
    admin_audit_db, monkeypatch, provider, endpoint_base_url, expected_url, response_body, auth_header
):
    key = Fernet.generate_key().decode("ascii")
    api_key = _credential()
    monkeypatch.setattr(persistence, "AI_SETTINGS_ENCRYPTION_KEY", key)
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    if provider == "openai_compatible":
        monkeypatch.setattr(
            persistence.socket,
            "getaddrinfo",
            lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 443))],
        )
    persistence.admin_set_ai_config(provider, "test-model", endpoint_base_url, api_key)

    class FakeResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def read(self): return response_body

    with patch("ai_engine._open_ai_request", return_value=FakeResponse()) as open_url:
        result = ai_engine.call_agentrouter("system text", "user text", model="test-model")

    request = open_url.call_args.args[0]
    assert result.endswith("response")
    assert request.full_url == expected_url
    assert secrets.compare_digest(str(request.get_header(auth_header) or ""), api_key if auth_header != "Authorization" else f"Bearer {api_key}")
    if provider in {"openai_compatible", "bluesminds", "openrouter", "deepseek"}:
        assert json.loads(request.data)["model"] == "test-model"
        assert request.get_header("X-api-key") is None
    elif provider == "anthropic":
        assert json.loads(request.data)["messages"][0]["content"] == "user text"
        assert request.get_header("Authorization") is None
    else:
        assert json.loads(request.data)["contents"][0]["parts"][0]["text"] == "user text"
        assert request.get_header("Authorization") is None


def test_selected_provider_does_not_fall_back_to_bluesminds_key(admin_audit_db, monkeypatch):
    monkeypatch.setattr(persistence, "AI_SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", _credential())
    persistence.admin_set_ai_config("anthropic", "test-model", "https://api.anthropic.com/v1")

    with patch("ai_engine._open_ai_request") as open_url:
        with pytest.raises(ValueError, match="AI provider is not configured"):
            ai_engine.call_llm("system", "user")
    open_url.assert_not_called()


def test_ai_provider_endpoint_validation_blocks_local_and_insecure_targets(admin_audit_db, monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    api_key = _credential()
    monkeypatch.setattr(persistence, "AI_SETTINGS_ENCRYPTION_KEY", key)
    with pytest.raises(ValueError, match="HTTPS"):
        persistence.admin_set_ai_config("openai_compatible", "test-model", "http://127.0.0.1/v1", api_key)
    with pytest.raises(ValueError, match="private or reserved"):
        persistence.admin_set_ai_config("openai_compatible", "test-model", "https://127.0.0.1/v1", api_key)

    monkeypatch.setattr(
        persistence.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("10.0.0.8", 443))],
    )
    with pytest.raises(ValueError, match="private or reserved"):
        persistence.admin_set_ai_config("openai_compatible", "test-model", "https://gateway.example/v1", api_key)


def test_missing_ai_encryption_key_cannot_store_plaintext(admin_audit_db, monkeypatch):
    api_key = _credential()
    monkeypatch.setattr(persistence, "AI_SETTINGS_ENCRYPTION_KEY", "")
    monkeypatch.delenv("PAPERPLANE_AI_SETTINGS_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="PAPERPLANE_AI_SETTINGS_ENCRYPTION_KEY"):
        persistence.admin_set_ai_config("bluesminds", "test-model", "https://api.bluesminds.com/v1", api_key)


def test_legacy_ai_credential_migrates_to_its_provider_key(admin_audit_db, monkeypatch):
    api_key = _credential()
    monkeypatch.setattr(persistence, "AI_SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    with persistence.connect() as db:
        db.execute(
            "INSERT INTO admin_system_settings (key, value, updated_at) VALUES ('AI_PROVIDER', 'anthropic', ?)",
            (time.time(),),
        )
        db.execute(
            "INSERT INTO admin_system_settings (key, value, updated_at) VALUES ('AI_API_KEY', ?, ?)",
            (api_key, time.time()),
        )
        db.commit()

    runtime = persistence.get_runtime_ai_credentials()

    assert runtime["provider"] == "anthropic"
    assert secrets.compare_digest(runtime["api_key"], api_key)
    with persistence.connect() as db:
        legacy = db.execute("SELECT value FROM admin_system_settings WHERE key='AI_API_KEY'").fetchone()
        migrated = db.execute("SELECT value FROM admin_system_settings WHERE key='AI_API_KEY__anthropic'").fetchone()[0]
    assert legacy is None
    assert migrated.startswith("fernet:v1:")
    assert not secrets.compare_digest(api_key, migrated)
