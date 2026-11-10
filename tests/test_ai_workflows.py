from __future__ import annotations

import json
from pathlib import Path
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

    client = TestClient(app)
    headers = {"X-Forwarded-For": "198.51.100.42"}
    for _ in range(12):
        assert client.get("/api/ai/capabilities", headers=headers).status_code == 200
    limited = client.get("/api/ai/capabilities", headers=headers)
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
    for question, answer in expected.items():
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
    monkeypatch.setattr(ai_engine, "summarize_pdf", lambda _path: (time.sleep(0.15), "late response")[1])
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
    monkeypatch.setattr(ai_engine, "call_llm", lambda system, user, timeout_seconds=None: captured.setdefault("prompt", user) or "ok")
    summary = ai_engine.summarize_pdf(source)
    assert "Page 20" in captured["prompt"]
    assert summary

    def answer_page(system, prompt, timeout_seconds=None):
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
    def summarize_chunk(system, prompt, timeout_seconds=None):
        calls.append((prompt, timeout_seconds))
        if prompt.startswith("Synthesize these page-grounded"):
            return "The document covers its opening topic [Page 1] and final topic [Page 69]."
        pages = [int(value) for value in __import__("re").findall(r"--- Page (\d+) ---", prompt)]
        return f"Section summary spans [Page {pages[0]}] through [Page {pages[-1]}]."

    monkeypatch.setattr(ai_engine, "call_llm", summarize_chunk)
    summary = ai_engine.summarize_pdf(source)

    assert len(calls) == 4
    included_pages = {
        int(value)
        for prompt, _ in calls[:3]
        for value in __import__("re").findall(r"--- Page (\d+) ---", prompt)
    }
    assert included_pages == set(range(1, 70))
    assert all(timeout == 35 for _, timeout in calls)
    assert "[Page 1]" in summary and "[Page 69]" in summary


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

    def fake_call_llm(system_prompt, user_prompt, timeout_seconds=None):
        captured["timeout"] = timeout_seconds
        return json.dumps({"translations": [{"id": 0, "text": "Texto traducido"}]})

    monkeypatch.setattr(ai_engine, "call_llm", fake_call_llm)
    result = ai_engine._translate_text_batch([(0, "Translated text")], "Spanish")

    assert result == {0: "Texto traducido"}
    assert captured["timeout"] == 6.0
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
    with pytest.raises(RuntimeError, match="invalid structured response"):
        ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    assert not output.exists()
    assert report["fallback_used"] is True
    assert report["blocks_translated"] == 0
    assert report["blocks_seen"] >= 1
    assert "invalid structured response" in report["warnings"][-1]


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
    assert res.status_code == 503
    assert res.json()["detail"] == "AI provider is not configured"

    # 2. When BLUESMINDS_API_KEY is present and upstream succeeds -> HTTP 200 with result
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "valid-test-key")
    monkeypatch.setattr(ai_engine, "call_llm", lambda sys, usr, timeout_seconds=None: "October 25, 2026 is the deadline [Page 1].")

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
    assert res.status_code == 502
    assert res.json()["detail"] == "AI request failed, please try again"
