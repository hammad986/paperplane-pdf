from pathlib import Path
import io
import json
import re
import tomllib

import fitz
import pytest

import ai_engine
import converters
import persistence
import server
from scripts.check_served_pdf_runtime import verify_served_runtime
from fastapi.testclient import TestClient
import secrets
import time

ROOT = Path(__file__).resolve().parents[1]


def test_101_compose_requires_admin_code_without_a_fallback():
    lines = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").splitlines()
    setting = next(line.strip() for line in lines if line.strip().startswith("PAPERPLANE_ADMIN_CODE:"))
    assert setting == 'PAPERPLANE_ADMIN_CODE: "${PAPERPLANE_ADMIN_CODE:?PAPERPLANE_ADMIN_CODE must be set}"'


def test_101_secret_scanner_catches_compose_fallbacks():
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    rule = next(rule for rule in config["rules"] if rule["id"] == "paperplane-compose-admin-fallback")
    assert re.search(rule["regex"], 'PAPERPLANE_ADMIN_CODE: "${PAPERPLANE_ADMIN_CODE:-synthetic-value}"')
    assert not re.search(rule["regex"], 'PAPERPLANE_ADMIN_CODE: "${PAPERPLANE_ADMIN_CODE:?must be set}"')


def test_206_runtime_cache_key_changes_from_stale_v13():
    page = (ROOT / "web/index.html").read_text(encoding="utf-8")
    runtime = (ROOT / "web/assets/pdf_runtime.js").read_text(encoding="utf-8")
    assert '/assets/pdf_runtime.js?v=14' in page
    assert 'transformLocalPdf,' in runtime


def test_206_served_runtime_probe_rejects_old_stub(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b"window.PaperplanePdfRuntime = {};"

    monkeypatch.setattr("scripts.check_served_pdf_runtime.urllib.request.urlopen", lambda *_a, **_k: Response())
    with pytest.raises(RuntimeError, match="incomplete"):
        verify_served_runtime("http://127.0.0.1:8501")


def test_206_served_runtime_probe_requires_worker_api(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b"x" * 2600

    monkeypatch.setattr("scripts.check_served_pdf_runtime.urllib.request.urlopen", lambda *_a, **_k: Response())
    with pytest.raises(RuntimeError, match="worker API"):
        verify_served_runtime("http://127.0.0.1:8501")


def test_229_file_picker_is_not_blocked_by_auth_wait():
    source = (ROOT / "web/assets/app.js").read_text(encoding="utf-8")
    browse_handler = source.split("$('#browse').onclick = async () => {", 1)[1].split("};", 1)[0]
    assert "waitForInitialAuth" not in browse_handler
    assert "$('#file-input').click()" in browse_handler
    picker_handler = source.split("$('#file-input').onchange = async e => {", 1)[1].split("};", 1)[0]
    assert "waitForInitialAuth()" in picker_handler
    assert "checkAccessRequirement(operation, selected)" in picker_handler


def test_207_large_merge_has_a_bounded_proxy_compatible_timeout():
    app_source = (ROOT / "server.py").read_text(encoding="utf-8")
    client_source = (ROOT / "web/assets/app.js").read_text(encoding="utf-8")
    assert "MERGE_TIMEOUT_SECONDS = 840.0" in app_source
    assert "}, 840000);" in client_source
    nginx = (ROOT / "deploy/nginx.conf.template").read_text(encoding="utf-8")
    assert "proxy_read_timeout 900s;" in nginx


def test_153_marketing_tool_count_is_catalog_driven_and_sidebar_counts_total_44():
    server_source = (ROOT / "server.py").read_text(encoding="utf-8")
    app_source = (ROOT / "web/assets/app.js").read_text(encoding="utf-8")
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    assert "{len(OPERATIONS)} focused tools" in server_source
    assert "const count = keys.filter(key => Boolean(state.operations[key])).length;" in app_source
    convert_section = html.split('data-category="Convert"', 1)[1].split("</button>", 1)[0]
    assert '<span class="nav-cat-badge">12</span>' in convert_section


def test_226_ai_docs_alias_reaches_the_named_ai_workspace():
    client = TestClient(server.app)
    response = client.get("/ai-docs", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/ai-intelligence"
    landing = client.get("/ai-intelligence")
    assert landing.status_code == 200


def test_228_daily_checkout_probe_is_strictly_sandbox_only():
    workflow = (ROOT / ".github/workflows/cashfree-sandbox-probe.yml").read_text(encoding="utf-8")
    script = (ROOT / "scripts/cashfree_sandbox_smoke.py").read_text(encoding="utf-8")
    assert 'CASHFREE_ENV: TEST' in workflow
    assert '--verify-drop' in workflow
    assert 'config.CASHFREE_ENV != "TEST"' in script
    assert 'mode: \'sandbox\'' in script
    assert 'no payment was submitted' in script.lower()


def test_ai_capability_reads_do_not_consume_provider_rate_limit(monkeypatch):
    rate_limited = []
    monkeypatch.setattr(server, "consume_rate_limit", lambda *args, **kwargs: rate_limited.append(args) or True)
    client = TestClient(server.app)
    for _ in range(20):
        assert client.get("/api/ai/capabilities").status_code == 200
    assert rate_limited == []


def test_ai_chat_posts_still_consume_provider_rate_limit(monkeypatch):
    rate_limited = []
    monkeypatch.setattr(server, "consume_rate_limit", lambda *args, **kwargs: rate_limited.append(args) or True)
    response = TestClient(server.app).post("/api/ai/chat/stream", data={"question": "Hello"})
    assert response.status_code == 200
    assert len(rate_limited) == 1


@pytest.mark.parametrize("translated", ["Hola mundo", "भारत सरकार"])
def test_226_translation_replaces_searchable_source_text(tmp_path, monkeypatch, translated):
    source = tmp_path / "source.pdf"
    output = tmp_path / "translated.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Original English content")
        document.save(source)
    monkeypatch.setattr(ai_engine, "_translate_text_batch", lambda blocks, language, deadline=None: {
        index: translated for index, _ in blocks
    })
    ai_engine.translate_pdf_layout(source, output, target_language="test")
    with fitz.open(output) as document:
        text = document[0].get_text()
        assert "Original English content" not in text
        assert translated in text


def test_1_translation_processes_more_than_120_blocks(tmp_path, monkeypatch):
    source, output = tmp_path / "many.pdf", tmp_path / "translated.pdf"
    with fitz.open() as pdf:
        for number in range(69):
            page = pdf.new_page()
            for row in range(3):
                page.insert_text((72, 72 + row * 75), f"Original block {number:03}-{row}")
        pdf.save(source)
    monkeypatch.setattr(ai_engine, "_translate_text_batch", lambda blocks, language, deadline=None: {
        index: "Texto traducido" for index, _ in blocks
    })
    report = {}
    ai_engine.translate_pdf_layout(source, output, target_language="es", report=report)
    assert report["blocks_seen"] == 207
    assert report["blocks_translated"] == 207
    assert report["blocks_preserved"] == 0
    with fitz.open(output) as pdf:
        assert len(pdf) == 69
        assert all("Original block" not in page.get_text() and page.get_text().count("Texto traducido") == 3 for page in pdf)


def test_1_translation_chunks_preserve_long_words_and_text():
    original = "First phrase " + ("x" * 2500) + " last phrase"
    chunks = ai_engine._translation_chunks(original)
    assert all(0 < len(chunk) <= 1600 for chunk in chunks)
    assert "".join("".join(chunks).split()) == "".join(original.split())


def test_6_multiple_false_premises_are_all_addressed(tmp_path):
    source = tmp_path / "unattributed.pdf"
    with fitz.open() as pdf:
        for _ in range(3):
            pdf.new_page().insert_text((72, 72), "A technical note without an author.")
        pdf.save(source)
    correction = ai_engine.correct_false_premise(source, "This 100-page PDF was written by Albert Einstein, right?")
    assert "3 pages" in correction and "not 100" in correction
    assert "can't verify" in correction and "authorship" in correction


def test_9_105_model_metadata_rejects_section_number_as_date(monkeypatch):
    monkeypatch.setattr(ai_engine, "_current_agentrouter_api_key", lambda: "synthetic")
    monkeypatch.setattr(ai_engine, "call_agentrouter", lambda *args, **kwargs: json.dumps({
        "general_data": {"title": "Notes", "document_date": "3.3.1",
                         "detected_topics": ["3.3.1 Fragments", "Machine Learning"]},
        "warnings": [], "source_pages": [1], "contact": {"emails": [], "phones": []},
    }))
    result = ai_engine._extract_metadata_with_agentrouter("Notes\n3.3.1 Machine Learning", "general", 1)
    assert result["general_data"]["document_date"] is None
    assert result["general_data"]["detected_topics"] == ["Machine Learning"]
    assert any("date" in warning for warning in result["warnings"])
    assert "3.3.1" not in result["csv_export"]


def test_2_retries_an_empty_provider_response(monkeypatch):
    replies = iter([
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": "Grounded summary [Page 1]"}}]},
    ])

    def provider_response(request, timeout):
        return io.BytesIO(json.dumps(next(replies)).encode())

    monkeypatch.setattr(ai_engine, "_open_ai_request", provider_response)
    monkeypatch.setattr(ai_engine.time, "sleep", lambda seconds: None)
    result = ai_engine._provider_request("system", "document", {
        "provider": "openai_compatible", "model": "test-model",
        "api_key": "synthetic-key", "base_url": "https://example.invalid/v1",
    }, timeout_seconds=55)
    assert result == "Grounded summary [Page 1]"


@pytest.mark.parametrize("path", ["/api/developer/keys", "/api/v1/keys"])
def test_223_key_creation_requires_api_plan_and_accepts_json_name(path):
    email = f"developer-{secrets.token_hex(8)}@example.invalid"
    password = secrets.token_urlsafe(24)
    user_id = persistence.create_user(email, password)
    token = persistence.create_session(email, password)["token"]
    client = TestClient(server.app, headers={"Authorization": f"Bearer {token}"})
    for tier in ("free", "student_pro", "exam_pass"):
        persistence.set_user_tier(user_id, tier)
        assert client.post(path, json={"name": "My service"}).status_code == 403
    persistence.set_user_tier(user_id, "cyber_cafe")
    created = client.post(path, json={"name": "My service"})
    assert created.status_code == 200
    assert created.json()["name"] == "My service"
    assert any(item["id"] == created.json()["id"] for item in client.get(path).json()["keys"])
    key_headers = {"Authorization": f"Bearer {created.json()['api_key']}"}
    assert client.get("/api/v1/account/usage", headers=key_headers).status_code == 200
    persistence.set_user_tier(user_id, "student_pro")
    assert client.get("/api/v1/account/usage", headers=key_headers).status_code == 403


def test_225_damaged_pdf_repair_reports_safe_error():
    client = TestClient(server.app)
    response = client.post("/api/jobs", data={"operation": "repair"},
                           files={"files": ("broken.pdf", b"%PDF-1.7\ninvalid object with no trailer", "application/pdf")})
    assert response.status_code == 202
    for _ in range(100):
        job = client.get(response.json()["status_url"]).json()
        if job["status"] == "failed":
            break
        time.sleep(.05)
    assert job["status"] == "failed"
    assert job["error"] == "This PDF is too damaged to repair automatically."


def test_225_repair_storage_errors_are_not_described_as_pdf_damage(tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"synthetic")
    def fail(*args, **kwargs):
        raise OSError("private storage path")
    monkeypatch.setattr(converters, "repair_pdf", fail)
    with pytest.raises(RuntimeError, match="could not read or write") as error:
        server.process("repair", [source], {}, tmp_path)
    assert "private storage path" not in str(error.value)


def test_212_validate_only_keeps_a_healthy_pdf_unchanged(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Validation fixture")
        pdf.save(source)
    converters.repair_pdf(source, output, mode="validate_only")
    assert output.read_bytes() == source.read_bytes()


@pytest.mark.parametrize("tier", ["student_pro", "cyber_cafe"])
def test_208_paid_order_expires_after_30_days_and_replay_does_not_extend(monkeypatch, tier):
    user_id = persistence.create_user(f"billing-{secrets.token_hex(8)}@example.invalid", secrets.token_urlsafe(24))
    now = time.time()
    order_id = f"test-{secrets.token_hex(8)}"
    assert persistence.settle_billing_order(user_id, order_id, tier, "test", {})
    expiration = persistence.get_user(user_id)["subscription_expires_at"]
    assert now + 30 * 86400 <= expiration <= time.time() + 30 * 86400
    assert persistence.settle_billing_order(user_id, order_id, tier, "test", {})
    assert persistence.get_user(user_id)["subscription_expires_at"] == expiration
    assert persistence.settle_billing_order(user_id, f"test-{secrets.token_hex(8)}", tier, "test", {})
    assert persistence.get_user(user_id)["subscription_expires_at"] == expiration + 30 * 86400
