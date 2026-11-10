from __future__ import annotations

import io
import os
import json
import logging
import secrets
import sqlite3
import subprocess
import sys
from contextlib import closing
from io import StringIO
from pathlib import Path

import fitz
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

import ai_engine
import email_service
import persistence
import server
from scripts import backup_db


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/billing/checkout-session",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 1234),
            "query_string": b"",
            "root_path": "",
        }
    )


def _pdf_bytes(page_texts: list[str]) -> bytes:
    document = fitz.open()
    for text in page_texts:
        page = document.new_page()
        page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def test_persistence_health_reports_counts_and_resolved_database(tmp_path, monkeypatch):
    database = tmp_path / "health.sqlite3"
    monkeypatch.setattr(persistence, "DATABASE", database)
    persistence.init_db()
    user_id = persistence.create_user("health-probe@example.test", secrets.token_urlsafe(24))
    persistence.create_job("compress", user_id=user_id, ttl=3600)
    persistence.add_waitlist_entry("health-waitlist@example.test")
    persistence.create_api_key(user_id, "health probe")

    client = TestClient(server.app)
    assert client.get("/api/health/persistence").status_code == 401
    response = client.get(
        "/api/health/persistence",
        headers={"X-Admin-Session": persistence.create_admin_session()},
    )

    assert response.status_code == 200
    body = response.json()
    assert Path(body["database_path"]) == database.resolve()
    assert body["database_size_bytes"] > 0
    assert body["row_counts"]["users"] == 1
    assert body["row_counts"]["jobs"] == 1
    assert body["row_counts"]["api_keys"] == 1
    assert body["row_counts"]["app_waitlist"] == 1
    assert isinstance(body["database_on_mounted_volume"], bool)


def test_public_health_routes_do_not_disclose_filesystem_paths():
    client = TestClient(server.app)

    for path in ("/health", "/api/health"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert "jobs_directory" not in body
        assert str(server.JOBS) not in response.text


def test_backup_is_outside_database_and_restores_to_scratch(tmp_path, monkeypatch):
    database = tmp_path / "primary" / "paperplane.sqlite3"
    database.parent.mkdir()
    monkeypatch.setattr(persistence, "DATABASE", database)
    persistence.init_db()
    email = "backup-probe@example.test"
    password = secrets.token_urlsafe(24)
    persistence.create_user(email, password)

    backup_dir = tmp_path / "host-backups"
    backup = backup_db.backup_database(backup_dir)
    assert backup.exists()
    assert backup.parent == backup_dir
    assert backup.is_relative_to(tmp_path)
    assert not backup.is_relative_to(database.parent)

    scratch = tmp_path / "scratch-restore.sqlite3"
    with closing(sqlite3.connect(backup)) as source, closing(sqlite3.connect(scratch)) as target:
        source.backup(target)
    monkeypatch.setattr(persistence, "DATABASE", scratch)
    restored = persistence.get_user_by_email(email)
    assert restored is not None
    assert restored["email"] == email
    assert persistence.verify_user_credentials(email, password) is not None


def test_production_config_requires_a_stable_session_secret(tmp_path):
    env = os.environ.copy()
    for name in ("PAPERPLANE_SESSION_SECRET", "SESSION_SECRET_KEY", "JWT_SECRET", "TESTING"):
        env.pop(name, None)
    env["PAPERPLANE_SKIP_DOTENV"] = "1"
    env["PAPERPLANE_ENV"] = "production"
    env["PAPERPLANE_DATA_DIR"] = str(tmp_path / "isolated-data")
    env["PAPERPLANE_PUBLIC_URL"] = "https://paperplane.example.test"

    result = subprocess.run(
        [sys.executable, "-c", "import config"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode != 0
    assert "Production requires PAPERPLANE_SESSION_SECRET" in result.stderr


@pytest.mark.parametrize("public_url", ["", "http://paperplane.example.test", "https://localhost", "https://paperplane.local"])
def test_production_config_rejects_unusable_public_origins(tmp_path, public_url):
    env = os.environ.copy()
    env.pop("TESTING", None)
    env["PAPERPLANE_ENV"] = "production"
    env["PAPERPLANE_SESSION_SECRET"] = secrets.token_urlsafe(48)
    env["PAPERPLANE_PUBLIC_URL"] = public_url
    env["PAPERPLANE_DATA_DIR"] = str(tmp_path / f"origin-{secrets.token_hex(4)}")

    result = subprocess.run(
        [sys.executable, "-c", "import config"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode != 0
    assert "Production requires PAPERPLANE_PUBLIC_URL" in result.stderr


def test_cashfree_demo_activation_is_blocked_in_production_without_credentials(monkeypatch):
    user_id = persistence.create_user("billing-probe@example.test", secrets.token_urlsafe(24))
    monkeypatch.setattr(server, "CASHFREE_APP_ID", "")
    monkeypatch.setattr(server, "CASHFREE_SECRET_KEY", "")
    monkeypatch.setattr(server, "ENVIRONMENT", "production")
    monkeypatch.setattr(server, "ALLOW_BILLING_SIMULATION", False)

    with pytest.raises(HTTPException) as error:
        server.create_checkout_session(_request(), {"tier": "pro"}, user_id)

    assert error.value.status_code == 503
    assert persistence.get_user(user_id)["tier"] == "free"
    assert persistence.get_user(user_id)["cashfree_order_id"] is None


def test_cashfree_production_rejects_sandbox_gateway_even_with_credentials(monkeypatch):
    user_id = persistence.create_user("sandbox-prod-probe@example.test", secrets.token_urlsafe(24))
    monkeypatch.setattr(server, "CASHFREE_APP_ID", secrets.token_urlsafe(24))
    monkeypatch.setattr(server, "CASHFREE_SECRET_KEY", secrets.token_urlsafe(32))
    monkeypatch.setattr(server, "CASHFREE_ENV", "TEST")
    monkeypatch.setattr(server, "ENVIRONMENT", "production")
    monkeypatch.setattr(server, "ALLOW_BILLING_SIMULATION", False)
    attempted: list[str] = []
    monkeypatch.setattr(server, "_cashfree_request", lambda *args, **kwargs: attempted.append("called"))

    with pytest.raises(HTTPException) as error:
        server.create_checkout_session(_request(), {"tier": "pro"}, user_id)

    assert error.value.status_code == 503
    assert attempted == []
    assert persistence.get_user(user_id)["tier"] == "free"


def test_cashfree_demo_activation_requires_explicit_development_opt_in(monkeypatch):
    user_id = persistence.create_user("billing-dev-probe@example.test", secrets.token_urlsafe(24))
    monkeypatch.setattr(server, "CASHFREE_APP_ID", "")
    monkeypatch.setattr(server, "CASHFREE_SECRET_KEY", "")
    monkeypatch.setattr(server, "ENVIRONMENT", "development")
    monkeypatch.setattr(server, "ALLOW_BILLING_SIMULATION", True)

    result = server.create_checkout_session(_request(), {"tier": "pro"}, user_id)

    assert result["mode"] == "demo_activated"
    assert persistence.get_user(user_id)["tier"] == "pro"


def test_billing_simulation_defaults_off_in_development(tmp_path):
    env = os.environ.copy()
    env.pop("PAPERPLANE_ALLOW_BILLING_SIMULATION", None)
    env["PAPERPLANE_ENV"] = "development"
    env["PAPERPLANE_DATA_DIR"] = str(tmp_path / "runtime")
    env["PAPERPLANE_BACKUP_DIR"] = str(tmp_path / "backups")
    value = subprocess.check_output(
        [sys.executable, "-c", "import config; print(config.ALLOW_BILLING_SIMULATION)"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
    ).strip()

    assert value == "False"


def test_student_eligibility_uses_supported_academic_suffixes():
    for email in (
        "student@campus.edu",
        "student@university.ac.in",
        "student@college.edu.in",
        "student@university.ac.uk",
        "student@institute.ernet.in",
    ):
        assert persistence.is_educational_email(email)

    for email in (
        "student@research.res.in",
        "student@univ",
        "student@college",
        "student@school",
    ):
        assert not persistence.is_educational_email(email)


def test_settings_does_not_claim_an_unspecified_developer_quota():
    source = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "Developer API quotas are separate" not in source
    assert "Developer API quotas are separate" not in app_js


def test_studio_extract_toolbar_uses_selected_pages():
    source = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
    assert "window.PaperplanePageOrganizer.extractSelected()" in source
    assert "Extract selected pages as a PDF" in html


def test_studio_and_ai_docs_preserve_the_document_page_during_handoff():
    root = Path(__file__).resolve().parents[1]
    source = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    html = (root / "web" / "index.html").read_text(encoding="utf-8")

    assert 'id="studio-open-ai-btn"' in html
    assert 'id="ai-open-studio-btn"' in html
    assert 'id="ai-doc-page-context"' in html
    assert "$('#studio-open-ai-btn')?.addEventListener('click', () => openStudioDocumentInAiDocs())" in source
    assert "$('#ai-open-studio-btn')?.addEventListener('click', () => openAiDocumentInStudio())" in source
    assert "state.aiContextPage = Math.max(1, Number(state.studio.currentPage) || 1)" in source
    assert "loadDocumentIntoStudio(file, { initialPage: targetPage })" in source
    assert "await jumpToStudioPage(targetPage)" in source
    assert "data-ai-page=\"${pageNumber}\"" in source
    assert "state.aiContextPage = Math.max(1, Number(citation.dataset.aiPage) || 1)" in source
    assert "citations.innerHTML = (message.citations || []).map(aiPageCitationTag).join('')" in source


def test_developer_keys_work_with_both_headers_and_update_last_used():
    pdf = _pdf_bytes(["Paperplane developer key acceptance fixture"])
    client = TestClient(server.app)

    for index in range(2):
        user_id = persistence.create_user(
            f"developer-probe-{index}-{secrets.token_hex(3)}@example.test",
            secrets.token_urlsafe(24),
        )
        persistence.set_user_tier(user_id, tier="developer", status="active")
        key_id, api_key = persistence.create_api_key(user_id, f"local regression key {index}")

        for header_name in ("Authorization", "X-API-Key"):
            headers = (
                {"Authorization": f"Bearer {api_key}"}
                if header_name == "Authorization"
                else {"X-API-Key": api_key}
            )
            for _ in range(2):
                usage = client.get("/api/v1/account/usage", headers=headers)
                job = client.post(
                    "/api/v1/jobs",
                    headers=headers,
                    data={"operation": "compress"},
                    files={"files": ("probe.pdf", pdf, "application/pdf")},
                )
                assert usage.status_code == 200
                assert job.status_code == 202

        with closing(persistence.connect()) as connection:
            row = connection.execute(
                "SELECT key_prefix, last_used_at FROM api_keys WHERE id = ?",
                (key_id,),
            ).fetchone()
        assert row is not None
        assert row["key_prefix"].startswith("sk_live_")
        assert row["last_used_at"] is not None


def test_chat_with_attached_pdf_uses_context_without_phrase_gate(tmp_path, monkeypatch):
    source = tmp_path / "chat-qa.pdf"
    source.write_bytes(_pdf_bytes(["Hello PaperPlane QA alpha.", "Second page text beta."]))
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "")
    monkeypatch.setattr(ai_engine, "call_llm", lambda *args, **kwargs: pytest.fail("provider must be unavailable"))

    answer = ai_engine.chat_with_pdf(source, "What word is written on page two?")
    hey = ai_engine.chat_with_pdf(source, "hey")
    hello = ai_engine.chat_with_pdf(source, "hello")

    assert "beta" in answer["answer"].lower()
    assert answer["citations"] == [2]
    assert "hello!" in hey["answer"].lower()
    assert "hello!" in hello["answer"].lower()
    assert hey["citations"] == hello["citations"] == []


def test_stream_chat_uses_attached_pdf_without_phrase_gate(monkeypatch):
    pdf = _pdf_bytes(["Hello PaperPlane QA alpha.", "Second page text beta."])
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "")

    response = TestClient(server.app).post(
        "/api/ai/chat/stream",
        data={"question": "What word is written on page two?"},
        files={"file": ("chat-qa.pdf", pdf, "application/pdf")},
    )

    assert response.status_code == 200
    event_text = []
    for block in response.text.split("\n\n"):
        lines = block.splitlines()
        if len(lines) < 2 or lines[0] != "event: token" or not lines[1].startswith("data: "):
            continue
        event_text.append(json.loads(lines[1][6:])["text"])
    assert "Second page text beta." in "".join(event_text)
    assert '"citations": [2]' in response.text
    assert '"message": "AI provider is not configured"' not in response.text


def test_citations_normalize_nested_and_duplicate_markup():
    text, chips = ai_engine.align_answer_citations("Fact [[Page 2]] [Page 2].", [2])

    assert text == "Fact [Page 2]."
    assert chips == [2]


def test_false_author_claim_uses_document_text_or_states_uncertainty(tmp_path):
    source = tmp_path / "author-qa.pdf"
    source.write_bytes(_pdf_bytes(["Author: Jane Doe."]))

    correction = ai_engine.correct_false_premise(source, "Was this written by Albert Einstein?")

    assert correction is not None
    assert "Jane Doe" in correction
    assert "Albert Einstein" in correction

    unattributed = tmp_path / "unattributed.pdf"
    unattributed.write_bytes(_pdf_bytes(["A technical note without author information."]))
    uncertain = ai_engine.correct_false_premise(unattributed, "Was this written by Albert Einstein?")
    assert uncertain is not None
    assert "can't verify" in uncertain


def test_password_reset_email_does_not_report_simulated_success(monkeypatch):
    monkeypatch.setattr(email_service, "SMTP_ENABLED", False)
    monkeypatch.setattr(email_service, "SMTP_HOST", "")
    monkeypatch.setattr(email_service, "RESEND_API_KEY", "")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger = email_service.logger
    previous_handlers = logger.handlers[:]
    previous_level = logger.level
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    reset_token = secrets.token_urlsafe(32)
    try:
        delivered = email_service.send_password_reset_email(
            "qa-reset@example.test", reset_token, "https://paperplane.example.test"
        )
        log = stream.getvalue().lower()
    finally:
        logger.handlers = previous_handlers
        logger.setLevel(previous_level)
        handler.close()
    assert delivered is False
    assert "simulated" not in log
    assert "transactional email was not delivered" in log
    assert reset_token not in log


def test_forgot_password_uses_configured_public_url(monkeypatch):
    email = f"reset-url-{secrets.token_hex(4)}@example.test"
    persistence.create_user(email, secrets.token_urlsafe(24))
    monkeypatch.setattr(server, "PAPERPLANE_PUBLIC_URL", "https://paperplane.example.test")
    captured: list[str | None] = []
    monkeypatch.setattr(
        server,
        "send_password_reset_email",
        lambda _email, _token, base_url=None: captured.append(base_url) or False,
    )

    response = TestClient(server.app).post("/api/auth/forgot-password", json={"email": email})

    assert response.status_code == 200
    assert "has been dispatched" not in response.json()["message"]
    assert captured == ["https://paperplane.example.test"]


def test_resend_keeps_both_unexpired_otp_codes_valid():
    for index in range(2):
        email = f"overlap-{index}-{secrets.token_hex(4)}@example.test"
        older = persistence.create_email_otp(email, "signup", {"challenge": "shared"})
        newer = persistence.create_email_otp(email, "signup", None)

        assert persistence.verify_email_otp(email, "signup", older) == {"challenge": "shared"}
        assert persistence.verify_email_otp(email, "signup", newer) == {"challenge": "shared"}

