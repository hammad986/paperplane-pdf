import fitz
from PIL import Image
from fastapi.testclient import TestClient

import converters
import server


def test_page_numbers_substitute_both_user_template_tokens(tmp_path):
    source = tmp_path / "six-pages.pdf"
    with fitz.open() as document:
        for _ in range(6):
            document.new_page()
        document.save(source)

    output = server.process("page_numbers", [source], {"format": "Page {n} of {total}"}, tmp_path)
    with fitz.open(output) as document:
        assert "Page 1 of 6" in document[0].get_text()
        assert "Page 6 of 6" in document[5].get_text()


def test_public_billing_status_does_not_disclose_payment_order_id(monkeypatch):
    monkeypatch.setattr(server, "get_user", lambda _user_id: {
        "id": "test-user", "tier": "pro", "subscription_status": "active",
        "payment_customer_id": "customer-private", "cashfree_order_id": "order-private",
    })
    monkeypatch.setattr(server, "get_user_tier", lambda _user_id: "pro")
    monkeypatch.setattr(server, "get_daily_usage", lambda _subject: 0)
    server.app.dependency_overrides[server.current_user] = lambda: "test-user"
    try:
        response = TestClient(server.app).get("/api/billing/status")
        assert response.status_code == 200
        assert "cashfree_order_id" not in response.json()
        assert "order-private" not in response.text
    finally:
        server.app.dependency_overrides.pop(server.current_user, None)


def test_compression_preservation_warning_reaches_completed_job(monkeypatch, tmp_path):
    source = tmp_path / "source.pdf"
    with fitz.open() as document:
        document.new_page()
        document.save(source)
    output = None
    warnings = []

    def fake_converter(_func, _source, destination, **_kwargs):
        with fitz.open(source) as document:
            document.save(destination)
        return {"content_preserved_original": True, "note": "The readable original was preserved."}

    monkeypatch.setattr(server, "run_converter_with_timeout", fake_converter)
    output = server.process("compress", [source], {"preset": "balanced"}, tmp_path)
    assert output.exists()
    assert "readable original was preserved" in (tmp_path / ".job-warning").read_text(encoding="utf-8").lower()
    job_dir = tmp_path / "job-123"
    job_dir.mkdir()
    job_output = job_dir / "preserved.pdf"
    job_output.write_bytes(output.read_bytes())
    (job_dir / ".job-warning").write_text("Readable original preserved; target not reached.", encoding="utf-8")
    monkeypatch.setattr(server, "JOBS", tmp_path)
    monkeypatch.setattr(server, "process", lambda *_args, **_kwargs: job_output)
    monkeypatch.setattr(server, "update_job", lambda _job_id, **values: warnings.append(values.get("warning")) if "warning" in values else None)

    server.run_job("job-123", "compress", [source], {}, None)

    assert warnings == ["Readable original preserved; target not reached."]


def test_scan_to_pdf_uses_selected_physical_page_size(tmp_path):
    image_path = tmp_path / "camera-photo.png"
    Image.new("RGB", (1600, 1200), (235, 235, 235)).save(image_path)

    a4_output = tmp_path / "a4.pdf"
    letter_output = tmp_path / "letter.pdf"
    original_output = tmp_path / "original.pdf"
    converters.scan_to_pdf([image_path], a4_output, page_size="a4")
    converters.scan_to_pdf([image_path], letter_output, page_size="letter")
    converters.scan_to_pdf([image_path], original_output, page_size="original")

    with fitz.open(a4_output) as document:
        assert abs(document[0].rect.width - 841.89) < 1
        assert abs(document[0].rect.height - 595.28) < 1
        assert document[0].get_images()
    with fitz.open(letter_output) as document:
        assert abs(document[0].rect.width - 792) < 1
        assert abs(document[0].rect.height - 612) < 1
    with fitz.open(original_output) as document:
        # 1600x1200 pixels at 200 DPI, with landscape orientation.
        assert abs(document[0].rect.width - 576) < 1
        assert abs(document[0].rect.height - 432) < 1

