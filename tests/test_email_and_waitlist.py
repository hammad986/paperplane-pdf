import pytest
import io
import urllib.error
from pathlib import Path
import persistence
import email_service
from persistence import init_db, add_waitlist_entry, get_waitlist_count
from email_service import send_login_notification, send_password_reset_email, send_password_changed_notification


def test_transactional_dispatch_rejects_consumer_sender_even_with_provider(monkeypatch):
    monkeypatch.setattr(email_service, "SMTP_FROM_EMAIL", "owner@gmail.com")
    monkeypatch.setattr(email_service, "RESEND_API_KEY", "re_test_mock_key")
    monkeypatch.setattr(email_service, "SMTP_ENABLED", True)
    monkeypatch.setattr(email_service, "SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(email_service, "_send_resend_api", lambda *args: pytest.fail("must not dispatch"))
    monkeypatch.setattr(email_service, "_send_smtp", lambda *args: pytest.fail("must not dispatch"))

    assert email_service._dispatch_email("owner@gmail.com", "OTP", "<p>code</p>", "code", allow_simulated=True) is False


def test_transactional_dispatch_prefers_resend_before_smtp(monkeypatch):
    monkeypatch.setattr(email_service, "SMTP_FROM_EMAIL", "security@paperplane.example")
    monkeypatch.setattr(email_service, "RESEND_API_KEY", "re_test_mock_key")
    monkeypatch.setattr(email_service, "SMTP_ENABLED", True)
    monkeypatch.setattr(email_service, "SMTP_HOST", "smtp.example.test")
    calls = []
    monkeypatch.setattr(email_service, "_send_resend_api", lambda *args: calls.append("resend") or True)
    monkeypatch.setattr(email_service, "_send_smtp", lambda *args: calls.append("smtp") or True)

    assert email_service._dispatch_email("user@example.test", "OTP", "<p>code</p>", "code") is True
    assert calls == ["resend"]

def test_email_service_fallback(monkeypatch):
    """No transactional notification claims delivery without a configured provider."""
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setattr("email_service.RESEND_API_KEY", "")
    assert send_login_notification("test@paperplane.local", client_ip="127.0.0.1", user_agent="Mozilla/5.0") is False
    assert send_password_reset_email("test@paperplane.local", reset_token="mock123", base_url="http://localhost:8000") is False
    assert send_password_changed_notification("test@paperplane.local", client_ip="127.0.0.1") is False


def test_password_reset_email_matches_30_minute_token_lifetime(monkeypatch):
    captured = {}

    def capture(to_email, subject, html_body, text_body, **kwargs):
        captured.update(html=html_body, text=text_body)
        return True

    monkeypatch.setattr(email_service, "_dispatch_email", capture)
    assert send_password_reset_email("user@example.test", "safe-token", "https://paperplane.example.test")
    assert "valid for 30 minutes" in captured["text"]
    assert "expires in 30 minutes" in captured["html"]
    assert "60 minutes" not in captured["html"]


def test_resend_api_dispatch(monkeypatch):
    """Ensure Resend REST API path is properly invoked when RESEND_API_KEY is configured."""
    dispatched = []

    class MockResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_value, traceback):
            return False
        def read(self):
            return b'{"id": "re_12345"}'

    def mock_urlopen(req, timeout=10):
        dispatched.append({
            "url": req.full_url,
            "headers": dict(req.headers),
            "data": req.data.decode("utf-8")
        })
        return MockResponse()

    monkeypatch.setattr("email_service.RESEND_API_KEY", "re_test_mock_key")
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    res = send_login_notification("user@example.com", client_ip="192.168.1.1", user_agent="Chrome/120")
    assert res is True
    assert len(dispatched) == 1
    assert dispatched[0]["url"] == "https://api.resend.com/emails"
    assert "Bearer re_test_mock_key" in dispatched[0]["headers"]["Authorization"]
    assert "user@example.com" in dispatched[0]["data"]

def test_waitlist_persistence(tmp_path, monkeypatch):
    """Ensure app waitlist correctly tracks registrations and numbers."""
    db_path = tmp_path / "test_waitlist.db"
    monkeypatch.setattr(persistence, "DATABASE", db_path)
    init_db()

    initial_count = get_waitlist_count()
    assert initial_count == 0

    # Add entry 1
    res1 = add_waitlist_entry("dev1@example.com", platform="windows", ip_address="127.0.0.1")
    assert res1["status"] == "success"
    assert res1["waitlist_position"] == 1
    assert get_waitlist_count() == 1

    # Add entry 2
    res2 = add_waitlist_entry("dev2@example.com", platform="macos", ip_address="127.0.0.1")
    assert res2["status"] == "success"
    assert res2["waitlist_position"] == 2
    assert get_waitlist_count() == 2

    # Duplicate email should return existing id
    res1_dup = add_waitlist_entry("dev1@example.com", platform="linux", ip_address="127.0.0.1")
    assert res1_dup["status"] == "success"
    assert res1_dup["waitlist_position"] == 1
    assert get_waitlist_count() == 2


def test_resend_retries_transient_failures_with_bounded_backoff_without_logging_recipient_or_otp(monkeypatch, caplog):
    attempts = []
    sleeps = []

    class MockResponse:
        status = 202
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    def flaky_urlopen(req, timeout=10):
        attempts.append((req, timeout))
        if len(attempts) < 3:
            raise urllib.error.HTTPError(req.full_url, 429 if len(attempts) == 1 else 503, "transient", {}, io.BytesIO(b"provider details"))
        return MockResponse()

    monkeypatch.setattr(email_service, "SMTP_FROM_EMAIL", "security@paperplane.example")
    monkeypatch.setattr(email_service, "RESEND_API_KEY", "test-key-never-log")
    monkeypatch.setattr(email_service.time, "sleep", sleeps.append)
    monkeypatch.setattr("urllib.request.urlopen", flaky_urlopen)
    with caplog.at_level("WARNING", logger="paperplane.email"):
        assert email_service._send_resend_api("person@example.test", "OTP", "<p>654321</p>", "654321") is True
    assert len(attempts) == 3
    assert sleeps == [0.25, 0.75]
    assert "person@example.test" not in caplog.text
    assert "654321" not in caplog.text
    assert "test-key-never-log" not in caplog.text


def test_resend_does_not_retry_permanent_sender_or_request_errors(monkeypatch):
    attempts = []
    def reject_urlopen(req, timeout=10):
        attempts.append(req)
        raise urllib.error.HTTPError(req.full_url, 400, "invalid sender", {}, io.BytesIO(b"do not leak details"))
    monkeypatch.setattr(email_service, "SMTP_FROM_EMAIL", "security@paperplane.example")
    monkeypatch.setattr(email_service, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr("urllib.request.urlopen", reject_urlopen)
    monkeypatch.setattr(email_service.time, "sleep", lambda _delay: pytest.fail("permanent errors must not retry"))
    assert email_service._send_resend_api("person@example.test", "OTP", "<p>x</p>", "x") is False
    assert len(attempts) == 1


def test_otp_dispatch_never_reports_simulated_delivery_success(monkeypatch):
    monkeypatch.setattr(email_service, "RESEND_API_KEY", "")
    monkeypatch.setattr(email_service, "SMTP_ENABLED", False)
    monkeypatch.setattr(email_service, "SMTP_HOST", "")
    monkeypatch.setattr(email_service, "SMTP_FROM_EMAIL", "security@paperplane.example")
    assert email_service.send_otp_email("person@example.test", "123456", "login") is False
