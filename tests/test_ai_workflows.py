from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import fitz
from PIL import Image, ImageDraw, ImageFont

import ai_engine


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
    import pytest
    with pytest.raises(ValueError, match="AI provider is not configured"):
        ai_engine.call_bluesminds("system", "user")


def test_bluesminds_network_failure_raises_clear_error(monkeypatch):
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")

    import pytest
    with patch("ai_engine.urllib.request.urlopen", side_effect=URLError("offline")):
        with pytest.raises(RuntimeError, match="AI service could not be reached or timed out"):
            ai_engine.call_bluesminds("system", "user")


def test_bluesminds_uses_fresh_environment_key(monkeypatch):
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", ai_engine._INITIAL_BLUESMINDS_API_KEY)
    monkeypatch.setenv("BLUESMINDS_API_KEY", "fresh-bluesminds-key-from-environment")
    monkeypatch.setattr(ai_engine, "BLUESMINDS_MODEL", "owner/configured-model")

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"upstream response"}}]}'

    with patch("ai_engine.urllib.request.urlopen", return_value=FakeResponse()) as open_url:
        assert ai_engine.call_bluesminds("system", "user") == "upstream response"

    request = open_url.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer fresh-bluesminds-key-from-environment"
    assert json.loads(request.data)["model"] == "owner/configured-model"
    assert open_url.call_count == 1


def test_bluesminds_retries_transient_first_attempt(monkeypatch):
    from urllib.error import HTTPError

    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def read(self): return b'{"choices":[{"message":{"content":"first successful response"}}]}'

    with patch("ai_engine.urllib.request.urlopen", side_effect=[HTTPError("https://provider.invalid", 503, "busy", {}, None), FakeResponse()]) as open_url, patch("ai_engine.time.sleep"):
        assert ai_engine.call_bluesminds("system", "user", timeout_seconds=8) == "first successful response"
    assert open_url.call_count == 2


def test_bluesminds_stream_parses_provider_deltas(monkeypatch):
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"Hello "}}]}\n'
            yield b'data: {"choices":[{"delta":{"content":"there."}}]}\n'
            yield b'data: [DONE]\n'

    with patch("ai_engine.urllib.request.urlopen", return_value=FakeResponse()) as open_url:
        assert list(ai_engine.stream_bluesminds("system", "user")) == ["Hello ", "there."]
    request = open_url.call_args.args[0]
    assert json.loads(request.data)["stream"] is True


def test_bluesminds_stream_retries_transient_failure_before_first_token(monkeypatch):
    from urllib.error import HTTPError

    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"recovered"}}]}\n'
            yield b'data: [DONE]\n'

    with patch("ai_engine.urllib.request.urlopen", side_effect=[HTTPError("https://provider.invalid", 503, "busy", {}, None), FakeResponse()]) as open_url, patch("ai_engine.time.sleep"):
        assert list(ai_engine.stream_bluesminds("system", "user")) == ["recovered"]
    assert open_url.call_count == 2


def test_bluesminds_stream_does_not_restart_after_partial_output(monkeypatch):
    import pytest

    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "test-key")

    class PartialResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_value, traceback): return False
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n'
            raise URLError("connection dropped")

    with patch("ai_engine.urllib.request.urlopen", return_value=PartialResponse()) as open_url:
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
    assert "Hello!" in response.json()["answer"]
    assert response.json()["citations"] == []

    document_question = client.post("/api/ai/chat", data={"question": "What is the deadline in the PDF?"})
    assert document_question.status_code == 200
    assert "No PDF is open" in document_question.json()["answer"]


def test_ai_first_attempt_general_identity_and_code_scope(monkeypatch):
    from fastapi.testclient import TestClient
    from server import app

    monkeypatch.setattr(ai_engine, "call_llm", lambda system, user, timeout_seconds=None: "A direct answer on the first request.")
    client = TestClient(app)
    response = client.post("/api/ai/chat", data={"question": "Hello, how are you?"})
    assert response.status_code == 200
    assert response.json()["answer"] == "A direct answer on the first request."

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
    with pytest.raises(RuntimeError, match="No text was translated"):
        ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    assert not output.exists()
    assert report["fallback_used"] is True
    assert report["blocks_translated"] == 0
    assert report["blocks_preserved"] >= 1
    assert "No text blocks were translated" in report["warnings"][-1]


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

    unsupported = ai_engine.chat_with_pdf(source, "What is the atmospheric composition of Mars?")
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

    # 1. When BLUESMINDS_API_KEY is missing -> HTTP 503 "AI provider is not configured"
    monkeypatch.setattr(ai_engine, "BLUESMINDS_API_KEY", "")
    monkeypatch.setenv("BLUESMINDS_API_KEY", "")

    with open(pdf_path, "rb") as f:
        res = client.post("/api/ai/chat", data={"question": "What is the deadline?"}, files={"file": ("test.pdf", f, "application/pdf")})
    assert res.status_code == 503
    assert res.json()["detail"] == "AI provider is not configured"

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
