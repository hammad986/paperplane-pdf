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


def test_agentrouter_network_failure_does_not_retry(monkeypatch):
    monkeypatch.setattr(ai_engine, "AGENTROUTER_API_KEY", "test-key")
    monkeypatch.setattr(ai_engine, "AGENTROUTER_MAX_RETRIES", 1)

    with patch("ai_engine.urllib.request.urlopen", side_effect=URLError("offline")) as open_url:
        assert ai_engine.call_agentrouter("system", "user") == ""

    assert open_url.call_count == 1
    assert open_url.call_args.kwargs["timeout"] <= 8


def test_agentrouter_uses_fresh_environment_key(monkeypatch):
    monkeypatch.setattr(ai_engine, "AGENTROUTER_API_KEY", ai_engine._INITIAL_AGENTROUTER_API_KEY)
    monkeypatch.setenv("AGENTROUTER_API_KEY", "fresh-key-from-environment")

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"upstream response"}}]}'

    with patch("ai_engine.urllib.request.urlopen", return_value=FakeResponse()) as open_url:
        assert ai_engine.call_agentrouter("system", "user") == "upstream response"

    request = open_url.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer fresh-key-from-environment"


def test_translation_batch_requires_structured_json(monkeypatch):
    monkeypatch.setattr(ai_engine, "AGENTROUTER_API_KEY", "test-key")
    captured = {}

    def fake_call_llm(system_prompt, user_prompt, timeout_seconds=None):
        captured["timeout"] = timeout_seconds
        return json.dumps({"translations": [{"id": 0, "text": "Texto traducido"}]})

    monkeypatch.setattr(ai_engine, "call_llm", fake_call_llm)
    result = ai_engine._translate_text_batch([(0, "Translated text")], "Spanish")

    assert result == {0: "Texto traducido"}
    assert captured["timeout"] == 6.0
    assert ai_engine._parse_translation_batch("not json", [0]) == {}


def test_translation_fallback_preserves_source_text(tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    output = tmp_path / "translated.pdf"
    make_pdf(source)
    monkeypatch.setattr(ai_engine, "AGENTROUTER_API_KEY", "test-key")
    monkeypatch.setattr(ai_engine, "GEMINI_API_KEY", "")
    monkeypatch.setattr(ai_engine, "OPENAI_API_KEY", "")
    monkeypatch.setattr(ai_engine, "call_llm", lambda *args, **kwargs: "provider timed out")

    report = {}
    ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    translated_doc = fitz.open(str(output))
    text = "\n".join(page.get_text() for page in translated_doc)
    translated_doc.close()

    assert output.exists()
    assert "Paperplane document intelligence" in text
    assert report["fallback_used"] is True
    assert report["blocks_translated"] == 0
    assert report["blocks_preserved"] >= 1
    assert "[ES]" not in text


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
