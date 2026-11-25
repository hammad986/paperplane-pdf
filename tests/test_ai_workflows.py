from __future__ import annotations

import json
from pathlib import Path
import time
from unittest.mock import patch
from urllib.error import URLError

import fitz
import pytest
from PIL import Image, ImageDraw, ImageFont

import ai_engine


def use_bluesminds_test_config(monkeypatch):
    """Keep legacy Bluesminds adapter tests isolated from host AI_PROVIDER settings."""
    monkeypatch.setattr(
        ai_engine,
        "_runtime_ai_config",
        lambda: {
            "provider": "bluesminds",
            "model": ai_engine.BLUESMINDS_MODEL,
            "base_url": ai_engine.BLUESMINDS_BASE_URL or "https://api.bluesminds.com/v1",
            "api_key": ai_engine._current_bluesminds_api_key(),
        },
    )


def make_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Paperplane document intelligence keeps source text available.")
    page.insert_text((72, 100), "Important deadline: October 25, 2026.")
    doc.save(str(path))
    doc.close()


def test_bluesminds_missing_key_raises_clear_error(monkeypatch):
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "")
    monkeypatch.setenv("BLUESMINDS_API_KEY", "")
    use_bluesminds_test_config(monkeypatch)
    import pytest
    with pytest.raises(ValueError, match="AI provider is not configured"):
        ai_engine.call_bluesminds("system", "user")


def test_bluesminds_network_failure_raises_clear_error(monkeypatch):
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")
    use_bluesminds_test_config(monkeypatch)

    import pytest
    with patch("ai_engine._open_ai_request", side_effect=URLError("offline")), patch("ai_engine.time.sleep"):
        with pytest.raises(RuntimeError, match="AI service could not be reached or timed out"):
            ai_engine.call_bluesminds("system", "user")


def test_bluesminds_uses_fresh_environment_key(monkeypatch):
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", ai_engine._INITIAL_BLUESMINDS_API_KEY)
    monkeypatch.setenv("BLUESMINDS_API_KEY", "fresh-bluesminds-key-from-environment")
    monkeypatch.setattr(ai_engine, "BLUESMINDS_MODEL", "owner/configured-model")
    use_bluesminds_test_config(monkeypatch)

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"upstream response"}}]}'

    with patch("ai_engine._open_ai_request", return_value=FakeResponse()) as open_url:
        assert ai_engine.call_bluesminds("system", "user") == "upstream response"

    request = open_url.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer fresh-bluesminds-key-from-environment"
    assert json.loads(request.data)["model"] == "owner/configured-model"
    assert open_url.call_count == 1


def test_bluesminds_retries_transient_first_attempt(monkeypatch):
    from urllib.error import HTTPError

    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")
    use_bluesminds_test_config(monkeypatch)
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def read(self): return b'{"choices":[{"message":{"content":"first successful response"}}]}'

    with patch("ai_engine._open_ai_request", side_effect=[HTTPError("https://provider.invalid", 503, "busy", {}, None), FakeResponse()]) as open_url, patch("ai_engine.time.sleep"):
        assert ai_engine.call_bluesminds("system", "user", timeout_seconds=8) == "first successful response"
    assert open_url.call_count == 2


def test_translation_retry_budget_allows_slow_but_healthy_provider(monkeypatch):
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    calls = []

    class FakeResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def read(self): return b'{"choices":[{"message":{"content":"{\\"translations\\":[{\\"id\\":0,\\"text\\":\\"Texto traducido\\"}]}"}}]}'

    def slow_provider(request, timeout):
        calls.append(timeout)
        # Model an upstream that needs 15 seconds: the old 55-second total
        # budget split over four attempts provided only about 12 seconds each.
        if timeout < 15:
            raise TimeoutError("simulated provider response exceeded attempt timeout")
        time.sleep(15.1)
        return FakeResponse()

    monkeypatch.setattr(ai_engine, "_open_ai_request", slow_provider)
    credentials = {
        "provider": "openai_compatible",
        "base_url": "https://provider.invalid/v1",
        "model": "synthetic-model",
        "api_key": "synthetic-key",
    }
    result = ai_engine._provider_request(
        "Translate the text.",
        '[{"id":0,"text":"Source text"}]',
        credentials,
        timeout_seconds=ai_engine.TRANSLATION_CALL_TIMEOUT_SECONDS,
        max_attempts=4,
    )

    assert result == '{"translations":[{"id":0,"text":"Texto traducido"}]}'
    assert len(calls) == 1
    assert calls[0] >= 15


def test_bluesminds_429_retry_honors_bounded_retry_after(monkeypatch):
    from urllib.error import HTTPError

    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")
    use_bluesminds_test_config(monkeypatch)

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def read(self): return b'{"choices":[{"message":{"content":"recovered after provider cooldown"}}]}'

    throttled = HTTPError("https://provider.invalid", 429, "limited", {"Retry-After": "60"}, None)
    with patch("ai_engine._open_ai_request", side_effect=[throttled, FakeResponse()]) as open_url, \
            patch("ai_engine.time.sleep") as sleep:
        assert ai_engine.call_bluesminds("system", "user", timeout_seconds=8) == "recovered after provider cooldown"
    assert open_url.call_count == 2
    assert sleep.call_count == 1
    assert sleep.call_args.args[0] == pytest.approx(4.2, abs=0.1)


def test_provider_retry_after_is_honored_within_total_timeout_budget(monkeypatch):
    from urllib.error import HTTPError

    now = [100.0]
    sleep_calls = []
    request_timeouts = []

    class FakeResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def read(self): return b'{"choices":[{"message":{"content":"recovered"}}]}'

    def advance(seconds):
        sleep_calls.append(seconds)
        now[0] += seconds

    def provider(request, timeout):
        request_timeouts.append(timeout)
        if len(request_timeouts) == 1:
            raise HTTPError(request.full_url, 429, "limited", {"Retry-After": "30"}, None)
        return FakeResponse()

    monkeypatch.setattr(ai_engine.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(ai_engine.time, "sleep", advance)
    monkeypatch.setattr(ai_engine, "_open_ai_request", provider)
    credentials = {
        "provider": "openai_compatible", "base_url": "https://provider.invalid/v1",
        "model": "synthetic-model", "api_key": "synthetic-key",
    }

    result = ai_engine._provider_request(
        "Translate the text.", "Source text", credentials,
        timeout_seconds=90, max_attempts=4,
    )

    assert result == "recovered"
    assert sleep_calls == [30.0]
    assert request_timeouts == pytest.approx([20.65, 17.67], abs=0.02)
    assert now[0] - 100.0 <= 90


def test_ai_connection_check_uses_configured_fallback_after_primary_rate_limit(monkeypatch):
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_runtime_ai_config", lambda: {
        "provider": "openai_compatible",
        "base_url": "https://primary.example/v1",
        "model": "primary-model",
        "api_key": "primary-test-key",
        "fallback": {
            "provider": "openrouter",
            "base_url": "https://fallback.example/v1",
            "model": "fallback-model",
            "api_key": "fallback-test-key",
        },
    })
    calls = []

    def provider_request(_system, _user, credentials, **_kwargs):
        calls.append(credentials["provider"])
        if credentials["provider"] == "openai_compatible":
            raise RuntimeError("AI service returned HTTP 429. Please try again.")
        return "connected"

    monkeypatch.setattr(ai_engine, "_provider_request", provider_request)
    result = ai_engine.test_bluesminds_connectivity()

    assert calls == ["openai_compatible", "openrouter"]
    assert result["status"] == "inference_succeeded"
    assert result["fallback_active"] is True
    assert "fallback.example" not in result["message"]


def test_translation_falls_back_after_primary_rate_limit_and_reports_admin_health(tmp_path, monkeypatch):
    import persistence
    source = tmp_path / "fallback-source.pdf"
    output = tmp_path / "fallback-translated.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "The document processing service is ready for review.")
        pdf.save(source)

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_AI_PROVIDER_STATUS", {
        "last_request_at": None, "last_status": "not_checked", "last_provider": None,
        "fallback_active": False, "last_failure": None,
    })
    monkeypatch.setattr(persistence, "set_ai_provider_health_status", lambda _status: None)
    monkeypatch.setattr(persistence, "get_ai_provider_health_status", lambda: dict(ai_engine._AI_PROVIDER_STATUS))
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "primary-secret")
    monkeypatch.setattr(ai_engine, "_runtime_ai_config", lambda: {
        "provider": "openai_compatible", "base_url": "https://primary.example/v1",
        "model": "primary-model", "api_key": "primary-secret",
        "fallback": {
            "provider": "openrouter", "base_url": "https://fallback.example/v1",
            "model": "fallback-model", "api_key": "fallback-secret",
        },
    })
    calls = []

    def provider_request(_system, _user, credentials, **_kwargs):
        calls.append(credentials["provider"])
        if credentials["provider"] == "openai_compatible":
            raise RuntimeError("AI service returned HTTP 429. Please try again.")
        return json.dumps({"translations": [{"id": 0, "text": "El servicio de procesamiento está listo para revisión."}]})

    monkeypatch.setattr(ai_engine, "_provider_request", provider_request)
    report = {}
    ai_engine.translate_pdf_layout(source, output, target_lang="Spanish", report=report)

    assert calls == ["openai_compatible", "openrouter"]
    assert report["translation_status"] == "translated"
    with fitz.open(output) as translated:
        assert len(translated) == 1
        assert "procesamiento" in translated[0].get_text().lower()

    health = ai_engine.get_ai_configuration_health()
    assert health["runtime_status"]["last_status"] == "rate_limited"
    assert health["runtime_status"]["last_failure"] == "rate_limit"
    assert health["runtime_status"]["fallback_active"] is True
    assert "rate limited" in health["message"].lower()
    assert "primary-secret" not in json.dumps(health)
    assert "fallback-secret" not in json.dumps(health)


def test_hindi_translation_embeds_extractable_devanagari_text(tmp_path, monkeypatch):
    source = tmp_path / "hindi-source.pdf"
    output = tmp_path / "hindi-translated.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 100), "Sample English text for translation")
        document.save(source)

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "controlled-test-key")
    monkeypatch.setattr(ai_engine, "_translate_text_batch", lambda batch, *args, **kwargs: {
        block_id: "प्लेन टेस्ट" for block_id, _ in batch
    })
    report = {}

    ai_engine.translate_pdf_layout(source, output, target_language="Hindi", report=report)

    with fitz.open(output) as translated:
        extracted = translated[0].get_text()
        assert "प्लेन" in extracted
        assert "टेस्ट" in extracted
        assert report["blocks_translated"] == 1


@pytest.mark.parametrize(("language", "translated_text"), [("Spanish", "es"), ("Hindi", "हाँ")])
def test_translation_preserves_vertical_text_orientation_and_searchability(tmp_path, monkeypatch, language, translated_text):
    source = tmp_path / "vertical-source.pdf"
    output = tmp_path / "vertical-translated.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((150, 150), "It", fontsize=7.78, rotate=90)
        document.save(source)

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "controlled-test-key")
    monkeypatch.setattr(ai_engine, "_translate_text_batch", lambda batch, *args, **kwargs: {
        block_id: translated_text for block_id, _ in batch
    })
    report = {}

    ai_engine.translate_pdf_layout(source, output, target_language=language, report=report)

    with fitz.open(output) as translated:
        page = translated[0]
        extracted = page.get_text()
        assert translated_text in extracted
        assert "It" not in extracted
        assert report["blocks_translated"] == 1
        assert report["blocks_preserved"] == 0
        assert report["blocks_rotated"] == 1
        assert report["translation_status"] == "translated"
        assert page.get_images(full=True)


def test_sparse_gallery_question_explains_low_searchable_text_instead_of_no_match(tmp_path, monkeypatch):
    source = tmp_path / "sparse-gallery.pdf"
    with fitz.open() as document:
        for page_number in range(1, 25):
            page = document.new_page()
            page.insert_text((72, 72), f"Photo {page_number}")
        document.save(source)
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "controlled-test-key")
    monkeypatch.setattr(ai_engine, "call_llm", lambda *_args, **_kwargs: pytest.fail("sparse broad questions should not call the provider"))

    result = ai_engine.chat_with_pdf(source, "What is this document about?")

    assert "very little searchable text" in result["answer"]
    assert "OCR" in result["answer"]
    assert "No relevant information found" not in result["answer"]
    assert result["retrieval_method"] == "Sparse PDF Text Check"


def test_bluesminds_stream_parses_provider_deltas(monkeypatch):
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")
    use_bluesminds_test_config(monkeypatch)

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"Hello "}}]}\n'
            yield b'data: {"choices":[{"delta":{"content":"there."}}]}\n'
            yield b'data: [DONE]\n'

    with patch("ai_engine._open_ai_request", return_value=FakeResponse()) as open_url:
        assert list(ai_engine.stream_bluesminds("system", "user")) == ["Hello ", "there."]
    request = open_url.call_args.args[0]
    assert json.loads(request.data)["stream"] is True


def test_bluesminds_stream_retries_transient_failure_before_first_token(monkeypatch):
    from urllib.error import HTTPError

    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")
    use_bluesminds_test_config(monkeypatch)

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"recovered"}}]}\n'
            yield b'data: [DONE]\n'

    with patch("ai_engine._open_ai_request", side_effect=[HTTPError("https://provider.invalid", 503, "busy", {}, None), FakeResponse()]) as open_url, patch("ai_engine.time.sleep"):
        assert list(ai_engine.stream_bluesminds("system", "user")) == ["recovered"]
    assert open_url.call_count == 2


def test_configured_fallback_completes_a_failed_stream_without_recalling_primary(monkeypatch):
    credentials = {
        "provider": "bluesminds",
        "api_key": "primary-test-key",
        "fallback": {"provider": "openrouter", "api_key": "fallback-test-key", "model": "test-model", "base_url": "https://fallback.invalid/v1"},
    }
    monkeypatch.setattr(ai_engine, "_runtime_ai_config", lambda: credentials)
    calls = []

    def provider_request(system_prompt, user_prompt, config, **kwargs):
        calls.append(config["provider"])
        assert config is credentials["fallback"]
        return "A safe fallback answer."

    monkeypatch.setattr(ai_engine, "_provider_request", provider_request)
    answer = ai_engine.complete_with_configured_fallback("system", "question", RuntimeError("AI service returned HTTP 429. Please try again."))

    assert answer == "A safe fallback answer."
    assert calls == ["openrouter"]
    status = ai_engine._get_ai_provider_status()
    assert status["last_status"] == "rate_limited"
    assert status["fallback_active"] is True


def test_chat_stream_replaces_failed_provider_stream_with_configured_fallback(monkeypatch):
    from fastapi.testclient import TestClient
    from server import app

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "primary-test-key")

    def failed_stream(*_args, **_kwargs):
        raise RuntimeError("AI service returned HTTP 429. Please try again.")
        yield  # pragma: no cover

    monkeypatch.setattr(ai_engine, "stream_bluesminds", failed_stream)
    monkeypatch.setattr(ai_engine, "complete_with_configured_fallback", lambda *_args, **_kwargs: "Fallback answer for the question.")
    response = TestClient(app).post("/api/ai/chat/stream", data={"question": "Explain why the sky looks blue."})

    assert response.status_code == 200
    assert 'event: replace\ndata: {"text": "Fallback answer for the question."}' in response.text
    assert '"mode": "provider_fallback"' in response.text
    assert response.text.count("event: done") == 1


def test_bluesminds_stream_does_not_restart_after_partial_output(monkeypatch):
    import pytest

    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")
    use_bluesminds_test_config(monkeypatch)

    class PartialResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n'
            raise URLError("connection dropped")

    with patch("ai_engine._open_ai_request", return_value=PartialResponse()) as open_url:
        stream = ai_engine.stream_bluesminds("system", "user")
        assert next(stream) == "partial"
        with pytest.raises(RuntimeError, match="AI service could not be reached or timed out"):
            next(stream)
    assert open_url.call_count == 1


def test_ai_test_connection_returns_specific_visible_http_failure(monkeypatch):
    from fastapi.testclient import TestClient
    from server import app

    monkeypatch.setattr(ai_engine, "test_bluesminds_connectivity", lambda: {"status": "connection_error", "http_status": 401})
    response = TestClient(app).get("/api/ai/test-connection")
    assert response.status_code == 200
    assert response.json()["status"] == "connection_error"
    assert "HTTP 401" in response.json()["message"]
    assert "model" not in response.json()


def test_ai_routes_apply_guest_request_limit_with_retry_after():
    from fastapi.testclient import TestClient
    from server import app
    import persistence
    import secrets

    email = f"ai-limit-{secrets.token_hex(8)}@example.invalid"
    password = secrets.token_urlsafe(24)
    persistence.create_user(email, password)
    persistence.set_user_tier(persistence.get_user_by_email(email)["id"], "cyber_cafe")
    token = persistence.create_session(email, password)["token"]
    client = TestClient(app, cookies={"paperplane_token": token})
    for _ in range(12):
        assert client.post("/api/ai/chat/stream", data={"question": "Hello"}).status_code == 200
    limited = client.post("/api/ai/chat/stream", data={"question": "Hello"})
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"


def test_ai_chat_stream_emits_real_stage_events_and_progressive_deltas(monkeypatch):
    from fastapi.testclient import TestClient
    from server import app

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    first = "The first words arrive. " + ("A long answer streams progressively through the Paperplane workspace. " * 8)
    second = "Then the rest streams. " + ("More grounded detail arrives in a later chunk. " * 8)
    monkeypatch.setattr(ai_engine, "stream_bluesminds", lambda system, user, timeout_seconds=50: iter([first, second]))
    response = TestClient(app).post("/api/ai/chat/stream", data={"question": "Tell me something useful."})
    assert response.status_code == 200
    body = response.text
    assert body.index('stage": "Thinking') < body.index('stage": "Analysing') < body.index('stage": "Generating')
    assert body.count("event: token") >= 2
    assert '"text": "The first words arrive.' in body
    assert body.count("event: token") >= 2
    assert "event: done" in body


def test_ai_chat_stream_reports_document_stages_and_page_citation(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from server import app

    source = tmp_path / "stream-page.pdf"
    make_pdf(source)
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")
    monkeypatch.setattr(ai_engine, "stream_bluesminds", lambda system, user, timeout_seconds=50: iter(["October 25, 2026 is the deadline. [Page 1] " + ("More context follows. " * 20)]))
    with source.open("rb") as handle:
        response = TestClient(app).post(
            "/api/ai/chat/stream",
            data={"question": "What is on page 1?"},
            files={"file": ("stream-page.pdf", handle, "application/pdf")},
        )
    body = response.text
    ordered = ['stage": "Thinking', 'stage": "Extracting', 'stage": "Analysing', 'stage": "Searching', 'stage": "Generating']
    positions = [body.index(stage) for stage in ordered]
    assert positions == sorted(positions)
    assert '"citations": [1]' in body


def test_ai_chat_stream_sparse_gallery_returns_ocr_guidance_instead_of_no_match(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from server import app

    source = tmp_path / "sparse-gallery-stream.pdf"
    with fitz.open() as document:
        for number in range(1, 25):
            page = document.new_page()
            page.insert_text((72, 72), f"Photo {number}")
        document.save(source)

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "")
    monkeypatch.setattr(ai_engine, "stream_bluesminds", lambda *_args, **_kwargs: pytest.fail("sparse subject queries must not call a provider"))
    with source.open("rb") as handle:
        response = TestClient(app).post(
            "/api/ai/chat/stream",
            data={"question": "What is this document about?"},
            files={"file": (source.name, handle, "application/pdf")},
        )

    body = response.text
    assert response.status_code == 200
    assert "very little searchable text" in body
    assert "Run OCR" in body
    assert "No relevant information found" not in body
    assert '"mode": "sparse_text_guidance"' in body


def test_ai_chat_answers_general_question_without_pdf(monkeypatch):
    from fastapi.testclient import TestClient
    from server import app

    monkeypatch.setattr(ai_engine, "call_llm", lambda system, user, timeout_seconds=None: "Hello! I’m doing well, thanks for asking.")
    client = TestClient(app)
    response = client.post("/api/ai/chat", data={"question": "Hello, how are you?"})
    assert response.status_code == 200
    assert response.json()["answer"] == ai_engine._simple_greeting_reply("Hello, how are you?")
    assert response.json()["citations"] == []

    document_question = client.post("/api/ai/chat", data={"question": "What is the deadline in the PDF?"})
    assert document_question.status_code == 200
    assert "No PDF is open" in document_question.json()["answer"]


def test_ai_greetings_bypass_document_retrieval_with_or_without_pdf(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from server import app

    source = tmp_path / "greeting-document.pdf"
    make_pdf(source)
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "call_llm", lambda *args, **kwargs: "A direct general answer.")
    client = TestClient(app)

    expected = {
        "hey": "Hello! How can I help you today? You can ask a general question or ask about your PDF.",
        "hello": "Hello! How can I help you today? You can ask a general question or ask about your PDF.",
        "how are you": "I'm here and ready to help. What would you like to know or do with your PDF?",
    }
    for index, (question, answer) in enumerate(expected.items()):
        client = TestClient(app, client=(f"192.0.2.{index + 1}", 50000))
        no_document = client.post("/api/ai/chat", data={"question": question})
        assert no_document.status_code == 200
        assert no_document.json()["answer"] == answer
        assert no_document.json()["citations"] == []

        with source.open("rb") as handle:
            with_document = client.post(
                "/api/ai/chat",
                data={"question": question},
                files={"file": (source.name, handle, "application/pdf")},
            )
        assert with_document.status_code == 200
        assert with_document.json()["answer"] == answer
        assert with_document.json()["citations"] == []

        stream_no_document = client.post("/api/ai/chat/stream", data={"question": question})
        assert stream_no_document.status_code == 200
        assert f'"text": "{answer}"' in stream_no_document.text
        assert '"mode": "direct_conversation"' in stream_no_document.text

        with source.open("rb") as handle:
            stream_with_document = client.post(
                "/api/ai/chat/stream",
                data={"question": question},
                files={"file": (source.name, handle, "application/pdf")},
            )
        assert stream_with_document.status_code == 200
        assert f'"text": "{answer}"' in stream_with_document.text
        assert '"mode": "direct_conversation"' in stream_with_document.text
        assert '"stage": "Extracting' not in stream_with_document.text


def test_ai_chat_with_pdf_uses_attached_document_for_non_greeting_questions(tmp_path, monkeypatch):
    source = tmp_path / "direct-versus-document.pdf"
    make_pdf(source)
    prompts = []

    def fake_call(system, user, timeout_seconds=None):
        prompts.append(user)
        if "DOCUMENT EXCERPTS" in user:
            return "The page includes an important deadline. [Page 1]"
        return "A direct general answer."

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")
    monkeypatch.setattr(ai_engine, "call_llm", fake_call)
    document_context_answer = ai_engine.chat_with_pdf(source, "Can you help me with a general question?")
    assert document_context_answer["answer"] != "A direct general answer."
    assert "DOCUMENT EXCERPTS" in prompts[-1]

    grounded = ai_engine.chat_with_pdf(source, "What is on page 1?")
    assert "important deadline" in grounded["answer"]
    assert grounded["citations"] == [1]
    assert "[Page 1]" in prompts[-1]


def test_ai_summary_timeout_and_translation_failure_return_actionable_gateway_errors(tmp_path, monkeypatch):
    import time
    from fastapi.testclient import TestClient
    import server

    source = tmp_path / "bounded-ai.pdf"
    make_pdf(source)
    client = TestClient(server.app)

    monkeypatch.setattr(server, "AI_SUMMARY_REQUEST_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(ai_engine, "summarize_pdf", lambda _path, **_kwargs: (time.sleep(0.15), "late response")[1])
    with source.open("rb") as handle:
        summary = client.post("/api/ai/summarize", files={"file": (source.name, handle, "application/pdf")})
    assert summary.status_code == 504
    assert summary.json()["detail"] == "The AI provider did not return an executive brief before the request deadline. No output was created; retry later."

    monkeypatch.setattr(server, "translation_ai_available", lambda: True)
    monkeypatch.setattr(ai_engine, "translate_pdf_layout", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider failure details")))
    with source.open("rb") as handle:
        translated = client.post(
            "/api/ai/translate",
            data={"target_language": "es"},
            files={"file": (source.name, handle, "application/pdf")},
        )
    assert translated.status_code == 502
    assert translated.json()["detail"] == "Translation provider failed during document processing. Please retry later."


def test_document_chat_uses_cited_local_answer_when_ai_provider_is_unconfigured(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from server import app

    source = tmp_path / "local-answer.pdf"
    make_pdf(source)
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "")
    monkeypatch.setenv("BLUESMINDS_API_KEY", "")
    monkeypatch.setattr(ai_engine, "call_llm", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider must not be called")))

    direct = ai_engine.chat_with_pdf(source, "What is on page 1?")
    assert "October 25, 2026" in direct["answer"]
    assert direct["citations"] == [1]
    assert direct["fallback_used"] is True

    with source.open("rb") as handle:
        response = TestClient(app).post(
            "/api/ai/chat/stream",
            data={"question": "What is on page 1?"},
            files={"file": (source.name, handle, "application/pdf")},
        )
    assert response.status_code == 200
    assert '"mode": "local_extraction"' in response.text
    streamed_answer = ""
    lines = response.text.splitlines()
    for index, line in enumerate(lines[:-1]):
        if line.strip() == "event: token" and lines[index + 1].startswith("data: "):
            streamed_answer += json.loads(lines[index + 1][6:])["text"]
    assert "October 25, 2026" in streamed_answer
    assert "[Page 1]" in streamed_answer
    assert "[[Page" not in streamed_answer
    assert '"citations": [1]' in response.text


def test_ai_first_attempt_general_identity_and_code_scope(monkeypatch):
    from fastapi.testclient import TestClient
    from server import app

    monkeypatch.setattr(ai_engine, "call_llm", lambda system, user, timeout_seconds=None: "A direct answer on the first request.")
    client = TestClient(app)
    response = client.post("/api/ai/chat", data={"question": "Hello, how are you?"})
    assert response.status_code == 200
    assert response.json()["answer"] == ai_engine._simple_greeting_reply("Hello, how are you?")

    for question in ("Who are you?", "What model are you?", "Who trained you?", "Are you Nemotron?"):
        answer = client.post("/api/ai/chat", data={"question": question}).json()["answer"]
        assert answer == ai_engine._PAPERPLANE_IDENTITY
        assert not any(name in answer.lower() for name in ("nemotron", "nvidia", "bluesminds"))

    for question in ("Write Python code to check yes or no", "Generate JavaScript code", "Debug this Python function"):
        answer = client.post("/api/ai/chat", data={"question": question}).json()["answer"]
        assert answer == ai_engine._CODE_SCOPE_REPLY
        assert "```" not in answer


def test_broad_summary_covers_all_document_pages_and_page_one_retrieval(tmp_path, monkeypatch):
    source = tmp_path / "many-pages.pdf"
    doc = fitz.open()
    for page_num in range(1, 21):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {page_num} unique topic marker-{page_num} broad summary text.")
    doc.save(str(source))
    doc.close()

    captured = {}
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")
    def capture_summary(system, user, timeout_seconds=None, max_attempts=2, **kwargs):
        captured.setdefault("prompts", []).append(user)
        captured.setdefault("temperatures", []).append(kwargs.get("temperature"))
        return "ok"
    monkeypatch.setattr(ai_engine, "call_llm", capture_summary)
    summary = ai_engine.summarize_pdf(source)
    assert "Page 20" in "\n".join(captured["prompts"])
    assert captured["temperatures"] == [0.0, 0.0, 0.0]
    assert summary

    def answer_page(system, prompt, timeout_seconds=None, max_attempts=2, **kwargs):
        captured["page_prompt"] = prompt
        return "Page one unique topic marker-1. [Page 1]"
    monkeypatch.setattr(ai_engine, "call_llm", answer_page)
    result = ai_engine.chat_with_pdf(source, "What is on page 1?")
    assert "Page one unique topic marker-1" in result["answer"]
    assert result["citations"] == [1]
    assert "Page 20:" not in captured["page_prompt"]


def test_large_summary_chunks_all_pages_and_preserves_supported_citations(tmp_path, monkeypatch):
    source = tmp_path / "summary-69-pages.pdf"
    doc = fitz.open()
    for page_num in range(1, 70):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {page_num} of 69. Topic marker {page_num}. Supporting facts for the document summary.")
    doc.save(str(source))
    doc.close()

    calls = []
    def summarize_chunk(system, prompt, timeout_seconds=None, max_attempts=2, **kwargs):
        calls.append((prompt, timeout_seconds, kwargs.get("temperature")))
        if prompt.startswith("Synthesize these page-grounded"):
            return "The document covers its opening topic [Page 1] and final topic [Page 69]."
        pages = [int(value) for value in __import__("re").findall(r"--- Page (\d+) ---", prompt)]
        return f"Section summary spans [Page {pages[0]}] through [Page {pages[-1]}]."

    monkeypatch.setattr(ai_engine, "call_llm", summarize_chunk)
    summary = ai_engine.summarize_pdf(source)

    assert len(calls) == 7
    included_pages = {
        int(value)
        for prompt, _, _temperature in calls[:6]
        for value in __import__("re").findall(r"--- Page (\d+) ---", prompt)
    }
    assert included_pages == set(range(1, 70))
    assert all(1 <= timeout <= ai_engine.SUMMARY_CALL_TIMEOUT_SECONDS for _, timeout, _temperature in calls)
    assert all(temperature == 0.0 for _, _, temperature in calls)
    assert "[Page 1]" in summary and "[Page 69]" in summary


def test_summary_returns_full_citations_when_inline_label_is_bounded(tmp_path, monkeypatch):
    import re

    source = tmp_path / "summary-scattered-citations-120-pages.pdf"
    with fitz.open() as pdf:
        for page_no in range(1, 121):
            page = pdf.new_page()
            page.insert_text((72, 72), f"Page {page_no} records its audited fact.")
        pdf.save(source)

    expected_pages = list(range(1, 120, 2))

    def summarize_chunk(_system, prompt, **_kwargs):
        if prompt.startswith("Synthesize these page-grounded section notes"):
            cited = ", ".join(map(str, expected_pages))
            return f"The audited findings vary across the source. [Pages {cited}]"
        pages = [int(value) for value in re.findall(r"--- Page (\d+) ---", prompt)]
        return f"Section findings include [Page {pages[0]}] and [Page {pages[-1]}]."

    monkeypatch.setattr(ai_engine, "call_llm", summarize_chunk)
    summary, citations = ai_engine.summarize_pdf(source, include_citations=True)

    assert citations == expected_pages
    assert "… +52 more pages" in summary
    assert len(re.search(r"\[Pages [^\]]+\]", summary).group(0)) <= 120


def test_large_summary_preserves_late_page_text_within_each_provider_chunk(tmp_path, monkeypatch):
    source = tmp_path / "summary-69-pages-late-facts.pdf"
    doc = fitz.open()
    for page_num in range(1, 70):
        page = doc.new_page()
        leading_context = (
            f"Page {page_num} operational context includes findings, ownership, impact, and recommended follow-up. "
            * 12
        )
        page_tail = f"LATE-PAGE-FACT-{page_num:02d}"
        page.insert_textbox(fitz.Rect(50, 50, 545, 790), leading_context + page_tail, fontsize=9)
    doc.save(str(source))
    doc.close()

    provider_prompts = []

    def capture_chunk(system, prompt, timeout_seconds=None, max_attempts=2, **kwargs):
        if prompt.startswith("Synthesize these page-grounded"):
            return "The document covers its opening and closing sections [Page 1] [Page 69]."
        provider_prompts.append(prompt)
        pages = [int(value) for value in __import__("re").findall(r"--- Page (\d+) ---", prompt)]
        return f"Section findings are documented on [Page {pages[0]}] and [Page {pages[-1]}]."

    monkeypatch.setattr(ai_engine, "call_llm", capture_chunk)
    result = ai_engine.summarize_pdf(source)

    assert len(provider_prompts) == 6
    for page_num in range(1, 70):
        assert f"LATE-PAGE-FACT-{page_num:02d}" in "\n".join(provider_prompts)
    assert "[Page 1]" in result and "[Page 69]" in result


def test_large_summary_keeps_beginning_middle_and_end_of_long_pages(tmp_path, monkeypatch):
    source = tmp_path / "summary-69-pages-long-text.pdf"
    doc = fitz.open()
    for page_num in range(1, 70):
        page = doc.new_page()
        for row in range(30):
            position = "beginning" if row == 0 else "middle" if row == 15 else "ending" if row == 29 else "detail"
            marker = f"PAGE-{page_num:02d}-{position.upper()}-FACT"
            page.insert_text(
                (45, 58 + row * 22),
                f"{marker} operational finding {row:02d}. " + ("Routine monitoring and control detail. " * 3),
                fontsize=8,
            )
    doc.save(str(source))
    doc.close()

    provider_prompts = []

    def capture_chunk(system, prompt, timeout_seconds=None, max_attempts=2, **kwargs):
        if prompt.startswith("Synthesize these page-grounded"):
            return "The report records its opening and final findings [Page 1] [Page 69]."
        provider_prompts.append(prompt)
        pages = [int(value) for value in __import__("re").findall(r"--- Page (\d+) ---", prompt)]
        return f"The section records findings [Page {pages[0]}] and [Page {pages[-1]}]."

    monkeypatch.setattr(ai_engine, "call_llm", capture_chunk)
    result = ai_engine.summarize_pdf(source)
    transmitted = "\n".join(provider_prompts)

    assert len(provider_prompts) == 6
    assert len(transmitted) > 0
    for page_num in range(1, 70):
        for position in ("BEGINNING", "MIDDLE", "ENDING"):
            assert f"PAGE-{page_num:02d}-{position}-FACT" in transmitted
    assert "[Page 1]" in result and "[Page 69]" in result


def test_offline_executive_brief_is_concise_and_keeps_numeric_and_decision_facts():
    repeated = "Repeated operational boilerplate describes routine controls and follow-up actions."
    prompt = "DOCUMENT CONTENT:\n\n" + "\n\n".join([
        "--- Page 1 ---\nQuarterly operations review\nCompletion rate was 23 percent.\n" + "\n".join([repeated] * 12),
        "--- Page 2 ---\nDecision: retain all 69 records for the final audit.\nBudget approved: $42,000.\n" + "\n".join([repeated] * 12),
    ])

    brief = ai_engine._offline_rag_fallback("Executive Summary", prompt)
    page_one_points = [line for line in brief.splitlines() if line.startswith("-") and "[Page 1]" in line]
    page_two_points = [line for line in brief.splitlines() if line.startswith("-") and "[Page 2]" in line]

    assert len(page_one_points) <= 4 and len(page_two_points) <= 4
    assert "Completion rate was 23 percent." in brief
    assert "Decision: retain all 69 records for the final audit." in brief
    assert "$42,000" in brief
    assert "up to four page-grounded highlights per text page" in brief


def test_large_summary_chunk_failure_falls_back_with_all_section_lines_and_citations(tmp_path, monkeypatch):
    source = tmp_path / "summary-provider-failure-69-pages.pdf"
    doc = fitz.open()
    for page_num in range(1, 70):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {page_num} unique operations finding with enough extractable words for a grounded brief.")
        if page_num == 24:
            page.insert_text((72, 112), "Chunk recovery decision: preserve every record from the affected pages.")
    doc.save(str(source))
    doc.close()

    calls = []

    def fail_one_provider_section(system, prompt, timeout_seconds=None, max_attempts=2, **kwargs):
        calls.append(prompt)
        if "DOCUMENT SECTION, pages 13-24:" in prompt:
            raise RuntimeError("controlled upstream failure")
        pages = [int(value) for value in __import__("re").findall(r"--- Page (\d+) ---", prompt)]
        return f"Section findings from [Page {pages[0]}] to [Page {pages[-1]}]."

    monkeypatch.setattr(ai_engine, "call_llm", fail_one_provider_section)
    summary = ai_engine.summarize_pdf(source)
    citations = ai_engine.align_answer_citations(summary, set(range(1, 70)))[1]

    assert "Executive Summary (Offline Analysis)" in summary
    assert "Chunk recovery decision: preserve every record from the affected pages." in summary
    assert set(range(13, 25)).issubset(citations)
    assert len(calls) == 6


def test_translation_provider_failure_reports_safe_upstream_class(monkeypatch):
    import pytest

    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "configured")
    monkeypatch.setattr(
        ai_engine,
        "call_llm",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("AI service returned HTTP 429. Please try again.")),
    )

    with pytest.raises(RuntimeError, match="upstream HTTP 429"):
        ai_engine._translate_text_batch([(0, "source text")], "Spanish")


def test_translation_provider_failure_http_mapping_is_actionable():
    import server

    assert server.translation_failure_response(RuntimeError("Translation provider failed (upstream HTTP 429).")) == (
        429,
        "The translation provider is rate limited (upstream HTTP 429). Please retry shortly.",
        {"Retry-After": "30"},
    )
    assert server.translation_failure_response(RuntimeError("Translation provider failed (network timeout or connection error)."))[0] == 504
    assert server.translation_failure_response(RuntimeError("Translation provider failed (upstream HTTP 401)."))[0] == 503


def test_translation_batch_requires_structured_json(monkeypatch):
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")
    captured = {}

    def fake_call_llm(system_prompt, user_prompt, timeout_seconds=None, max_attempts=2):
        captured["timeout"] = timeout_seconds
        return json.dumps({"translations": [{"id": 0, "text": "Texto traducido"}]})

    monkeypatch.setattr(ai_engine, "call_llm", fake_call_llm)
    result = ai_engine._translate_text_batch([(0, "Translated text")], "Spanish")

    assert result == {0: "Texto traducido"}
    assert captured["timeout"] == ai_engine.TRANSLATION_CALL_TIMEOUT_SECONDS
    assert ai_engine._parse_translation_batch("not json", [0]) == {}


def test_translation_zero_result_fails_without_emitting_source_disguised_as_translation(tmp_path, monkeypatch):
    import pytest
    source = tmp_path / "source.pdf"
    output = tmp_path / "translated.pdf"
    make_pdf(source)
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")
    monkeypatch.setattr(ai_engine, "GEMINI_API_KEY", "")
    monkeypatch.setattr(ai_engine, "OPENAI_API_KEY", "")
    monkeypatch.setattr(ai_engine, "call_llm", lambda *args, **kwargs: "provider timed out")

    report = {}
    with pytest.raises(RuntimeError, match="No text was translated"):
        ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    assert not output.exists()
    assert report["fallback_used"] is True
    assert report["blocks_translated"] == 0
    assert report["blocks_seen"] >= 1
    assert "No text blocks were translated" in report["warnings"][-1]


def test_translation_reports_upstream_rate_limit_when_all_batches_fail(tmp_path, monkeypatch):
    import server

    source = tmp_path / "rate-limited-source.pdf"
    output = tmp_path / "rate-limited-output.pdf"
    make_pdf(source)
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "configured-test-key")

    def rate_limited(*_args, **_kwargs):
        raise RuntimeError("Translation provider failed (upstream HTTP 429).")

    monkeypatch.setattr(ai_engine, "_translate_text_batch", rate_limited)
    report = {}
    with pytest.raises(RuntimeError, match="upstream HTTP 429") as failure:
        ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    assert "No text was translated" in str(failure.value)
    assert report["failure_class"] == ["upstream HTTP 429"]
    assert server.translation_failure_response(failure.value)[0] == 429
    assert not output.exists()


def test_translation_repairs_segments_omitted_from_partial_provider_batch(tmp_path, monkeypatch):
    source = tmp_path / "partial-batch-source.pdf"
    output = tmp_path / "partial-batch-translated.pdf"
    with fitz.open() as document:
        page = document.new_page()
        for y, text in ((72, "Source paragraph alpha."), (100, "Source paragraph bravo."), (128, "Source paragraph charlie.")):
            page.insert_text((72, y), text)
        document.save(source)

    monkeypatch.setattr(ai_engine, "TRANSLATION_BATCH_SIZE", 4)
    monkeypatch.setattr(ai_engine, "TRANSLATION_MAX_PARALLEL_BATCHES", 1)
    calls = []

    def partial_then_complete(batch, *_args, **_kwargs):
        calls.append([block_id for block_id, _ in batch])
        if len(calls) == 1:
            block_id = batch[0][0]
            return {block_id: f"Párrafo traducido {block_id}."}
        return {block_id: f"Párrafo traducido {block_id}." for block_id, _ in batch}

    monkeypatch.setattr(ai_engine, "_translate_text_batch", partial_then_complete)
    report = {}
    ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    assert output.exists()
    assert len(calls) == 3
    assert report["blocks_translated"] == 3
    assert report["partial_translation_repair"] == {
        "requests": 2,
        "segments_requested": 2,
        "segments_recovered": 2,
        "segments_missing": 2,
        "segments_remaining": 0,
        "segments_deferred": 0,
    }
    with fitz.open(output) as translated:
        text = translated[0].get_text()
    assert "Párrafo traducido 0" in text
    assert "Párrafo traducido 1" in text
    assert "Párrafo traducido 2" in text


def test_translation_reuses_identical_segments_across_repeated_pages(tmp_path, monkeypatch):
    """A provider with a small response budget should translate repeated page text once."""
    source = tmp_path / "repeated-pages.pdf"
    output = tmp_path / "translated-repeated-pages.pdf"
    repeated = (
        "Free local PDF tools for everyone.",
        "This page demonstrates document translation.",
        "Every sample file is available for testing.",
        "No account, upload, or tracking is required.",
    )
    with fitz.open() as document:
        for number in range(1, 6):
            page = document.new_page()
            for index, text in enumerate((f"Page {number} translation sample.", *repeated)):
                page.insert_text((72, 72 + 45 * index), text)
        document.save(source)

    requested: list[int] = []

    def response_limited_provider(batch, *_args, **_kwargs):
        # The live provider returned only 10 of 25 repeated blocks. Model a
        # ten-item response ceiling; smaller repair calls cannot recover more.
        if len(batch) <= 2:
            raise RuntimeError("provider response budget exhausted")
        requested.extend(block_id for block_id, _ in batch)
        return {block_id: f"Texto traducido {block_id}." for block_id, _ in batch[:10]}

    monkeypatch.setattr(ai_engine, "_translate_text_batch", response_limited_provider)
    report = {}
    ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    assert output.exists()
    assert report["blocks_seen"] == 25
    assert report["blocks_translated"] == 25
    assert report["text_segments_seen"] == 25
    assert report["text_segments_unique"] == 9
    assert report["translated_segment_fraction"] == 1.0
    assert len(requested) == 9
    with fitz.open(output) as translated:
        assert translated.page_count == 5
        assert all("Texto traducido" in page.get_text() for page in translated)


def test_translation_keeps_light_text_readable_on_dark_page_header(tmp_path, monkeypatch):
    source = tmp_path / "dark-header.pdf"
    output = tmp_path / "translated-dark-header.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.draw_rect(fitz.Rect(0, 0, page.rect.width, 92), color=None, fill=(0.04, 0.16, 0.48))
        page.insert_text((48, 55), "White title on a blue header", fontsize=24, color=(1, 1, 1))
        page.insert_text((48, 145), "Ordinary body paragraph", fontsize=13, color=(0.15, 0.15, 0.2))
        document.save(source)

    def translate(batch, *_args, **_kwargs):
        return {segment_id: ("Título blanco traducido" if text.startswith("White title")
                             else "Párrafo del contenido traducido") for segment_id, text in batch}

    monkeypatch.setattr(ai_engine, "_translate_text_batch", translate)
    report = {}
    ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)
    assert report["blocks_translated"] == 2
    with fitz.open(output) as translated:
        page = translated[0]
        assert "Título blanco traducido" in page.get_text()
        title_pixels = page.get_pixmap(matrix=fitz.Matrix(2, 2),
                                       clip=fitz.Rect(48, 30, 360, 65), alpha=False)
        samples = title_pixels.samples
        bright_pixels = sum(1 for index in range(0, len(samples), title_pixels.n)
                            if all(channel > 220 for channel in samples[index:index + 3]))
        assert bright_pixels > 50, bright_pixels


def test_translation_batches_cap_count_and_prompt_characters_without_dropping_segments():
    segments = [(index, "x" * length) for index, length in enumerate([20] * 40 + [1_600] * 10)]
    batches = ai_engine._build_translation_batches(segments)

    assert ai_engine.TRANSLATION_BATCH_SIZE == 16
    assert ai_engine.TRANSLATION_BATCH_MAX_CHARACTERS == 12_000
    assert [segment for batch in batches for segment in batch] == segments
    assert all(len(batch) <= 16 for batch in batches)
    assert all(sum(len(text) for _, text in batch) <= 12_000 for batch in batches)


def test_translation_repairs_a_fully_failed_provider_batch_with_smaller_retries(tmp_path, monkeypatch):
    source = tmp_path / "failed-batch-source.pdf"
    output = tmp_path / "failed-batch-translated.pdf"
    with fitz.open() as document:
        page = document.new_page()
        for index in range(10):
            page.insert_text((72, 60 + index * 28), f"Source paragraph {index:02d}.")
        document.save(source)

    monkeypatch.setattr(ai_engine, "TRANSLATION_BATCH_SIZE", 20)
    monkeypatch.setattr(ai_engine, "TRANSLATION_MAX_PARALLEL_BATCHES", 1)
    calls = []

    def fail_once_then_translate(batch, *_args, **_kwargs):
        calls.append([block_id for block_id, _ in batch])
        if len(calls) == 1:
            raise RuntimeError("Translation provider failed (upstream HTTP 504).")
        return {block_id: f"Párrafo traducido {block_id}." for block_id, _ in batch}

    monkeypatch.setattr(ai_engine, "_translate_text_batch", fail_once_then_translate)
    report = {}
    ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    assert output.exists()
    assert len(calls) == 6  # One failed batch followed by five two-segment repairs.
    assert report["blocks_translated"] == 10
    assert report["partial_translation_repair"] == {
        "requests": 5,
        "segments_requested": 10,
        "segments_recovered": 10,
        "segments_missing": 10,
        "segments_remaining": 0,
        "segments_deferred": 0,
    }
    assert not any("untranslated source text was preserved" in warning for warning in report["warnings"])
    with fitz.open(output) as translated:
        text = translated[0].get_text()
    assert all(f"Párrafo traducido {index}" in text for index in range(10))
    assert "Source paragraph 08." not in text and "Source paragraph 09." not in text


def test_translation_repair_repeats_progress_rounds_until_every_segment_is_recovered(tmp_path, monkeypatch):
    source = tmp_path / "progress-rounds-source.pdf"
    output = tmp_path / "progress-rounds-translated.pdf"
    with fitz.open() as document:
        page = document.new_page()
        for index in range(6):
            page.insert_text((72, 60 + index * 38), f"Source segment marker {index:02d}.")
        document.save(source)

    monkeypatch.setattr(ai_engine, "TRANSLATION_BATCH_SIZE", 8)
    monkeypatch.setattr(ai_engine, "TRANSLATION_MAX_PARALLEL_BATCHES", 1)
    calls = []

    def one_repair_segment_at_a_time(batch, *_args, **_kwargs):
        calls.append([block_id for block_id, _ in batch])
        if len(calls) == 1:
            raise RuntimeError("Translation provider failed (upstream HTTP 504).")
        block_id = batch[0][0]
        return {block_id: f"Segmento traducido {block_id}."}

    monkeypatch.setattr(ai_engine, "_translate_text_batch", one_repair_segment_at_a_time)
    report = {}
    ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    assert len(calls) == 7  # One initial failure, then 3 + 2 + 1 progress-round repairs.
    assert report["blocks_translated"] == 6
    assert report["partial_translation_repair"] == {
        "requests": 6,
        "segments_requested": 6,
        "segments_recovered": 6,
        "segments_missing": 6,
        "segments_remaining": 0,
        "segments_deferred": 0,
    }
    assert any("smaller retries recovered all affected text" in warning for warning in report["warnings"])
    with fitz.open(output) as translated:
        text = translated[0].get_text()
    assert all(f"Segmento traducido {index}" in text for index in range(6))
    assert all(f"Source segment marker {index:02d}." not in text for index in range(6))


def test_translation_provider_fanout_is_capped_at_two_concurrent_batches(tmp_path, monkeypatch):
    import threading

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "configured-test-key")
    source = tmp_path / "bounded-provider-fanout-source.pdf"
    output = tmp_path / "bounded-provider-fanout-output.pdf"
    with fitz.open() as document:
        page = document.new_page()
        for index in range(8):
            page.insert_text((72, 72 + index * 24), f"Source paragraph {index}.")
        document.save(source)

    monkeypatch.setattr(ai_engine, "TRANSLATION_BATCH_SIZE", 1)
    assert ai_engine.TRANSLATION_MAX_PARALLEL_BATCHES == 2
    active = 0
    peak = 0
    lock = threading.Lock()

    def bounded_provider(batch, *_args, **_kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.02)
            return {block_id: f"Párrafo traducido {block_id}." for block_id, _ in batch}
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(ai_engine, "_translate_text_batch", bounded_provider)
    report = {}
    ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    assert output.exists()
    assert peak == 2
    assert report["blocks_translated"] == 8
    with fitz.open(output) as translated:
        output_text = translated[0].get_text()
    assert all(f"Párrafo traducido {index}" in output_text for index in range(8))


def test_short_document_chat_uses_full_context_but_keeps_unsupported_queries_uncited(tmp_path, monkeypatch):
    source = tmp_path / "income-certificate.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Income Certificate\nCertificate No: TN-4202608046409\nDate: 2026-08-04\nApplicant Name: Priya Raman",
    )
    doc.save(str(source))
    doc.close()

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", True)
    result = ai_engine.chat_with_pdf(source, "What is the certificate number and applicant name?")
    assert result["citations"] == [1]
    assert "TN-4202608046409" in result["answer"]
    assert "Priya Raman" in result["answer"]

    unsupported = ai_engine.chat_with_pdf(source, "According to this PDF, what is the atmospheric composition of Mars?")
    assert unsupported["citations"] == []
    assert "no relevant information" in unsupported["answer"].lower()


def test_tokenization_preserves_short_and_hyphenated_identifiers():
    assert ai_engine._tokenize("No ID TN-4202608046409") == ["no", "id", "tn-4202608046409"]


def test_scanned_pdf_uses_mupdf_ocr_when_native_text_is_empty(tmp_path):
    image_path = tmp_path / "scanned-certificate.png"
    pdf_path = tmp_path / "scanned-certificate.pdf"
    image = Image.new("RGB", (1400, 700), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    draw.text((60, 80), "Income Certificate", fill="black", font=font)
    draw.text((60, 180), "Certificate No: TN-4202608046409", fill="black", font=font)
    draw.text((60, 280), "Applicant Name: Priya Raman", fill="black", font=font)
    image.save(image_path)

    doc = fitz.open()
    page = doc.new_page(width=1400, height=700)
    page.insert_image(page.rect, filename=str(image_path))
    doc.save(str(pdf_path))
    doc.close()

    chunks = ai_engine.extract_chunks_from_pdf(pdf_path)
    extracted = "\n".join(chunk.text for chunk in chunks)
    assert "Certificate" in extracted
    assert ("TN-4202608046409" in extracted or "4202608046409" in extracted)
    assert "Priya Raman" in extracted


def test_ai_chat_and_summarize_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from server import app

    client = TestClient(app)
    pdf_path = tmp_path / "test_doc.pdf"
    make_pdf(pdf_path)

    # 1. Document questions remain useful without an AI key through cited local extraction.
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "")
    monkeypatch.setenv("BLUESMINDS_API_KEY", "")

    with open(pdf_path, "rb") as f:
        res = client.post("/api/ai/chat", data={"question": "What is the deadline?"}, files={"file": ("test.pdf", f, "application/pdf")})
    assert res.status_code == 200
    assert "October 25, 2026" in res.json()["answer"]
    assert res.json()["citations"] == [1]
    assert res.json()["fallback_used"] is True

    with open(pdf_path, "rb") as f:
        res = client.post("/api/ai/summarize", files={"file": ("test.pdf", f, "application/pdf")})
    assert res.status_code == 200
    assert res.json().get("summary")

    # 2. When BLUESMINDS_API_KEY is present and upstream succeeds -> HTTP 200 with result
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "valid-test-key")
    monkeypatch.setattr(ai_engine, "call_llm", lambda sys, usr, timeout_seconds=None, **kwargs: "October 25, 2026 is the deadline [Page 1].")

    with open(pdf_path, "rb") as f:
        res = client.post("/api/ai/chat", data={"question": "What is the deadline?"}, files={"file": ("test.pdf", f, "application/pdf")})
    assert res.status_code == 200
    data = res.json()
    assert "October 25, 2026" in data["answer"]
    assert "provider" not in data
    assert "model" not in data

    with open(pdf_path, "rb") as f:
        res = client.post("/api/ai/summarize", files={"file": ("test.pdf", f, "application/pdf")})
    assert res.status_code == 200
    assert "October 25, 2026" in res.json()["summary"]

    # 3. When call fails -> HTTP 502 "AI request failed, please try again"
    def fail_call(*args, **kwargs):
        raise RuntimeError("AI request failed, please try again")

    monkeypatch.setattr(ai_engine, "call_llm", fail_call)
    with open(pdf_path, "rb") as f:
        res = client.post("/api/ai/chat", data={"question": "What is the deadline?"}, files={"file": ("test.pdf", f, "application/pdf")})
    assert res.status_code == 502
    assert res.json()["detail"] == "AI request failed, please try again"

    with open(pdf_path, "rb") as f:
        res = client.post("/api/ai/summarize", files={"file": ("test.pdf", f, "application/pdf")})
    assert res.status_code == 200
    assert res.json().get("summary")
