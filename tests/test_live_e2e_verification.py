import io
import time
import uuid
import re
import pytest
from fastapi.testclient import TestClient

from server import app
import persistence
from persistence import init_db, connect, get_user_by_email
import fitz

client = TestClient(app)


def test_e2e_html_structure_and_dom_elements():
    """Verify that all UI elements for OTP auth and AI Studio exist in the served HTML."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    # 1. Auth Modal & Confirm Password
    assert 'id="auth-modal"' in html
    assert 'id="auth-confirm-password-row"' in html
    assert 'id="auth-confirm-password"' in html
    assert 'id="confirm-password-toggle-btn"' in html

    # 2. OTP Verification Pane
    assert 'id="auth-otp-pane"' in html
    assert 'id="auth-otp-code"' in html
    assert 'id="auth-otp-email-display"' in html
    assert 'id="btn-resend-otp"' in html
    assert 'id="otp-countdown"' in html
    assert 'id="auth-otp-back-btn"' in html

    # 3. AI Intelligence Studio View
    assert 'id="tab-ai-view"' in html
    assert 'id="view-ai-studio"' in html
    assert 'id="ai-test-connection-btn"' in html
    assert 'id="chat-form"' in html
    assert 'id="chat-input"' in html
    assert 'id="trigger-summary-btn"' in html
    assert 'id="trigger-extract-btn"' in html


def test_e2e_otp_signup_and_login_lifecycle(tmp_path, monkeypatch):
    """Full lifecycle test of OTP-based registration, login, and security alerts."""
    test_db = tmp_path / "test_e2e_auth.db"
    monkeypatch.setattr(persistence, "DATABASE", test_db)
    monkeypatch.setenv("TESTING", "True")
    init_db()

    email = f"e2e_user_{uuid.uuid4().hex[:6]}@example.com"
    pw = "SuperSecurePass123!"

    # 1. Attempt register with mismatched passwords
    res = client.post("/api/auth/register", data={
        "email": email,
        "password": pw,
        "confirm_password": "WrongPassword123!",
        "require_otp": "1"
    })
    assert res.status_code == 400
    assert "Passwords do not match" in res.json().get("detail", "")

    # 2. Register with valid matching password -> triggers OTP
    res = client.post("/api/auth/register", data={
        "email": email,
        "password": pw,
        "confirm_password": pw,
        "require_otp": "1"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "otp_required"
    assert data["email"] == email
    assert data["purpose"] == "signup"
    dev_otp = data.get("dev_otp")
    assert dev_otp is not None and len(dev_otp) == 6

    # Verify user does not exist yet
    assert get_user_by_email(email) is None

    # 3. Verify with invalid OTP -> fails
    res = client.post("/api/auth/verify-signup-otp", json={
        "email": email,
        "otp": "999999"
    })
    assert res.status_code == 400
    assert "Invalid or expired" in res.json().get("detail", "")

    # 4. Verify with valid OTP -> succeeds and issues session token
    res = client.post("/api/auth/verify-signup-otp", json={
        "email": email,
        "otp": dev_otp
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "token" in data
    assert data["email"] == email
    auth_token = data["token"]

    # User is now in DB
    user = get_user_by_email(email)
    assert user is not None

    # Check authenticated profile
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
    assert me_res.status_code == 200
    assert me_res.json()["authenticated"] is True
    assert me_res.json()["email"] == email

    # 5. Attempt Login with invalid password -> fails with 401
    bad_login = client.post("/api/auth/login", data={
        "email": email,
        "password": "IncorrectPassword123!",
        "require_otp": "1"
    })
    assert bad_login.status_code == 401

    # 6. Login with correct password -> triggers 2FA OTP
    login_res = client.post("/api/auth/login", data={
        "email": email,
        "password": pw,
        "require_otp": "1"
    })
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["status"] == "otp_required"
    assert login_data["purpose"] == "login"
    login_otp = login_data.get("dev_otp")
    assert login_otp is not None and len(login_otp) == 6

    # 7. Resend OTP immediately -> throttled by 60s cooldown (429)
    resend_fail = client.post("/api/auth/resend-otp", json={
        "email": email,
        "purpose": "login"
    })
    assert resend_fail.status_code == 429
    assert "seconds before requesting a new code" in resend_fail.json().get("detail", "")

    # 8. Complete 2FA login verification
    verify_login = client.post("/api/auth/verify-login-otp", json={
        "email": email,
        "otp": login_otp
    })
    assert verify_login.status_code == 200
    new_token = verify_login.json()["token"]
    assert new_token is not None


def test_e2e_ai_features_with_sample_document(tmp_path):
    """Test AI test-connection, chat, summarize, and extract endpoints."""
    # 1. Diagnostic test-connection endpoint
    conn_res = client.get("/api/ai/test-connection")
    assert conn_res.status_code == 200
    conn_data = conn_res.json()
    assert "status" in conn_data
    assert "fallback_active" in conn_data

    # 2. Build a test PDF document
    test_pdf = tmp_path / "apollo_brief.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Mission Apollo 2026\n"
        "Budget: $4,500,000 USD\n"
        "Lead Director: Dr. Sarah Connor\n"
        "Launch Window: December 15, 2026\n"
        "Primary Payload: Atmospheric Orbital Spectrometer"
    )
    doc.save(str(test_pdf))
    doc.close()

    # 3. Test /api/ai/chat
    with open(test_pdf, "rb") as f:
        chat_res = client.post(
            "/api/ai/chat",
            files={"file": ("apollo_brief.pdf", f, "application/pdf")},
            data={"question": "What is the mission budget and who is the lead director?"}
        )
    assert chat_res.status_code == 200
    chat_json = chat_res.json()
    assert "answer" in chat_json
    assert "4,500,000" in chat_json["answer"] or "Sarah Connor" in chat_json["answer"]
    assert 1 in chat_json["citations"]

    # 4. Test /api/ai/summarize
    with open(test_pdf, "rb") as f:
        summary_res = client.post(
            "/api/ai/summarize",
            files={"file": ("apollo_brief.pdf", f, "application/pdf")}
        )
    assert summary_res.status_code == 200
    summary_json = summary_res.json()
    assert summary_json["status"] == "success"
    assert "Apollo" in summary_json["summary"]

    # 5. Test /api/ai/extract
    with open(test_pdf, "rb") as f:
        extract_res = client.post(
            "/api/ai/extract",
            files={"file": ("apollo_brief.pdf", f, "application/pdf")},
            data={"doc_type": "auto"}
        )
    assert extract_res.status_code == 200
    extract_json = extract_res.json()
    assert extract_json["status"] == "success"
    assert "data" in extract_json
