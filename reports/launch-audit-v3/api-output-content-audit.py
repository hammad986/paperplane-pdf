from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import fitz
import requests


BASE = "http://127.0.0.1:8501"
OUT = Path("reports/launch-audit-v3")
SOURCE = Path("web/assets/sample_document.pdf")
THREE_PAGES = Path("runtime_data_codex_audit/delete_3pages_audit.pdf")


def create_colored_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(fitz.Rect(100, 150, 495, 700), color=(0.8, 0.05, 0.05), fill=(0.9, 0.08, 0.08))
    page.insert_text((120, 120), "Paperplane color verification page", fontsize=18, color=(0.1, 0.2, 0.8))
    doc.save(path)
    doc.close()


def create_form_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    widget = fitz.Widget()
    widget.field_name = "ApplicantName"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.rect = fitz.Rect(72, 100, 320, 130)
    page.add_widget(widget)
    doc.save(path)
    doc.close()


def run_job(session: requests.Session, operation: str, path: Path, options: dict, name: str) -> Path:
    with path.open("rb") as handle:
        response = session.post(
            BASE + "/api/jobs",
            data={"operation": operation, "options": json.dumps(options)},
            files={"files": (name, handle, "application/pdf")},
            timeout=60,
        )
    response.raise_for_status()
    job = response.json()
    for _ in range(480):
        status_response = session.get(BASE + job["status_url"], timeout=10)
        status_response.raise_for_status()
        row = status_response.json()
        if row.get("status") in {"completed", "failed"}:
            break
        time.sleep(0.25)
    if row.get("status") != "completed":
        raise RuntimeError(f"{operation} job failed: {row}")
    output = session.get(BASE + job["download_url"], timeout=60)
    output.raise_for_status()
    # The server chooses output extensions; retain them while using stable local names.
    content_type = output.headers.get("content-type", "")
    disposition = output.headers.get("content-disposition", "output.pdf")
    suggested_name = disposition.rsplit("filename=", 1)[-1].strip().strip('"')
    suffix = Path(suggested_name).suffix
    if not suffix:
        suffix = ".pdf" if "pdf" in content_type else ".bin"
    destination = OUT / f"content_{name}_{operation}{suffix}"
    destination.write_bytes(output.content)
    return destination


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    colored = Path("runtime_data_codex_audit/color-audit.pdf")
    form = Path("runtime_data_codex_audit/form-audit.pdf")
    create_colored_pdf(colored)
    create_form_pdf(form)
    session = requests.Session()
    results: dict[str, object] = {}

    merged_split = run_job(session, "split", THREE_PAGES, {"split_mode": "all_pages"}, "split-input.pdf")
    with zipfile.ZipFile(merged_split) as archive:
        names = archive.namelist()
        member_checks = []
        for member in names:
            content = archive.read(member)
            doc = fitz.open(stream=content, filetype="pdf")
            member_checks.append({"name": member, "pages": doc.page_count, "text": doc[0].get_text().strip()})
            doc.close()
    results["split_zip"] = {"zip_entries": len(names), "members": member_checks}

    rotated = run_job(session, "rotate", SOURCE, {"degrees": 90}, "rotate-input.pdf")
    doc = fitz.open(rotated)
    results["rotate"] = {"pages": doc.page_count, "rotation_degrees": doc[0].rotation, "contains_page_1_text": "verified test page #1" in doc[0].get_text().lower()}
    doc.close()

    protected = run_job(session, "protect", SOURCE, {"password": "LocalAudit-2026!"}, "protect-input.pdf")
    doc = fitz.open(protected)
    wrong_password_rejected = doc.authenticate("incorrect-audit-password") == 0
    correct_password_result = doc.authenticate("LocalAudit-2026!")
    protected_state = {"needs_password": doc.needs_pass, "wrong_password_rejected": wrong_password_rejected, "known_local_password_accepted": bool(correct_password_result), "pages_after_auth": doc.page_count if correct_password_result else 0}
    doc.close()
    unlocked = run_job(session, "unlock", protected, {"password": "LocalAudit-2026!"}, "protected-audit.pdf")
    doc = fitz.open(unlocked)
    results["protect_unlock"] = {**protected_state, "unlocked_needs_password": doc.needs_pass, "unlocked_pages": doc.page_count, "unlocked_contains_page_1_text": "verified test page #1" in doc[0].get_text().lower()}
    doc.close()

    compressed = run_job(session, "compress", SOURCE, {"preset": "100kb"}, "compress-input.pdf")
    doc = fitz.open(compressed)
    results["compress"] = {"input_bytes": SOURCE.stat().st_size, "output_bytes": compressed.stat().st_size, "pages": doc.page_count, "contains_page_1_text": "verified test page #1" in doc[0].get_text().lower()}
    doc.close()

    gray = run_job(session, "grayscale", colored, {}, "grayscale-input.pdf")
    doc = fitz.open(gray)
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(0.25, 0.25), colorspace=fitz.csRGB)
    samples = pix.samples
    rgb_pixels = len(samples) // 3
    grayscale_pixels = sum(1 for i in range(0, len(samples), 3) if samples[i] == samples[i + 1] == samples[i + 2])
    results["grayscale"] = {"pages": doc.page_count, "sample_pixels": rgb_pixels, "equal_rgb_pixels": grayscale_pixels, "all_sampled_pixels_neutral": grayscale_pixels == rgb_pixels, "contains_text": "Paperplane color verification page" in doc[0].get_text()}
    doc.close()

    filled = run_job(session, "forms", form, {"fields": {"ApplicantName": "Local Audit User"}}, "form-input.pdf")
    doc = fitz.open(filled)
    widgets = [widget for page in doc for widget in (page.widgets() or [])]
    results["form_fill"] = {"pages": doc.page_count, "field_values": {widget.field_name: widget.field_value for widget in widgets}, "expected_value_present": any(widget.field_name == "ApplicantName" and widget.field_value == "Local Audit User" for widget in widgets)}
    doc.close()

    metadata = run_job(session, "metadata", SOURCE, {"title": "Local metadata verification", "author": "Audit Fixture"}, "metadata-input.pdf")
    doc = fitz.open(metadata)
    results["metadata"] = {"pages": doc.page_count, "title": doc.metadata.get("title"), "author": doc.metadata.get("author"), "contains_page_1_text": "verified test page #1" in doc[0].get_text().lower()}
    doc.close()

    markdown = run_job(session, "pdf_to_markdown", SOURCE, {}, "markdown-input.pdf")
    markdown_text = markdown.read_text(encoding="utf-8")
    results["pdf_to_markdown"] = {"filename": markdown.name, "bytes": markdown.stat().st_size, "contains_source_title": "Paperplane PDF Sample Document" in markdown_text, "contains_page_1_text": "verified test page #1" in markdown_text, "preview": markdown_text[:220]}

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
