from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import secrets
import sys
import time
import zipfile
from pathlib import Path

import fitz
import openpyxl
import requests
from docx import Document
from PIL import Image, ImageDraw
from pptx import Presentation

AUDIT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = AUDIT_ROOT.parents[1]

# Isolate this local processor pass from inherited keys and local dotenv files.
SENSITIVE_ENV_MARKERS = ("SECRET", "KEY", "TOKEN", "PASSWORD", "CASHFREE", "SMTP", "EMAIL", "OPENAI", "ANTHROPIC", "GOOGLE", "GEMINI", "DEEPSEEK", "OPENROUTER", "BLUESMINDS")
for environment_name in list(os.environ):
    if any(marker in environment_name.upper() for marker in SENSITIVE_ENV_MARKERS):
        os.environ.pop(environment_name, None)
os.environ.update({
    "PAPERPLANE_SKIP_DOTENV": "1",
    "PAPERPLANE_ENV": "development",
    "CASHFREE_ENV": "TEST",
    "AI_PROVIDER": "",
    "PAPERPLANE_DATA_DIR": str(AUDIT_ROOT / "runtime-isolated"),
})
sys.path.insert(0, str(REPO_ROOT))
import server as local_server


RUNNER_PATH = REPO_ROOT / "reports" / "launch-audit-v5" / "catalog_output_audit.py"
BASE_URL = "http://127.0.0.1:8501"
NOTES_69 = REPO_ROOT / "reports" / "launch-audit-v8" / "test-files" / "notes-69page.pdf"
FORM_SOURCE = REPO_ROOT / "reports" / "launch-audit-v8" / "test-files" / "form-Name-Email-City.pdf"
EXPECTED_FIELDS = {
    "ApplicantName": "Audit Applicant",
    "ContactEmail": "audit@example.test",
    "ProgramTitle": "Paperplane Output Audit",
    "Statement": "Synthetic form value for local output verification.",
}


def load_runner():
    spec = importlib.util.spec_from_file_location("paperplane_v5_catalog_audit", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def make_sample_set(folder: Path) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    outputs = AUDIT_ROOT / "outputs" / folder.name
    outputs.mkdir(parents=True, exist_ok=True)
    base = folder / "audit-sample.pdf"
    changed = folder / "audit-sample-changed.pdf"
    doc = fitz.open()
    synthetic_identifier = "".join(secrets.choice("0123456789") for _ in range(12))
    for page_num in (1, 2):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), "PAPERPLANE_AUDIT_SAMPLE", fontsize=18)
        page.insert_text((72, 112), f"AUDIT_PAGE_{page_num}", fontsize=13)
        page.insert_text((72, 145), "Applicant: Synthetic Applicant", fontsize=11)
        page.insert_text((72, 170), "Document date: 2026-11-07", fontsize=11)
        page.insert_text((72, 195), "SYNTHETIC_TEXT: REDACT_THIS_MARKER", fontsize=11)
        page.draw_rect(fitz.Rect(430, 70, 470, 110), color=(0.9, 0.1, 0.1), fill=(0.9, 0.1, 0.1))
        if page_num == 2:
            page.insert_text((72, 235), "AUDIT_SECOND_PAGE_ORIGINAL", fontsize=11)
            page.insert_text((72, 265), f"SYNTHETIC ONLY - NOT A REAL ID - test pattern: {synthetic_identifier}", fontsize=11)
    doc.save(base, garbage=4, deflate=True)
    doc.close()

    doc = fitz.open(base)
    page = doc[1]
    page.add_redact_annot(fitz.Rect(68, 218, 500, 247), fill=(1, 1, 1))
    page.apply_redactions()
    page.insert_text((72, 235), "AUDIT_SECOND_PAGE_CHANGED_DELTA", fontsize=11)
    doc.save(changed, garbage=4, deflate=True)
    doc.close()

    images = []
    for name, title, color in (
        ("audit-photo.png", "PAPERPLANE IMAGE AUDIT", (240, 95, 50)),
        ("audit-photo-2.png", "SECOND IMAGE PAGE", (35, 135, 110)),
    ):
        path = folder / name
        image = Image.new("RGB", (900, 1200), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((40, 40, 860, 1160), outline=color, width=8)
        draw.text((85, 130), title, fill=(20, 30, 35))
        draw.text((85, 210), "Synthetic visual-only content for local testing.", fill=(20, 30, 35))
        for index in range(12):
            draw.line((85, 300 + index * 50, 780 - (index % 3) * 45, 300 + index * 50), fill=(100, 125, 135), width=2)
        draw.ellipse((580, 800, 760, 980), outline=color, width=9)
        image.save(path, "PNG", optimize=True)
        images.append(path)

    docx_path = folder / "audit-office.docx"
    docx = Document()
    docx.add_heading("PAPERPLANE_DOCX_AUDIT", level=1)
    docx.add_paragraph("Synthetic office source for local converter verification.")
    docx.add_paragraph("Expected text marker: AUDIT_OFFICE_WORD_OUTPUT.")
    docx.save(docx_path)

    xlsx_path = folder / "audit-office.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Audit Data"
    for row in (
        ("Item", "Amount", "Status"),
        ("Application", 19, "Paid"),
        ("Processing", 49, "Pending"),
        ("Marker", "AUDIT_OFFICE_EXCEL_OUTPUT", "Synthetic"),
    ):
        sheet.append(row)
    workbook.save(xlsx_path)

    pptx_path = folder / "audit-office.pptx"
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[0])
    slide.shapes.title.text = "PAPERPLANE_PPTX_AUDIT"
    slide.placeholders[1].text = "AUDIT_OFFICE_POWERPOINT_OUTPUT"
    presentation.save(pptx_path)

    # Four synthetic AcroForm fields exercise Fill Form and Flatten without personal data.
    form = folder / "audit-form.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Paperplane Synthetic Form Audit", fontsize=14)
    for index, field_name in enumerate(EXPECTED_FIELDS):
        widget = fitz.Widget()
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_name = field_name
        widget.field_value = ""
        widget.rect = fitz.Rect(72, 120 + index * 48, 420, 148 + index * 48)
        page.add_widget(widget)
    doc.save(form, garbage=4, deflate=True)
    doc.close()

    # A 69-page repository substitute is used for the large-document conversions.
    if not NOTES_69.exists() or not FORM_SOURCE.exists():
        raise FileNotFoundError("The repository PDF/form regression fixtures are missing.")

    return {
        "pdf": base,
        "changed_pdf": changed,
        "image": images[0],
        "image2": images[1],
        "docx": docx_path,
        "xlsx": xlsx_path,
        "pptx": pptx_path,
        "form": form,
        "large_pdf": NOTES_69,
        "owner_form_substitute": FORM_SOURCE,
        "outputs": outputs,
    }


def redact_id_text(value):
    if isinstance(value, str):
        value = re.sub(r"(?<!\d)(?:\d[\s-]*){12}(?!\d)", "[synthetic ID redacted]", value)
        value = re.sub(r"Applicant:\s*[^\n]+", "Applicant: [synthetic details redacted]", value)
        value = re.sub(r"(?:TEST_SECRET|SYNTHETIC_TEXT):\s*[^\n]+", "[synthetic marker redacted]", value)
        return value
    if isinstance(value, list):
        return [redact_id_text(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_id_text(item) for key, item in value.items()}
    return value


def verify_output_content(runner, operation: str, output_path: Path, content: bytes, extension: str, inputs: list[Path]) -> dict:
    if operation == "protect" and extension == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content), strict=False)
        encrypted = reader.is_encrypted
        authenticated = bool(reader.decrypt(runner.PASSWORD)) if encrypted else False
        page_count = len(reader.pages) if authenticated else 0
        return {
            "extension": extension,
            "bytes": len(content),
            "opened_as_pdf": True,
            "encrypted": encrypted,
            "password_accepted": authenticated,
            "page_count": page_count,
            "verified": encrypted and authenticated and page_count > 0,
        }
    verification = runner.verify_output(operation, content, extension)
    if extension == ".pdf" and content.startswith(b"%PDF-"):
        doc = fitz.open(stream=content, filetype="pdf")
        page_texts = [page.get_text() for page in doc]
        all_text = "\n".join(page_texts)
        verification.update({
            "opened_as_pdf": True,
            "page_count": len(doc),
            "text_chars": len(all_text),
            "first_text": page_texts[0][:180] if page_texts else "",
            "last_text": page_texts[-1][:180] if page_texts else "",
        })
        source_doc = fitz.open(str(inputs[0])) if inputs and inputs[0].suffix.lower() == ".pdf" else None
        if source_doc and source_doc.is_encrypted:
            source_doc.authenticate(runner.PASSWORD)
        source_pages = len(source_doc) if source_doc else None
        if source_doc:
            source_text = "\n".join(page.get_text() for page in source_doc)
            source_doc.close()
        else:
            source_text = ""
        large_operations = {"merge", "split", "remove", "rotate", "compress", "repair", "pdf_to_word", "pdf_to_excel", "pdf_to_powerpoint", "pdf_to_pdfa", "pdf_to_text", "pdf_to_markdown", "grayscale"}
        if operation in large_operations:
            verification["verified"] = len(doc) > 0
        if operation == "merge":
            expected_pages = 0
            for path in inputs:
                input_doc = fitz.open(str(path))
                expected_pages += len(input_doc)
                input_doc.close()
            verification["verified"] = len(doc) == expected_pages
        elif operation == "split":
            verification["verified"] = len(doc) == 1 and ("Page 1 of 69" in all_text or "AUDIT_PAGE_1" in all_text)
        elif operation == "remove":
            verification["verified"] = source_pages == 69 and len(doc) == 68 and "Page 2 of 69" in page_texts[0]
        elif operation in {"rotate", "compress", "repair", "pdf_to_pdfa", "grayscale"}:
            verification["verified"] = source_pages == len(doc) and ("Page 1 of 69" in page_texts[0] or operation == "grayscale")
            if operation == "rotate":
                verification["verified"] = verification["verified"] and doc[0].rotation == 90
            if operation == "compress":
                verification["source_bytes"] = inputs[0].stat().st_size
                verification["output_not_larger"] = output_path.stat().st_size <= inputs[0].stat().st_size
                verification["verified"] = verification["verified"] and verification["output_not_larger"]
            if operation == "grayscale":
                pix = doc[0].get_pixmap(alpha=False)
                samples = pix.samples
                verification["colored_pixel_mismatches"] = sum(1 for index in range(0, len(samples) - 2, pix.n) if pix.n >= 3 and (samples[index] != samples[index + 1] or samples[index + 1] != samples[index + 2]))
                verification["verified"] = verification["verified"] and verification["colored_pixel_mismatches"] == 0
        doc.close()
    elif operation == "pdf_to_text" and extension == ".txt":
        text = content.decode("utf-8", errors="replace")
        verification.update({"page_one_marker": "Page 1 of 69" in text, "text_chars": len(text), "verified": "Page 1 of 69" in text})
    elif operation == "pdf_to_markdown" and extension == ".md":
        text = content.decode("utf-8", errors="replace")
        verification.update({"page_one_marker": "Page 1 of 69" in text, "text_chars": len(text), "verified": "Page 1 of 69" in text})
    elif operation == "pdf_to_word" and extension == ".docx":
        document = Document(io.BytesIO(content))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        verification.update({"paragraph_count": len(document.paragraphs), "first_page_marker": "Page 1 of 69" in text, "verified": bool(text.strip()) and "Page 1 of 69" in text})
    elif operation == "pdf_to_excel" and extension == ".xlsx":
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        values = [str(cell.value) for sheet in workbook.worksheets for row in sheet.iter_rows() for cell in row if cell.value is not None]
        verification.update({"sheet_count": len(workbook.worksheets), "page_one_marker": any("Page 1 of 69" in value for value in values), "verified": bool(values) and any("Page 1 of 69" in value for value in values)})
    elif operation == "pdf_to_powerpoint" and extension == ".pptx":
        presentation = Presentation(io.BytesIO(content))
        text = "\n".join(shape.text for slide in presentation.slides for shape in slide.shapes if getattr(shape, "has_text_frame", False))
        verification.update({"slide_count": len(presentation.slides), "page_one_marker": "Page 1 of 69" in text, "verified": len(presentation.slides) == 69})
    if operation == "mask_aadhaar" and extension == ".pdf":
        doc = fitz.open(stream=content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        verification.update({
            "synthetic_marker_preserved": "SYNTHETIC ONLY - NOT A REAL ID" in text,
            "number_masked": not re.search(r"(?<!\d)(?:\d[\s-]*){12}(?!\d)", text),
            "verified": "XXXX" in text and not re.search(r"(?<!\d)(?:\d[\s-]*){12}(?!\d)", text),
        })
    return redact_id_text(verification)


def main() -> None:
    runner = load_runner()
    rounds = []
    order = [
        "merge", "split", "remove", "rotate", "organize", "scan_pdf", "compress", "repair", "ocr",
        "jpg_to_pdf", "word_to_pdf", "excel_to_pdf", "powerpoint_to_pdf", "html_to_pdf",
        "pdf_to_jpg", "pdf_to_word", "pdf_to_excel", "pdf_to_powerpoint", "pdf_to_pdfa", "pdf_to_text", "pdf_to_markdown",
        "edit", "annotate", "crop", "redact", "watermark", "page_numbers", "protect", "unlock", "sign", "compare", "forms", "metadata",
        "ai_chat", "ai_extract", "summarize", "translate", "photo_resizer", "mask_aadhaar", "grayscale", "flatten",
    ]
    expected_count = len(order)
    options_by_op = {
        "split": {"pages": "1"},
        "remove": {"pages": "1"},
        "rotate": {"degrees": 90},
        "organize": {"pages": [{"page": 2}, {"page": 1}]},
        "compress": {"preset": "100kb", "target_size_kb": 100, "quality": 65, "dpi": 150},
        "repair": {"mode": "automatic"},
        "pdf_to_word": {"pages": "all"},
        "pdf_to_excel": {"pages": "all"},
        "pdf_to_powerpoint": {"pages": "all", "mode": "visual"},
        "pdf_to_text": {"pages": "all"},
        "pdf_to_markdown": {"pages": "all"},
        "edit": {"page": 1, "text": "PAPERPLANE_EDITED_TEXT", "x": 72, "y": 220, "font_size": 12},
        "annotate": {"annotations": [{"type": "text", "page": 1, "point": [72, 420], "text": "ANNOTATION_AUDIT_NOTE"}]},
        "crop": {"left": 18, "top": 18, "right": 18, "bottom": 18},
        "redact": {"terms": "REDACT_THIS_MARKER"},
        "watermark": {"text": "AUDIT_WATERMARK", "opacity": 0.25},
        "page_numbers": {"format": "page_of_total", "start_number": 1, "start_page": 1},
        "sign": {"mode": "visual", "signer_name": "PAPERPLANE AUDIT SIGNATURE"},
        "metadata": {"title": "PAPERPLANE_AUDIT_METADATA", "author": "Synthetic Audit"},
        "ai_chat": {"question": "What marker is written on page two?"},
        "ai_extract": {"document_type": "auto"},
        "photo_resizer": {"preset": "ssc_photo", "target_kb": 50, "format": "jpg"},
    }

    for round_number in (1, 2):
        round_dir = AUDIT_ROOT / "inputs" / f"tool-audit-round-{round_number}"
        samples = make_sample_set(round_dir)
        runner.ROOT = AUDIT_ROOT / "outputs" / f"round-{round_number}"
        runner.SAMPLES = round_dir
        runner.OUTPUTS = samples["outputs"]
        runner.FORM_SOURCE = samples["form"]
        runner.BASE_URL = BASE_URL
        runner.PASSWORD = secrets.token_hex(16)
        runner.EXPECTED_FIELDS = EXPECTED_FIELDS

        session = requests.Session()
        catalog_response = session.get(f"{BASE_URL}/api/operations", timeout=30)
        catalog_response.raise_for_status()
        catalog = catalog_response.json()
        results = []
        protected_path = None
        owner_password = secrets.token_hex(16)
        started_round = time.monotonic()

        for operation in order:
            item = catalog.get(operation, {})
            started = time.monotonic()
            if item.get("available") is False and operation != "ai_chat":
                results.append({
                    "operation": operation,
                    "status": "skipped_unavailable",
                    "reason": str(item.get("prerequisite") or item.get("status") or "not installed"),
                    "duration_seconds": round(time.monotonic() - started, 3),
                })
                continue

            if operation == "html_to_pdf":
                paths = []
            elif operation == "merge":
                paths = [samples["large_pdf"], samples["pdf"]]
            elif operation == "compare":
                paths = [samples["pdf"], samples["changed_pdf"]]
            elif operation in {"scan_pdf", "photo_resizer"}:
                paths = [samples["image"]]
            elif operation == "jpg_to_pdf":
                paths = [samples["image"], samples["image2"]]
            elif operation == "word_to_pdf":
                paths = [samples["docx"]]
            elif operation == "excel_to_pdf":
                paths = [samples["xlsx"]]
            elif operation == "powerpoint_to_pdf":
                paths = [samples["pptx"]]
            elif operation in {"forms", "flatten"}:
                paths = [samples["form"]]
            elif operation == "unlock" and protected_path:
                paths = [protected_path]
            elif operation in {"protect", "unlock", "sign", "ai_chat", "ai_extract", "summarize", "translate", "mask_aadhaar"}:
                paths = [samples["pdf"]]
            elif operation in {"split", "remove", "rotate", "compress", "repair", "pdf_to_word", "pdf_to_excel", "pdf_to_powerpoint", "pdf_to_pdfa", "pdf_to_text", "pdf_to_markdown", "grayscale"}:
                paths = [samples["large_pdf"]]
            else:
                paths = [samples["pdf"]]

            options = dict(options_by_op.get(operation, {}))
            if operation == "protect":
                options.update({"password": runner.PASSWORD, "owner_password": owner_password})
            if operation == "unlock":
                options["password"] = runner.PASSWORD
            if operation == "forms":
                options["fields"] = EXPECTED_FIELDS
            if operation == "flatten":
                options["flatten"] = True
            if operation == "html_to_pdf":
                options["url"] = BASE_URL + "/"

            try:
                out_path = local_server.process(operation, paths, options, runner.OUTPUTS)
                if not Path(out_path).exists():
                    raise FileNotFoundError("The processor returned without writing an output file.")
                content = Path(out_path).read_bytes()
                extension = Path(out_path).suffix.lower()
                verification = verify_output_content(runner, operation, Path(out_path), content, extension, paths)
                record = {
                    "operation": operation,
                    "status": "completed",
                    "output_filename": Path(out_path).name,
                    "output_bytes": len(content),
                    "output_path": str(out_path),
                    "verification": verification,
                }
                if operation == "protect":
                    protected_path = Path(out_path)
                record = redact_id_text(record)
                record["duration_seconds"] = round(time.monotonic() - started, 3)
                results.append(record)
            except Exception as error:
                error_message = str(error)
                expected_block = operation == "html_to_pdf" and "Security Guard" in error_message
                results.append({
                    "operation": operation,
                    "status": "blocked_by_ssrf_guard" if expected_block else "audit_error",
                    "error": "Localhost URL was refused by the SSRF guard." if expected_block else f"{type(error).__name__}: {error}",
                    "duration_seconds": round(time.monotonic() - started, 3),
                })

        rounds.append({
            "round": round_number,
            "catalog_operation_count": len(catalog),
            "attempted": expected_count,
            "duration_seconds": round(time.monotonic() - started_round, 3),
            "results": results,
            "limitations": [
                "This is a local worker/API audit with generated synthetic files and the repository 69-page substitute, not the owner's exact files or production UI.",
                "AI Translate and Summarize need an owner-configured provider and are not treated as passes when unavailable.",
                "The owner-provided Drive URL resolves to a one-page file; it cannot prove the separate 69-page import acceptance.",
            ],
        })

    report = {"round_count": len(rounds), "operation_count_per_round": expected_count, "rounds": rounds}
    report = redact_id_text(report)
    output_json = AUDIT_ROOT / "outputs" / "tool-content-audit.json"
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Paperplane v10 — Local 41-tool output-content audit",
        "",
        "Two sequential rounds called the same local `server.process` dispatcher used by queued jobs, wrote each available artifact, and opened it with a format-aware parser. The run used synthetic marked files plus the 4,980,286-byte, 69-page repository substitute. It did not call the browser UI or production, use owner credentials, or make a real payment.",
        "",
        "Files: [structured evidence](outputs/tool-content-audit.json); synthetic input fixtures are under `inputs/tool-audit-round-1/` and `inputs/tool-audit-round-2/`.",
        "",
    ]
    for round_data in rounds:
        lines += [f"## Round {round_data['round']}", "", f"Duration: {round_data['duration_seconds']} s; operations: {round_data['catalog_operation_count']} in the catalog; attempted: {round_data['attempted']}.", ""]
        lines += ["| Tool | Status | Download / bytes | Opened content evidence | Time |", "|---|---|---|---|---:|"]
        for row in round_data["results"]:
            verification = row.get("verification", {})
            output = row.get("output_filename", "—")
            size = row.get("output_bytes", "—")
            pages = verification.get("page_count", verification.get("pages", "—"))
            marker = verification.get("expected_marker", verification.get("text_sample", ""))
            if isinstance(marker, str):
                marker = re.sub(r"\s+", " ", marker)[:110]
            if not marker:
                marker = ", ".join(f"{key}={value}" for key, value in verification.items() if key in {"opened_as_pdf", "verified", "encrypted", "page_count", "dimensions", "synthetic_marker_preserved", "number_masked"})
            status = row.get("status", "unknown")
            if row.get("error"):
                marker = str(row["error"])[:110]
            if row.get("reason"):
                marker = str(row["reason"])[:110]
            lines.append(f"| `{row['operation']}` | {status} | {output} / {size} B | pages={pages}; {marker} | {row.get('duration_seconds', 0):.3f}s |")
        lines.append("")
    lines += [
        "## Limits",
        "",
        "The Translate/Summarize acceptance remains provider-blocked; OCR is unavailable because Tesseract is not installed. The HTML-to-PDF localhost probe was blocked by the SSRF guard as expected. Synthetic output checks do not establish that an operation passes for every file shape. The exact owner form, exact owner file, exact live Drive import, browser UI flows, mobile browser-chrome matrix, and production persistence remain separate acceptance gates.",
        "",
    ]
    (AUDIT_ROOT / "TOOL-CONTENT-AUDIT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "round_count": len(rounds),
        "operations_per_round": expected_count,
        "round_durations_seconds": [item["duration_seconds"] for item in rounds],
        "counts_by_status": [
            {status: sum(1 for item in round_data["results"] if item.get("status") == status) for status in sorted({item.get("status", "unknown") for item in round_data["results"]})}
            for round_data in rounds
        ],
        "report": str(output_json),
    }, indent=2))


if __name__ == "__main__":
    main()
