from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.request import Request as URLRequest

import fitz
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import ai_engine
import converters
import persistence
import server


def _http_request() -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/billing/checkout-session",
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 1234),
        "query_string": b"",
        "root_path": "",
    })


def _pdf_bytes(text: str = "Synthetic audit page") -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def test_invalid_cashfree_environment_fails_closed_without_test_fallback(tmp_path):
    env = os.environ.copy()
    env.update({
        "PAPERPLANE_SKIP_DOTENV": "1",
        "PAPERPLANE_DATA_DIR": str(tmp_path / "cashfree-invalid-env"),
        "CASHFREE_ENV": "invalid-mode",
    })
    env.pop("TESTING", None)
    result = subprocess.run(
        [sys.executable, "-c", "import config; assert config.CASHFREE_ENV == 'INVALID'; assert config.CASHFREE_BASE_URL == ''"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert "must be TEST/SANDBOX or PROD" in result.stderr
    assert "sandbox.cashfree.com" not in result.stdout + result.stderr


def test_cashfree_sandbox_alias_uses_only_the_cashfree_sandbox_host(tmp_path):
    env = os.environ.copy()
    env.update({
        "PAPERPLANE_SKIP_DOTENV": "1",
        "PAPERPLANE_DATA_DIR": str(tmp_path / "cashfree-sandbox-alias"),
        "PAPERPLANE_ENV": "development",
        "CASHFREE_ENV": "sandbox",
    })
    result = subprocess.run(
        [sys.executable, "-c", "import config; assert config.CASHFREE_ENV == 'TEST'; assert config.CASHFREE_BASE_URL == 'https://sandbox.cashfree.com/pg'; assert not config.CASHFREE_ENV_CONFIG_ERROR"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0


def test_invalid_cashfree_environment_returns_graceful_503(monkeypatch):
    user_id = persistence.create_user(f"billing-{secrets.token_hex(4)}@example.test", secrets.token_urlsafe(24))
    monkeypatch.setattr(server, "CASHFREE_ENV_CONFIG_ERROR", True)
    monkeypatch.setattr(server, "ENVIRONMENT", "production")

    with pytest.raises(server.HTTPException) as error:
        server.create_checkout_session(_http_request(), {"tier": "pro"}, user_id)

    assert error.value.status_code == 503
    assert error.value.detail == "Payments are temporarily unavailable. Please try again later."
    assert persistence.get_user(user_id)["tier"] == "free"


def test_signup_resend_explains_and_enforces_latest_code_only(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", tmp_path / "resend-latest-only.db")
    monkeypatch.setenv("TESTING", "True")
    monkeypatch.setattr(server, "can_resend_otp", lambda email, purpose, cooldown=60: (True, 0))
    monkeypatch.setattr(server, "deliver_otp_or_raise", lambda *args, **kwargs: None)
    persistence.init_db()
    email = "resend-check@example.test"
    previous_code = persistence.create_email_otp(email, "signup", None)

    with TestClient(server.app) as client:
        response = client.post("/api/auth/resend-otp", json={"email": email, "purpose": "signup"})

    assert response.status_code == 200
    result = response.json()
    assert "Any previous code is now invalid" in result["message"]
    assert persistence.verify_email_otp(email, "signup", previous_code) is None
    assert persistence.verify_email_otp(email, "signup", result["dev_otp"]) is not None


def test_admin_ai_health_is_protected_and_does_not_return_credentials(monkeypatch):
    monkeypatch.setattr(ai_engine, "_runtime_ai_config", lambda: {
        "provider": "openrouter", "model": "synthetic-model", "api_key": "",
    })
    client = TestClient(server.app)

    assert client.get("/api/admin/ai-health").status_code == 401
    response = client.get(
        "/api/admin/ai-health",
        headers={"X-Admin-Session": persistence.create_admin_session()},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "configuration_missing"
    assert body["configured"] is False
    assert "api_key" not in body
    assert "synthetic-model" not in response.text


def test_admin_lockout_status_ignores_untrusted_forwarded_for():
    actual_locked_ip = "198.51.100.42"
    unrelated_ip = "198.51.100.43"
    persistence.record_admin_failed_attempt(actual_locked_ip)
    persistence.record_admin_failed_attempt(actual_locked_ip)
    persistence.record_admin_failed_attempt(actual_locked_ip)

    client_locked = TestClient(server.app, client=(actual_locked_ip, 50100))
    response_locked = client_locked.get(
        "/api/admin/auth/status",
        headers={"X-Forwarded-For": unrelated_ip},
    )
    client_unrelated = TestClient(server.app, client=(unrelated_ip, 50101))
    response_unrelated = client_unrelated.get(
        "/api/admin/auth/status",
        headers={"X-Forwarded-For": actual_locked_ip},
    )

    assert response_locked.status_code == 200
    assert response_locked.json()["locked"] is True
    assert response_unrelated.status_code == 200
    assert response_unrelated.json()["locked"] is False
    assert "ip" not in response_locked.json()


def test_compose_trusts_only_the_static_nginx_peer_for_forwarded_headers():
    root = Path(__file__).resolve().parents[1]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    server_source = (root / "server.py").read_text(encoding="utf-8")

    assert "PAPERPLANE_TRUSTED_PROXY_HOSTS" in compose
    assert "PAPERPLANE_PROXY_NGINX_IP:-172.30.250.2" in compose
    assert "name: paperplane-pdf" in compose
    assert "PAPERPLANE_DATA_VOLUME_NAME:-paperplane-pdf_paperplane_data" in compose
    assert "paperplane_backups:/backups" in compose
    assert "PAPERPLANE_BACKUP_VOLUME_NAME:-paperplane-pdf_paperplane_backups" in compose
    assert 'trusted_hosts=TRUSTED_PROXY_HOSTS' in server_source
    assert 'trusted_hosts="*"' not in server_source


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin",
    "http://[::1]/admin",
    "http://169.254.169.254/latest/meta-data/",
    "http://metadata.google.internal/computeMetadata/v1/",
    "file:///etc/passwd",
    "gopher://127.0.0.1:70/",
])
def test_html_fetcher_rejects_local_metadata_and_non_http_schemes(url):
    safe, reason = converters.is_safe_url(url)
    assert safe is False
    assert reason


def test_html_fetcher_rejects_private_dns_answers(monkeypatch):
    monkeypatch.setattr(
        converters.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("10.8.0.9", 443))],
    )

    safe, reason = converters.is_safe_url("https://public.example.test/document")

    assert safe is False
    assert "private/internal" in reason


def test_html_fetcher_blocks_redirect_into_private_network(monkeypatch):
    monkeypatch.setattr(converters, "is_safe_url", lambda url: (False, "blocked target"))
    handler = converters.SSRFRedirectHandler()

    with pytest.raises(ValueError, match="Redirect blocked"):
        handler.redirect_request(
            URLRequest("https://public.example.test/"),
            None,
            302,
            "Found",
            {},
            "http://127.0.0.1/admin",
        )


def test_drive_import_reports_actionable_message_on_unavailable_drive(monkeypatch):
    def fail_fetch(url, **kwargs):
        raise ValueError("Could not resolve hostname: drive.google.com")

    monkeypatch.setattr(server.converters, "safe_fetch_url", fail_fetch)
    response = TestClient(server.app).post(
        "/api/cloud/sync",
        data={"file_url": "https://drive.google.com/file/d/synthetic-id/view"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Google Drive could not be reached. Confirm the file is shared with anyone who has the link, "
        "then retry or use a direct PDF download URL."
    )


def test_repair_endpoint_accepts_a_valid_header_with_truncated_trailer():
    truncated = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] >>\nendobj\n"
    response = TestClient(server.app).post(
        "/api/studio/repair",
        files={"file": ("truncated.pdf", truncated, "application/pdf")},
        data={"mode": "automatic"},
    )

    assert response.status_code == 200
    repaired = fitz.open(stream=response.content, filetype="pdf")
    assert repaired.page_count == 1
    repaired.close()


def test_prod_api_docs_and_schema_are_disabled():
    assert server._should_disable_docs("production", "true") is True
    assert server.app.openapi_url is None
    assert server.app.docs_url is None
    assert server.app.redoc_url is None


def test_studio_workspace_storage_is_account_scoped_and_fresh_load_wins():
    source = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "paperplane-local-work-account-id" in source
    assert "function localWorkStoreKey(key, scope = localWorkScope())" in source
    assert "return `${scope}:${key}`" in source
    assert "studioWorkspaceEpoch" in source
    assert "restoreEpoch !== studioWorkspaceEpoch" in source
    assert "await clearStudioPdf()" in source


def test_ai_document_greeting_has_grounded_prompts_and_safe_text_rendering():
    source = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "function ensureAiDocumentGreeting(file)" in source
    assert "Your PDF is ready. Ask about its content" in source
    assert "What word is written on page two?" in source
    assert "greeting.textContent = message.text" in source
    assert "button.textContent = question" in source


def test_feedback_dismissal_submission_and_settings_reopen_are_wired():
    root = Path(__file__).resolve().parents[1]
    source = (root / "web" / "assets" / "feedback.js").read_text(encoding="utf-8")
    markup = (root / "web" / "index.html").read_text(encoding="utf-8")
    assert 'writeFlag("dismissed")' in source
    assert 'writeFlag("submitted")' in source
    assert 'result?.status === "ok" && result.feedback_id' in source
    assert 'paperplane:auth-changed' in source
    assert 'id="settings-feedback-open"' in markup
    assert '.pp-feedback-btn[hidden] { display: none !important; }' in source
    assert 'body:has(.modal-backdrop:not([hidden])) #pp-feedback-container' in source


def test_retention_copy_matches_configurable_job_ttl_and_saved_browser_work():
    root = Path(__file__).resolve().parents[1]
    copy = (root / "web" / "index.html").read_text(encoding="utf-8")
    source = (root / "config.py").read_text(encoding="utf-8")
    example = (root / ".env.example").read_text(encoding="utf-8")
    assert "configured retention period (2 hours by default)" in copy
    assert "until you clear it" in copy
    assert "JOB_TTL_SECONDS = int(os.getenv(\"PAPERPLANE_JOB_TTL_SECONDS\", 2 * 60 * 60))" in source
    assert "PAPERPLANE_JOB_TTL_SECONDS=7200" in example
    assert "Automatically deleted within 24 hours" not in copy


def test_sanitize_endpoint_returns_output_and_accurate_removal_summary():
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Synthetic sanitization sample")
    document.set_metadata({"title": "Synthetic title", "author": "Synthetic author"})
    page.add_text_annot((100, 100), "Synthetic annotation")
    action_xref = document.get_new_xref()
    document.update_object(action_xref, "<< /S /JavaScript /JS (app.alert\\('synthetic'\\)) >>")
    document.xref_set_key(document.pdf_catalog(), "OpenAction", f"{action_xref} 0 R")
    content = document.tobytes()
    document.close()

    response = TestClient(server.app).post(
        "/api/studio/security/sanitize",
        files={"file": ("synthetic.pdf", content, "application/pdf")},
        data={"options": '{"remove_metadata":true,"remove_attachments":true,"remove_annotations":true,"remove_javascript":true}'},
    )

    assert response.status_code == 200
    sanitized = fitz.open(stream=response.content, filetype="pdf")
    assert sanitized.metadata.get("title") in (None, "")
    assert len(list(sanitized[0].annots())) == 0
    sanitized.close()
    report = __import__("json").loads(response.headers["X-Paperplane-Sanitize-Report"])
    assert set(report["metadata_keys_removed"]) == {"title", "author"}
    assert report["annotations_removed"] == 1
    assert report["javascript_actions_neutralized"] is True
    assert report["javascript_actions_detected"] >= 1
    assert report["javascript_detected_before"] is True


def test_standalone_protect_and_unlock_tools_link_to_security_audit():
    source = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    security = (Path(__file__).resolve().parents[1] / "web" / "assets" / "security_forms.js").read_text(encoding="utf-8")
    assert "open-security-audit-tool-btn" in source
    assert "controller.openSecurityModal(file)" in source
    assert "controller._switchSecurityTab('audit')" in source
    assert "async applySanitizePdf()" in security
    assert "Download sanitized PDF" in security


def test_standalone_sign_tool_explains_visual_stamp_and_studio_signatures():
    source = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "This tool places a typed visual stamp." in source
    assert "Studio → More Tools → Digital Signatures" in source


def test_tool_cards_are_crawlable_links_and_legacy_routes_redirect():
    root = Path(__file__).resolve().parents[1]
    source = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    styles = (root / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    assert '<a class="home-tool-card" href="${escapeHtml(operationPath(opId))}"' in source
    assert '<a class="home-tool-card" href="${escapeHtml(operationPath(id))}"' in source
    assert "color: inherit;\n  text-decoration: none;" in styles
    response = TestClient(server.app).get("/tools", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/"
    scan_response = TestClient(server.app).get("/scan-pdf", follow_redirects=False)
    assert scan_response.status_code == 301
    assert scan_response.headers["location"] == "/scan-to-pdf"


def test_unavailable_provider_tools_are_hidden_from_directory_cards():
    source = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "if (op.available === false && ['summarize', 'translate'].includes(opId)) return false;" in source
    assert "if (op.available === false && ['summarize', 'translate'].includes(id)) return false;" in source


def test_admin_head_uses_admin_portal_status_without_response_body():
    client = TestClient(server.app)
    get_response = client.get("/admin")
    head_response = client.head("/admin")
    assert get_response.status_code == 200
    assert head_response.status_code == 200
    assert head_response.content == b""


def test_metadata_date_rejects_section_numbers_and_topics_skip_boilerplate(tmp_path):
    path = tmp_path / "metadata-sections.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Document Overview\n3.3.1\nIntroduction\nDate: 3.3.1\nSecurity Architecture and Microservice Deployment Guidelines.")
    document.save(path)
    document.close()

    result = ai_engine.extract_metadata_entities(path, doc_type="general")
    general = result["general_data"]
    assert general["document_date"] is None
    assert "Introduction" not in general["detected_topics"]
    assert "3.3.1" not in general["detected_topics"]
    assert "Security Architecture" in general["detected_topics"]
    assert ai_engine._extract_valid_document_date("Published 2026-10-14") == "2026-10-14"


def test_seo_section_clears_previous_tool_content_before_fetching_next():
    source = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    start = source.index("async function syncSeoContent(operation)")
    end = source.index("\nasync function ", start + 1)
    seo_function = source[start:end]
    assert seo_function.index("section.replaceChildren()") < seo_function.index("safeFetch(`/api/seo/")
