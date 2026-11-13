import os
import secrets
import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from server import app
import persistence
import converters
from tests.auth_helpers import register_verified

client = TestClient(app)


def test_ssrf_protection_blocked_ips():
    """Verify that private, loopback, and cloud metadata targets are rejected."""
    bad_urls = [
        "http://127.0.0.1:8080/secret",
        "http://localhost:8501/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/internal",
        "http://192.168.1.1/router",
        "http://172.16.0.1/db",
        "http://metadata.google.internal/computeMetadata/v1/",
    ]
    for url in bad_urls:
        safe, reason = converters.is_safe_url(url)
        assert safe is False, f"Expected {url} to be blocked, but was deemed safe: {reason}"

    # Also test via /api/cloud/sync
    for url in ["http://127.0.0.1/evil", "http://169.254.169.254/meta"]:
        res = client.post("/api/cloud/sync", data={"file_url": url})
        assert res.status_code == 400
        assert "SSRF Protection" in res.json().get("detail", "") or "forbidden" in res.json().get("detail", "").lower()


def test_google_auth_rejection_without_credentials():
    """Verify that simulated or unverified Google login is rejected in production."""
    res = client.post("/api/auth/google", json={"email": "hacker@example.com", "credential": ""})
    assert res.status_code in (400, 503)


def test_billing_simulation_blocked_in_production(monkeypatch):
    """Verify that simulate-pro and simulate-dev return 403 when simulation is disabled."""
    monkeypatch.setattr("server.ALLOW_BILLING_SIMULATION", False)
    
    # Attempt simulate-pro
    res = client.post("/api/billing/simulate-pro")
    assert res.status_code == 403
    assert "disabled" in res.json()["detail"].lower()

    # Attempt simulate-dev
    res = client.post("/api/billing/simulate-dev")
    assert res.status_code == 403

    # Attempt simulate-free
    res = client.post("/api/billing/simulate-free")
    assert res.status_code == 403


def test_cashfree_webhook_rejects_invalid_signature():
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr("server.CASHFREE_SECRET_KEY", "expected-secret")
        payload = json.dumps({"type": "PAYMENT_SUCCESS_WEBHOOK"}).encode()
        timestamp = str(int(time.time() * 1000))
        valid_signature = base64.b64encode(
            hmac.new(b"wrong-secret", timestamp.encode() + payload, hashlib.sha256).digest()
        ).decode()
        response = client.post(
            "/api/billing/cashfree-webhook",
            content=payload,
            headers={
                "x-webhook-timestamp": timestamp,
                "x-webhook-signature": valid_signature,
            },
        )
        assert response.status_code == 400
        assert "signature verification failed" in response.json()["detail"].lower()
    finally:
        monkeypatch.undo()
def test_job_tenant_isolation():
    """Verify that user-owned jobs cannot be enumerated or downloaded by unauthorized guests or other users."""
    # 1. Create a user
    email = f"isolation_test_{os.urandom(4).hex()}@paperplane.test"
    reg = register_verified(client, email, "Password123!")
    token_a = reg.json()["token"]
    user_a = reg.json()["user_id"]

    # 2. Create job for User A directly via persistence
    job_id, _ = persistence.create_job("compress", user_id=user_a, ttl=3600)

    # 3. Anonymous/Guest attempts to access User A's job without credentials -> 404
    anon_client = TestClient(app)
    res = anon_client.get(f"/api/jobs/{job_id}")
    assert res.status_code == 404

    # 4. Another user attempts to access User A's job -> 404
    email_b = f"isolation_user_b_{os.urandom(4).hex()}@paperplane.test"
    reg_b = register_verified(client, email_b, "Password123!")
    assert reg_b.status_code == 200
    token_b = reg_b.json()["token"]

    user_b_client = TestClient(app)
    user_b_client.headers["Authorization"] = f"Bearer {token_b}"
    res_b = user_b_client.get(f"/api/jobs/{job_id}")
    assert res_b.status_code == 404

    # 5. User A accesses their own job -> 200
    user_a_client = TestClient(app)
    user_a_client.headers["Authorization"] = f"Bearer {token_a}"
    res_a = user_a_client.get(f"/api/jobs/{job_id}")
    assert res_a.status_code == 200
    assert res_a.json()["id"] == job_id


def test_operations_catalog_truthful_capabilities():
    """Verify operations catalog exposes availability and prerequisite details."""
    res = client.get("/api/operations")
    assert res.status_code == 200
    data = res.json()
    assert "merge" in data
    assert "ocr" in data
    assert "html_to_pdf" in data
    # Backward compatibility: implemented is True
    assert data["merge"]["implemented"] is True
    # Truthful runtime availability
    assert "available" in data["merge"]
    assert "status" in data["merge"]


def test_auth_config_endpoint():
    """Verify /api/auth/config exposes google_enabled and google_client_id safely."""
    res = client.get("/api/auth/config")
    assert res.status_code == 200
    data = res.json()
    assert "google_enabled" in data
    assert "google_client_id" in data
    # Client secret must NEVER be exposed
    assert "google_client_secret" not in data
    assert "secret" not in str(data).lower()


def test_google_auth_missing_client_id(monkeypatch):
    """Verify 503 Service Unavailable when GOOGLE_CLIENT_ID is not configured."""
    monkeypatch.setattr("server.GOOGLE_CLIENT_ID", "")
    res = client.post("/api/auth/google", json={"credential": "sample.dummy.token"})
    assert res.status_code == 503
    assert "missing GOOGLE_CLIENT_ID" in res.json()["detail"]


def test_google_auth_empty_or_missing_credential(monkeypatch):
    """Verify 400 Bad Request when credential or id_token is missing."""
    monkeypatch.setattr("server.GOOGLE_CLIENT_ID", "configured-client-id.apps.googleusercontent.com")
    res1 = client.post("/api/auth/google", json={})
    assert res1.status_code == 400
    res2 = client.post("/api/auth/google", json={"credential": ""})
    assert res2.status_code == 400


def test_google_auth_invalid_token_fails(monkeypatch):
    """Verify 401 when token verification fails (forged, malformed, or expired)."""
    monkeypatch.setattr("server.GOOGLE_CLIENT_ID", "configured-client-id.apps.googleusercontent.com")
    res = client.post("/api/auth/google", json={"credential": "not.a.valid.jwt.token"})
    assert res.status_code == 401
    assert "failed" in res.json()["detail"].lower() or "invalid" in res.json()["detail"].lower()


def test_google_auth_audience_mismatch(monkeypatch):
    """Verify token is rejected when intended audience does not match GOOGLE_CLIENT_ID."""
    monkeypatch.setattr("server.GOOGLE_CLIENT_ID", "expected-client-id.apps.googleusercontent.com")
    monkeypatch.setattr("server.HAS_GOOGLE_AUTH", True)

    def mock_verify_oauth2_token(token, req, client_id):
        return {
            "iss": "https://accounts.google.com",
            "aud": "wrong-client-id.apps.googleusercontent.com",
            "email": "user@example.com",
            "email_verified": True
        }

    monkeypatch.setattr("server.google_id_token.verify_oauth2_token", mock_verify_oauth2_token)
    res = client.post("/api/auth/google", json={"credential": "mock.jwt.token"})
    assert res.status_code == 401
    assert "audience mismatch" in res.json()["detail"]


def test_google_auth_issuer_mismatch(monkeypatch):
    """Verify token is rejected when issuer is not accounts.google.com."""
    monkeypatch.setattr("server.GOOGLE_CLIENT_ID", "expected-client-id.apps.googleusercontent.com")
    monkeypatch.setattr("server.HAS_GOOGLE_AUTH", True)

    def mock_verify_oauth2_token(token, req, client_id):
        return {
            "iss": "https://evil-issuer.com",
            "aud": "expected-client-id.apps.googleusercontent.com",
            "email": "user@example.com",
            "email_verified": True
        }

    monkeypatch.setattr("server.google_id_token.verify_oauth2_token", mock_verify_oauth2_token)
    res = client.post("/api/auth/google", json={"credential": "mock.jwt.token"})
    assert res.status_code == 401
    assert "issuer mismatch" in res.json()["detail"]


def test_google_auth_unverified_email_rejected(monkeypatch):
    """Verify token is rejected when email_verified claim is False."""
    monkeypatch.setattr("server.GOOGLE_CLIENT_ID", "expected-client-id.apps.googleusercontent.com")
    monkeypatch.setattr("server.HAS_GOOGLE_AUTH", True)

    def mock_verify_oauth2_token(token, req, client_id):
        return {
            "iss": "https://accounts.google.com",
            "aud": "expected-client-id.apps.googleusercontent.com",
            "email": "unverified@example.com",
            "email_verified": False
        }

    monkeypatch.setattr("server.google_id_token.verify_oauth2_token", mock_verify_oauth2_token)
    res = client.post("/api/auth/google", json={"credential": "mock.jwt.token"})
    assert res.status_code == 401
    assert "not verified" in res.json()["detail"].lower()


def test_google_auth_missing_email_claim_rejected(monkeypatch):
    """Verify token is rejected when email claim is completely absent."""
    monkeypatch.setattr("server.GOOGLE_CLIENT_ID", "expected-client-id.apps.googleusercontent.com")
    monkeypatch.setattr("server.HAS_GOOGLE_AUTH", True)

    def mock_verify_oauth2_token(token, req, client_id):
        return {
            "iss": "https://accounts.google.com",
            "aud": "expected-client-id.apps.googleusercontent.com",
            "email_verified": True
        }

    monkeypatch.setattr("server.google_id_token.verify_oauth2_token", mock_verify_oauth2_token)
    res = client.post("/api/auth/google", json={"credential": "mock.jwt.token"})
    assert res.status_code == 401
    assert "no email" in res.json()["detail"].lower()


def test_google_auth_valid_session_and_logout_lifecycle(monkeypatch):
    """Verify full valid token verification, session creation, and secure logout."""
    test_email = "verified_tester@example.com"
    expected_cid = "expected-client-id.apps.googleusercontent.com"
    monkeypatch.setattr("server.GOOGLE_CLIENT_ID", expected_cid)
    monkeypatch.setattr("server.HAS_GOOGLE_AUTH", True)

    def mock_verify_oauth2_token(token, req, client_id):
        return {
            "iss": "https://accounts.google.com",
            "aud": expected_cid,
            "email": test_email,
            "email_verified": True,
            "name": "Verified Tester"
        }

    monkeypatch.setattr("server.google_id_token.verify_oauth2_token", mock_verify_oauth2_token)

    # 1. Successful authentication
    auth_res = client.post("/api/auth/google", json={"credential": "valid.google.token"})
    assert auth_res.status_code == 200
    body = auth_res.json()
    assert body["email"] == test_email
    assert "token" in body
    session_token = body["token"]

    # 2. Authenticated user can access /api/auth/me
    auth_client = TestClient(app)
    auth_client.headers["Authorization"] = f"Bearer {session_token}"
    me_res = auth_client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["authenticated"] is True
    assert me_res.json()["email"] == test_email

    # 3. Secure logout invalidates session in SQLite database
    logout_res = auth_client.post("/api/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.json()["authenticated"] is False

    # 4. Previously valid session token is now completely revoked
    revoked_res = auth_client.get("/api/auth/me")
    assert revoked_res.status_code == 401


def test_favicon_and_legal_routes():
    """Verify favicon and legal terms/privacy routes respond correctly."""
    # Favicon
    fav_res = client.get("/favicon.ico")
    assert fav_res.status_code == 200
    assert "svg" in fav_res.headers.get("content-type", "")

    # Legal routes
    privacy_res = client.get("/privacy")
    assert privacy_res.status_code == 200
    assert "text/html" in privacy_res.headers.get("content-type", "")
    assert "Paperplane" in privacy_res.text

    terms_res = client.get("/terms")
    assert terms_res.status_code == 200
    assert "text/html" in terms_res.headers.get("content-type", "")
    assert "Paperplane" in terms_res.text


def test_password_reset_lifecycle():
    """Verify complete password reset workflow: request, token consumption, single-use, and session invalidation."""
    email = f"reset_test_{os.urandom(4).hex()}@paperplane.test"
    pw_initial = "OldPassword123!"
    pw_new = "NewPassword456!"

    # 1. Register user
    reg = register_verified(client, email, pw_initial)
    initial_token = reg.json()["token"]

    # 2. Request password reset
    forgot_res = client.post("/api/auth/forgot-password", json={"email": email})
    assert forgot_res.status_code == 200
    body = forgot_res.json()
    assert "If an account exists" in body["message"]
    # In non-production, dev_reset_url is provided
    assert "dev_reset_url" in body
    dev_url = body["dev_reset_url"]
    assert "token=" in dev_url
    token = dev_url.split("token=")[-1]

    # 3. Test non-existent email gets identical generic response (anti-enumeration)
    fake_res = client.post("/api/auth/forgot-password", json={"email": "nonexistent_fake@example.com"})
    assert fake_res.status_code == 200
    assert "If an account exists" in fake_res.json()["message"]

    # 4. Attempt reset with invalid/tampered token
    bad_reset = client.post("/api/auth/reset-password", json={"token": "tampered_token_xyz", "new_password": pw_new})
    assert bad_reset.status_code == 400
    assert "invalid or expired" in bad_reset.json()["detail"].lower()

    # 5. Consume valid reset token
    reset_res = client.post("/api/auth/reset-password", json={"token": token, "new_password": pw_new})
    assert reset_res.status_code == 200
    assert "Password successfully reset" in reset_res.json()["message"]

    # 6. Attempting to reuse the consumed token fails (single use)
    reuse_res = client.post("/api/auth/reset-password", json={"token": token, "new_password": "AnotherPassword789!"})
    assert reuse_res.status_code == 400
    assert "invalid or expired" in reuse_res.json()["detail"].lower()

    # 7. Old password no longer works
    old_login = client.post("/api/auth/login", data={"email": email, "password": pw_initial})
    assert old_login.status_code == 401

    # 8. New password works successfully
    new_login = client.post("/api/auth/login", data={"email": email, "password": pw_new})
    assert new_login.status_code == 200
    assert "token" in new_login.json()


def test_user_change_password_endpoint():
    """Verify authenticated password change in Settings."""
    email = f"change_pw_{os.urandom(4).hex()}@paperplane.test"
    pw_old = "CurrentSecret123!"
    pw_new = "UpdatedSecret456!"

    reg = register_verified(client, email, pw_old)
    user_token = reg.json()["token"]

    auth_client = TestClient(app)
    auth_client.headers["Authorization"] = f"Bearer {user_token}"

    # 1. Unauthenticated change password -> 401
    unauth_client = TestClient(app)
    unauth_res = unauth_client.post("/api/user/change-password", json={"old_password": pw_old, "new_password": pw_new})
    assert unauth_res.status_code == 401

    # 2. Incorrect old password -> 400
    wrong_old = auth_client.post("/api/user/change-password", json={"old_password": "WrongOldPassword!", "new_password": pw_new})
    assert wrong_old.status_code == 400
    assert "incorrect current password" in wrong_old.json()["detail"].lower()

    # 3. Successful password change
    good_change = auth_client.post("/api/user/change-password", json={"old_password": pw_old, "new_password": pw_new})
    assert good_change.status_code == 200
    assert "Password updated successfully" in good_change.json()["message"]

    # 4. Verify login with updated password
    verify_login = client.post("/api/auth/login", data={"email": email, "password": pw_new})
    assert verify_login.status_code == 200


def test_swagger_api_docs_route():
    """Docs are available in development and absent from production."""
    from server import DISABLE_DOCS

    docs_res = client.get("/api-docs", follow_redirects=False)
    openapi_res = client.get("/openapi.json")
    if DISABLE_DOCS:
        assert docs_res.status_code in (301, 302, 307, 308)
        assert docs_res.headers["location"] == "/developers"
        assert openapi_res.status_code == 404
        redirected_docs = client.get("/api-docs")
        assert redirected_docs.status_code == 200
        docs_redirect = client.get("/docs", follow_redirects=False)
        assert docs_redirect.status_code in (301, 302, 307, 308)
        assert docs_redirect.headers["location"] == "/developers"
        return

    assert docs_res.status_code == 200
    assert "swagger" in docs_res.text.lower() or "openapi" in docs_res.text.lower()

    assert openapi_res.status_code == 200
    schema = openapi_res.json()
    assert "openapi" in schema
    assert "paths" in schema
    assert "/api/jobs/create" in schema["paths"]

    redirect_res = client.get("/docs", follow_redirects=False)
    assert redirect_res.status_code in (301, 302, 307, 308)
    assert redirect_res.headers["location"] == "/api-docs"


def test_public_api_docs_disabled_for_production_even_if_env_false():
    from server import _should_disable_docs

    assert _should_disable_docs("production", "false") is True
    assert _should_disable_docs("production", "true") is True
    assert _should_disable_docs("Prod", "true") is True
    assert _should_disable_docs("staging", None) is True
    assert _should_disable_docs("development", None) is True
    assert _should_disable_docs("development", "false") is True
    assert _should_disable_docs("development", "true") is False


def test_csp_does_not_allow_inline_script_execution():
    nginx = (Path(__file__).resolve().parents[1] / "deploy" / "nginx.conf.template").read_text(encoding="utf-8")
    policy_line = next(line for line in nginx.splitlines() if 'add_header Content-Security-Policy ' in line)
    policy = policy_line.split('add_header Content-Security-Policy "', 1)[1].split('" always;', 1)[0]
    script_policy = policy.split("style-src", 1)[0]
    assert "unsafe-inline" not in script_policy
    assert "wasm-unsafe-eval" in script_policy
    style_policy = policy.split("style-src", 1)[1].split("font-src", 1)[0]
    assert "unsafe-inline" in style_policy
    assert "https://accounts.google.com" in style_policy


def test_plan_limits_match_server_upload_limits():
    from server import MAX_FILE_SIZE, plan_limits_payload, upload_limit_bytes_for_tier

    limits = plan_limits_payload()
    assert limits["free_operations_per_day"] > 0
    assert limits["free_max_file_size_mb"] > 0
    assert limits["max_batch_files"] == 100
    assert upload_limit_bytes_for_tier("free") == min(
        MAX_FILE_SIZE, limits["free_max_file_size_mb"] * 1024 * 1024
    )
    assert upload_limit_bytes_for_tier("pro") == MAX_FILE_SIZE
    assert upload_limit_bytes_for_tier("developer") == MAX_FILE_SIZE


def test_auth_profile_exposes_the_authoritative_plan_limits():
    from server import plan_limits_payload

    anonymous_response = TestClient(app).get("/api/auth/me")
    assert anonymous_response.status_code == 401
    authenticated = register_verified(client, f"profile_{os.urandom(4).hex()}@paperplane.test", secrets.token_urlsafe(24))
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {authenticated.json()['token']}"})
    assert response.status_code == 200
    assert response.json()["plan_limits"] == plan_limits_payload()


def test_ai_capability_endpoint_hides_provider_details_and_reports_local_availability(monkeypatch):
    import ai_engine

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "")
    unavailable = client.get("/api/ai/capabilities")
    assert unavailable.status_code == 200
    assert unavailable.json() == {
        "executive_brief_available": False,
        "reason": "ai_service_not_configured",
    }

    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "test-only-key")
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", True)
    disabled = client.get("/api/ai/capabilities")
    assert disabled.status_code == 200
    assert disabled.json() == {
        "executive_brief_available": False,
        "reason": "ai_service_disabled",
    }

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    available = client.get("/api/ai/capabilities")
    assert available.status_code == 200
    assert available.json() == {"executive_brief_available": True, "reason": None}
    assert "provider" not in available.text.lower()
    assert "model" not in available.text.lower()


def test_free_job_upload_limit_returns_actionable_413(monkeypatch):
    """The UI-advertised free cap is enforced by the upload route."""
    import server

    monkeypatch.setattr(server, "FREE_TIER_MAX_FILE_SIZE_MB", 1)
    oversized_pdf = b"%PDF-1.7\n" + (b"x" * (1024 * 1024))
    response = client.post(
        "/api/jobs/create",
        data={"operation": "merge"},
        files={"files": ("oversized.pdf", oversized_pdf, "application/pdf")},
    )

    assert response.status_code == 413
    assert "1 MB" in response.json()["detail"]


def test_studio_pdf_header_validation():
    """Accept a valid PDF with a short preamble and reject corrupt lookalikes."""
    import fitz

    # Some valid PDFs contain a short preamble before the PDF header. Keep the
    # fixture structurally valid so the route also exercises its page parser.
    document = fitz.open()
    document.new_page()
    valid_pdf_content = b"% leading comment\r\n" + document.tobytes()
    document.close()
    
    inspect_res = client.post(
        "/api/studio/security/inspect",
        files={"file": ("test.pdf", valid_pdf_content, "application/pdf")}
    )
    assert inspect_res.status_code == 200
    assert "is_encrypted" in inspect_res.json()

    # A header marker without a readable PDF body must still be rejected.
    corrupt_pdf = b"%PDF-1.7\nnot a parseable PDF"
    corrupt_inspect = client.post(
        "/api/studio/security/inspect",
        files={"file": ("corrupt.pdf", corrupt_pdf, "application/pdf")},
    )
    assert corrupt_inspect.status_code == 422
    assert "damaged or unreadable" in corrupt_inspect.json()["detail"]

    # 2. Truly invalid content (missing %PDF- in first 1024 bytes) returns 422
    bad_content = b"THIS IS NOT A PDF FILE AT ALL"
    bad_inspect = client.post(
        "/api/studio/security/inspect",
        files={"file": ("fake.pdf", bad_content, "application/pdf")}
    )
    assert bad_inspect.status_code == 422
    assert "valid pdf" in bad_inspect.json()["detail"].lower()
