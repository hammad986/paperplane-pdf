import pytest
from pathlib import Path
import persistence
from persistence import init_db, add_waitlist_entry, get_waitlist_count
from email_service import send_login_notification, send_password_reset_email, send_password_changed_notification

def test_email_service_fallback(monkeypatch):
    """Ensure email notifications execute safely even when SMTP credentials are not configured."""
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setattr("email_service.RESEND_API_KEY", "")
    assert send_login_notification("test@paperplane.local", client_ip="127.0.0.1", user_agent="Mozilla/5.0") is True
    assert send_password_reset_email("test@paperplane.local", reset_token="mock123", base_url="http://localhost:8000") is True
    assert send_password_changed_notification("test@paperplane.local", client_ip="127.0.0.1") is True


def test_resend_api_dispatch(monkeypatch):
    """Ensure Resend REST API path is properly invoked when RESEND_API_KEY is configured."""
    dispatched = []

    class MockResponse:
        status = 200
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
