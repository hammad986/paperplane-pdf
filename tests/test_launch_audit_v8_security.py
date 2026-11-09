from __future__ import annotations

import sqlite3
import secrets

import pytest
from fastapi.testclient import TestClient

import persistence
import server


@pytest.fixture
def isolated_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", tmp_path / "launch_audit_v8_security.db")
    monkeypatch.setattr(server, "JOBS", tmp_path / "jobs")
    monkeypatch.setenv("TESTING", "True")
    persistence.init_db()
    return server.JOBS


def _complete_job(job_id: str, jobs_dir, content: bytes = b"test pdf bytes") -> None:
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "result.pdf").write_bytes(content)
    persistence.update_job(job_id, status="completed", progress=100, output_name="result.pdf", output_size=len(content))


def test_registration_accepts_json_but_stays_pending_until_otp(isolated_jobs):
    client = TestClient(server.app)
    email = f"json-register-{secrets.token_hex(6)}@example.test"
    password = secrets.token_urlsafe(24)

    registration = client.post("/api/auth/register", json={"email": email, "password": password})
    assert registration.status_code == 200
    assert registration.json()["status"] == "otp_required"
    assert "paperplane_token" not in registration.cookies
    assert client.get("/api/auth/me").status_code == 401

    verification = client.post("/api/auth/verify-signup-otp", json={
        "email": email,
        "otp": registration.json()["dev_otp"],
    })
    assert verification.status_code == 200
    assert verification.json().get("token")
    assert client.get("/api/auth/me").status_code == 200


def test_job_access_is_owner_scoped_and_guest_capabilities_are_single_use(isolated_jobs):
    user_a = persistence.create_user("owner-a@example.test", secrets.token_urlsafe(24))
    user_b = persistence.create_user("owner-b@example.test", secrets.token_urlsafe(24))
    owner_session = persistence.create_session_for_user(user_a)
    user_job_id, user_job_guest_token = persistence.create_job("compress", user_a, ttl=3600)
    assert user_job_guest_token is None
    _complete_job(user_job_id, isolated_jobs, b"owner-only-result")

    owner_client = TestClient(server.app)
    owner_client.headers["Authorization"] = f"Bearer {owner_session['token']}"
    own_status = owner_client.get(f"/api/jobs/{user_job_id}")
    assert own_status.status_code == 200
    assert "guest_token" not in own_status.json()
    assert "user_id" not in own_status.json()
    own_download = owner_client.get(f"/api/jobs/{user_job_id}/download")
    assert own_download.status_code == 200
    assert own_download.content == b"owner-only-result"

    anonymous = TestClient(server.app)
    other_session = persistence.create_session_for_user(user_b)
    other = TestClient(server.app)
    other.headers["Authorization"] = f"Bearer {other_session['token']}"
    for client in (anonymous, other):
        assert client.get(f"/api/jobs/{user_job_id}").status_code == 404
        assert client.get(f"/api/jobs/{user_job_id}/download?token=guessed").status_code == 404
        assert client.delete(f"/api/jobs/{user_job_id}?token=guessed").status_code == 404

    ownerless_id = "legacy-ownerless-v8"
    with sqlite3.connect(persistence.DATABASE) as connection:
        connection.execute(
            "INSERT INTO jobs (id, user_id, guest_token, operation, status, created_at, expires_at) "
            "VALUES (?, NULL, NULL, 'compress', 'completed', 0, 9999999999)",
            (ownerless_id,),
        )
    assert persistence.get_job(ownerless_id) is None
    assert anonymous.get(f"/api/jobs/{ownerless_id}").status_code == 404
    assert anonymous.get(f"/api/jobs/{ownerless_id}/download").status_code == 404
    assert anonymous.delete(f"/api/jobs/{ownerless_id}").status_code == 404

    guest_job_id, guest_token = persistence.create_job("compress", None, ttl=3600)
    assert guest_token
    _complete_job(guest_job_id, isolated_jobs, b"guest-result")
    guest = TestClient(server.app)
    guest.headers["X-Guest-Token"] = guest_token
    guest_status = guest.get(f"/api/jobs/{guest_job_id}")
    assert guest_status.status_code == 200
    assert "guest_token" not in guest_status.json()
    assert guest.get(f"/api/jobs/{guest_job_id}/download").content == b"guest-result"
    assert guest.get(f"/api/jobs/{guest_job_id}/download").status_code == 404

    query_only = TestClient(server.app)
    assert query_only.get(f"/api/jobs/{guest_job_id}?token={guest_token}").status_code == 404
