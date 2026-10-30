import os
import uuid
import pytest
from fastapi.testclient import TestClient

from server import app
import persistence
from persistence import init_db, get_user_by_email, verify_email_otp, create_email_otp, can_resend_otp
import email_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_auth_otp.db"
    monkeypatch.setattr(persistence, "DATABASE", test_db)
    monkeypatch.setenv("TESTING", "True")
    init_db()


def test_registration_password_mismatch():
    res = client.post("/api/auth/register", data={
        "email": "mismatch@example.com",
        "password": "Password123!",
        "confirm_password": "DifferentPassword123!"
    })
    assert res.status_code == 400
    assert "Passwords do not match" in res.text


def test_registration_short_password():
    res = client.post("/api/auth/register", data={
        "email": "short@example.com",
        "password": "short",
        "confirm_password": "short"
    })
    assert res.status_code == 400
    assert "at least 8 characters" in res.text


def test_registration_otp_flow(monkeypatch):
    email = f"signup_{uuid.uuid4().hex[:6]}@example.com"
    pw = "SecurePassword123!"

    sent_emails = []
    def fake_send_otp(to_email, code, purpose):
        sent_emails.append({"to": to_email, "code": code, "purpose": purpose})
        return True

    login_notifications = []
    def fake_send_login_notice(to_email, client_ip="Unknown", user_agent=""):
        login_notifications.append({"to": to_email, "ip": client_ip, "ua": user_agent})
        return True

    monkeypatch.setattr(email_service, "send_otp_email", fake_send_otp)
    monkeypatch.setattr(email_service, "send_login_notification", fake_send_login_notice)

    # 1. Request signup with OTP
    reg_res = client.post("/api/auth/register", data={
        "email": email,
        "password": pw,
        "confirm_password": pw,
        "require_otp": "1"
    })
    assert reg_res.status_code == 200
    reg_json = reg_res.json()
    assert reg_json["status"] == "otp_required"
    assert reg_json["email"] == email
    assert reg_json["purpose"] == "signup"
    assert "dev_otp" in reg_json

    otp_code = reg_json["dev_otp"]
    assert len(otp_code) == 6

    # Verify user does not exist in DB yet
    assert get_user_by_email(email) is None

    # 2. Try invalid OTP
    bad_verify = client.post("/api/auth/verify-signup-otp", json={
        "email": email,
        "otp": "000000"
    })
    assert bad_verify.status_code == 400

    # 3. Submit valid OTP
    good_verify = client.post("/api/auth/verify-signup-otp", json={
        "email": email,
        "otp": otp_code
    })
    assert good_verify.status_code == 200
    verify_json = good_verify.json()
    assert verify_json["status"] == "success"
    assert verify_json["email"] == email
    assert "token" in verify_json
    assert "user_id" in verify_json

    # User now exists
    user_in_db = get_user_by_email(email)
    assert user_in_db is not None
    assert user_in_db["email"] == email


def test_login_otp_flow(monkeypatch):
    email = f"user_{uuid.uuid4().hex[:6]}@example.com"
    pw = "SuperSecretPassword123!"

    login_notices = []
    def fake_send_login_notice(to_email, client_ip="Unknown", user_agent=""):
        login_notices.append({"to": to_email, "ip": client_ip, "ua": user_agent})
        return True

    monkeypatch.setattr(email_service, "send_login_notification", fake_send_login_notice)

    # Create user first directly
    persistence.create_user(email, pw)

    # 1. Try login with wrong password
    bad_login = client.post("/api/auth/login", data={
        "email": email,
        "password": "WrongPassword123!",
        "require_otp": "1"
    })
    assert bad_login.status_code == 401

    # 2. Login with correct password requesting OTP
    req_res = client.post("/api/auth/login", data={
        "email": email,
        "password": pw,
        "require_otp": "1"
    })
    assert req_res.status_code == 200
    req_json = req_res.json()
    assert req_json["status"] == "otp_required"
    assert req_json["email"] == email
    assert req_json["purpose"] == "login"
    otp_code = req_json["dev_otp"]

    # 3. Verify OTP
    verify_res = client.post("/api/auth/verify-login-otp", json={
        "email": email,
        "otp": otp_code
    })
    assert verify_res.status_code == 200
    verify_json = verify_res.json()
    assert verify_json["status"] == "success"
    assert verify_json["email"] == email
    assert "token" in verify_json


def test_resend_otp_cooldown():
    email = f"resend_{uuid.uuid4().hex[:6]}@example.com"
    # Create initial OTP
    create_email_otp(email, "login")

    # Immediate resend within 60s should be rate limited (429)
    res = client.post("/api/auth/resend-otp", json={
        "email": email,
        "purpose": "login"
    })
    assert res.status_code == 429
    assert "seconds before requesting a new code" in res.text


def test_direct_auth_backward_compatibility():
    email = f"direct_{uuid.uuid4().hex[:6]}@example.com"
    pw = "DirectPassword123!"

    # Direct register
    reg = client.post("/api/auth/register", data={"email": email, "password": pw})
    assert reg.status_code == 200
    assert "token" in reg.json()

    # Direct login
    log = client.post("/api/auth/login", data={"email": email, "password": pw})
    assert log.status_code == 200
    assert "token" in log.json()


def test_dev_otp_never_leaked_in_production(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    email = f"prod_{uuid.uuid4().hex[:6]}@example.com"
    pw = "SuperSecurePass123!"

    # Registration
    reg = client.post("/api/auth/register", data={
        "email": email,
        "password": pw,
        "confirm_password": pw,
        "require_otp": "1"
    })
    assert reg.status_code == 200
    reg_json = reg.json()
    assert reg_json["status"] == "otp_required"
    assert "dev_otp" not in reg_json

    # Pre-create user for login test
    persistence.create_user(email, pw)
    log = client.post("/api/auth/login", data={
        "email": email,
        "password": pw,
        "require_otp": "1"
    })
    assert log.status_code == 200
    log_json = log.json()
    assert log_json["status"] == "otp_required"
    assert "dev_otp" not in log_json
