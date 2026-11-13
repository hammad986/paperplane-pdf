from __future__ import annotations

import io
import json
import argparse
import re
import time
import zipfile
from pathlib import Path

import fitz
import openpyxl
import requests
from docx import Document
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "catalog-samples"
OUTPUTS = ROOT / "catalog-outputs"
BASE_URL = "http://127.0.0.1:8501"
PASSWORD = "paperplane-audit-test-password"
FORM_SOURCE = ROOT / "p2-fill-form-1366-after.pdf"
EXPECTED_FIELDS = {
    "ApplicantName": "Audit Applicant",
    "ContactEmail": "audit@example.test",
    "ProgramTitle": "Paperplane Output Audit",
    "Statement": "Synthetic form value for local output verification.",
}


def create_samples() -> dict[str, Path]:
    SAMPLES.mkdir(exist_ok=True)
    OUTPUTS.mkdir(exist_ok=True)
    base = SAMPLES / "audit-sample.pdf"
    changed = SAMPLES / "audit-sample-changed.pdf"
    if not base.exists():
        doc = fitz.open()
        for page_num in (1, 2):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 72), "PAPERPLANE_AUDIT_SAMPLE", fontsize=18)
            page.insert_text((72, 112), f"AUDIT_PAGE_{page_num}", fontsize=13)
            page.insert_text((72, 145), "Applicant: Synthetic Example Person", fontsize=11)
            page.insert_text((72, 170), "Document date: 2026-11-07", fontsize=11)
            page.insert_text((72, 195), "TEST_SECRET: REDACT_ME_NOW", fontsize=11)
            page.draw_rect(fitz.Rect(430, 70, 470, 110), color=(0.9, 0.1, 0.1), fill=(0.9, 0.1, 0.1))
            if page_num == 1:
                xs = (72, 220, 370, 520)
                ys = (350, 385, 420, 455)
                for x in xs:
                    page.draw_line((x, ys[0]), (x, ys[-1]), color=(0, 0, 0), width=0.8)
                for y in ys:
                    page.draw_line((xs[0], y), (xs[-1], y), color=(0, 0, 0), width=0.8)
                cells = [
                    ["Item", "Amount", "Status"],
                    ["Application", "19.00", "Paid"],
                    ["Processing", "49.00", "Pending"],
                ]
                for row_index, row in enumerate(cells):
                    for col_index, value in enumerate(row):
                        page.insert_text((xs[col_index] + 6, ys[row_index] + 23), value, fontsize=10)
            else:
                page.insert_text((72, 235), "AUDIT_SECOND_PAGE_ORIGINAL", fontsize=11)
                page.insert_text((72, 265), "Synthetic Aadhaar test: 1234 5678 9012", fontsize=11)
        doc.save(base, garbage=4, deflate=True)
        doc.close()

    if not changed.exists():
        doc = fitz.open(base)
        page = doc[1]
        page.add_redact_annot(fitz.Rect(72, 215, 280, 247), fill=(1, 1, 1))
        page.apply_redactions()
        page.insert_text((72, 235), "AUDIT_SECOND_PAGE_CHANGED_DELTA", fontsize=11)
        doc.save(changed, garbage=4, deflate=True)
        doc.close()

    image_path = SAMPLES / "audit-photo.png"
    image2_path = SAMPLES / "audit-photo-2.png"
    for path, heading, color in (
        (image_path, "PAPERPLANE IMAGE AUDIT", (240, 95, 50)),
        (image2_path, "SECOND IMAGE PAGE", (35, 135, 110)),
    ):
        if not path.exists():
            image = Image.new("RGB", (900, 1200), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((40, 40, 860, 1160), outline=color, width=8)
            draw.text((85, 130), heading, fill=(20, 30, 35))
            draw.text((85, 210), "Synthetic visual-only content for local testing.", fill=(20, 30, 35))
            for index in range(12):
                draw.line((85, 300 + index * 50, 780 - (index % 3) * 45, 300 + index * 50), fill=(100, 125, 135), width=2)
            draw.ellipse((580, 800, 760, 980), outline=color, width=9)
            image.save(path, "PNG", optimize=True)

    docx_path = SAMPLES / "audit-office.docx"
    if not docx_path.exists():
        docx_doc = Document()
        docx_doc.add_heading("PAPERPLANE_DOCX_AUDIT", level=1)
        docx_doc.add_paragraph("Synthetic office source for local converter verification.")
        docx_doc.add_paragraph("Expected text marker: AUDIT_OFFICE_WORD_OUTPUT.")
        docx_doc.save(docx_path)

    xlsx_path = SAMPLES / "audit-office.xlsx"
    if not xlsx_path.exists():
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

    pptx_path = SAMPLES / "audit-office.pptx"
    if not pptx_path.exists():
        presentation = Presentation()
        slide = presentation.slides.add_slide(presentation.slide_layouts[0])
        slide.shapes.title.text = "PAPERPLANE_PPTX_AUDIT"
        slide.placeholders[1].text = "AUDIT_OFFICE_POWERPOINT_OUTPUT"
        presentation.save(pptx_path)

    filled_form = FORM_SOURCE if FORM_SOURCE.exists() else base
    return {
        "pdf": base,
        "changed_pdf": changed,
        "image": image_path,
        "image2": image2_path,
        "docx": docx_path,
        "xlsx": xlsx_path,
        "pptx": pptx_path,
        "form": filled_form,
    }


def extension_from_headers(headers: requests.structures.CaseInsensitiveDict) -> str:
    disposition = headers.get("Content-Disposition", "")
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.I)
    name = match.group(1).strip().strip('"') if match else "output.pdf"
    return Path(name).suffix.lower() or ".bin"


def verify_output(operation: str, content: bytes, extension: str) -> dict[str, object]:
    result: dict[str, object] = {"extension": extension, "bytes": len(content), "verified": False}
    if not content:
        result["reason"] = "empty output"
        return result

    if content.startswith(b"%PDF-"):
        if operation == "protect":
            reader = PdfReader(io.BytesIO(content), strict=False)
            is_encrypted = reader.is_encrypted
            password_accepted = bool(reader.decrypt(PASSWORD)) if is_encrypted else False
            page_count = len(reader.pages) if password_accepted else 0
            result.update({"opened_as_pdf": True, "encrypted": is_encrypted, "password_accepted": password_accepted, "page_count": page_count, "verified": is_encrypted and password_accepted and page_count == 2})
            return result
        doc = fitz.open(stream=content, filetype="pdf")
        texts = [page.get_text() for page in doc]
        text = "\n".join(texts)
        result.update({"opened_as_pdf": True, "page_count": len(doc), "text_chars": len(text), "text_sample": text[:280]})
        if operation == "unlock":
            reader = PdfReader(io.BytesIO(content), strict=False)
            result.update({"encrypted": reader.is_encrypted, "verified": not reader.is_encrypted and len(doc) > 0})
        elif operation == "flatten":
            widgets = sum(len(list(page.widgets() or [])) for page in doc)
            result.update({"active_widgets": widgets, "verified": widgets == 0 and len(doc) > 0})
        elif operation == "forms":
            widget_values = {}
            for page in doc:
                for widget in page.widgets() or []:
                    widget_values[widget.field_name] = widget.field_value
            result.update({"widget_values": widget_values, "verified": all(widget_values.get(k) == v for k, v in EXPECTED_FIELDS.items())})
        elif operation == "metadata":
            reader = PdfReader(io.BytesIO(content), strict=False)
            metadata = {str(k): str(v) for k, v in (reader.metadata or {}).items()}
            result.update({"metadata": metadata, "verified": any("PAPERPLANE_AUDIT_METADATA" in value for value in metadata.values())})
        elif operation == "rotate":
            rotations = [int(page.rotation) for page in doc]
            result.update({"rotations": rotations, "verified": bool(rotations) and rotations[0] == 90})
        elif operation == "crop":
            sizes = [[round(page.rect.width, 2), round(page.rect.height, 2)] for page in doc]
            result.update({"page_sizes": sizes, "verified": bool(sizes) and sizes[0][0] < 595 and sizes[0][1] < 842})
        elif operation == "organize":
            result["verified"] = len(doc) == 2 and "AUDIT_PAGE_2" in texts[0]
        elif operation == "merge":
            result["verified"] = len(doc) == 4 and all(marker in text for marker in ("AUDIT_PAGE_1", "AUDIT_PAGE_2"))
        elif operation == "split":
            result["verified"] = len(doc) == 1 and "AUDIT_PAGE_1" in text
        elif operation == "remove":
            result["verified"] = len(doc) == 1 and "AUDIT_PAGE_2" in text and "AUDIT_PAGE_1" not in text
        elif operation in {"edit", "watermark", "page_numbers", "annotate"}:
            marker = {
                "edit": "PAPERPLANE_EDITED_TEXT",
                "watermark": "AUDIT_WATERMARK",
                "page_numbers": "Page 1 of 2",
                "annotate": "ANNOTATION_AUDIT_NOTE",
            }[operation]
            result.update({"expected_marker": marker, "verified": marker.casefold() in text.casefold()})
        elif operation == "redact":
            result.update({"redacted_term_remaining": "TEST_SECRET" in text, "verified": "TEST_SECRET" not in text})
        elif operation == "mask_aadhaar":
            result.update({"masked_prefix_present": "XXXX XXXX" in text, "original_prefix_present": "1234 5678" in text, "last_four_present": "9012" in text})
            result["verified"] = result["masked_prefix_present"] and not result["original_prefix_present"] and result["last_four_present"]
        elif operation == "pdf_to_pdfa":
            result.update({"archival_marker_present": "PDF/A-1b" in str(doc.metadata or {})})
            result["verified"] = len(doc) > 0 and result["archival_marker_present"]
        elif operation == "grayscale":
            pix = doc[0].get_pixmap(alpha=False)
            if pix.n >= 3:
                samples = pix.samples
                mismatches = sum(1 for index in range(0, len(samples) - 2, pix.n) if samples[index] != samples[index + 1] or samples[index + 1] != samples[index + 2])
            else:
                mismatches = 0
            result.update({"colored_pixel_mismatches": mismatches, "verified": len(doc) > 0 and mismatches == 0})
        elif operation == "scan_pdf":
            pix = doc[0].get_pixmap(alpha=False)
            result.update({"first_page_dimensions": [pix.width, pix.height], "verified": len(doc) == 1 and pix.width > 0 and pix.height > 0})
        elif operation in {"jpg_to_pdf"}:
            pix = doc[0].get_pixmap(alpha=False)
            result.update({"first_page_dimensions": [pix.width, pix.height], "verified": len(doc) == 2 and pix.width > 0 and pix.height > 0})
        elif operation == "repair":
            result["verified"] = len(doc) == 2 and "PAPERPLANE_AUDIT_SAMPLE" in text
        elif operation == "compress":
            result.update({"source_bytes": (SAMPLES / "audit-sample.pdf").stat().st_size, "verified": len(doc) == 2 and "PAPERPLANE_AUDIT_SAMPLE" in text})
        elif operation == "sign":
            result.update({"signer_marker_present": "PAPERPLANE AUDIT SIGNATURE" in text, "verified": len(doc) > 0 and "PAPERPLANE AUDIT SIGNATURE" in text})
        elif operation in {"word_to_pdf", "excel_to_pdf", "powerpoint_to_pdf", "html_to_pdf"}:
            compact_text = re.sub(r"\s+", "", text).casefold()
            expected = {
                "word_to_pdf": "AUDIT_OFFICE_WORD_OUTPUT",
                "excel_to_pdf": "AUDIT_OFFICE_EXCEL_OUTPUT",
                "powerpoint_to_pdf": "AUDIT_OFFICE_POWERPOINT_OUTPUT",
                "html_to_pdf": "exampledomain",
            }[operation].casefold()
            result.update({"expected_marker": expected, "verified": len(doc) > 0 and expected in compact_text})
        elif operation in {"pdf_to_word", "pdf_to_excel", "pdf_to_powerpoint", "pdf_to_jpg", "pdf_to_text", "pdf_to_markdown", "ai_extract"}:
            result["reason"] = "unexpected PDF output extension for this operation"
        else:
            result["verified"] = len(doc) > 0
        doc.close()
        return result

    if extension == ".zip":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
            result["archive_entries"] = names
            if operation == "pdf_to_jpg":
                images = [name for name in names if name.lower().endswith((".jpg", ".jpeg"))]
                valid_images = sum(1 for name in images if archive.read(name).startswith(b"\xff\xd8"))
                result.update({"image_entries": len(images), "valid_jpegs": valid_images, "verified": len(images) == 2 and valid_images == 2})
            elif operation == "split":
                pages = [name for name in names if name.lower().endswith(".pdf")]
                valid_pdfs = sum(1 for name in pages if archive.read(name).startswith(b"%PDF-"))
                result.update({"pdf_entries": len(pages), "valid_pdfs": valid_pdfs, "verified": len(pages) == 2 and valid_pdfs == 2})
            else:
                result["verified"] = len(names) > 0
        return result

    if extension == ".txt":
        text = content.decode("utf-8", errors="replace")
        result["text_sample"] = text[:600]
        if operation == "compare":
            result["verified"] = "AUDIT_SECOND_PAGE_CHANGED_DELTA" in text or "No text differences found." in text
        elif operation == "pdf_to_text":
            result["verified"] = "PAPERPLANE_AUDIT_SAMPLE" in text and "AUDIT_PAGE_1" in text
        else:
            result["verified"] = bool(text.strip())
        return result

    if extension == ".md":
        text = content.decode("utf-8", errors="replace")
        result.update({"text_sample": text[:600], "verified": "PAPERPLANE_AUDIT_SAMPLE" in text})
        return result

    if extension == ".json":
        parsed = json.loads(content.decode("utf-8"))
        result.update({"json_keys": list(parsed) if isinstance(parsed, dict) else [], "verified": isinstance(parsed, dict) and bool(parsed)})
        return result

    if extension == ".docx":
        document = Document(io.BytesIO(content))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        result.update({"paragraph_count": len(document.paragraphs), "text_sample": text[:600]})
        if operation == "pdf_to_word":
            result["verified"] = "PAPERPLANE_AUDIT_SAMPLE" in text
        else:
            result["verified"] = len(document.paragraphs) > 0
        return result

    if extension == ".xlsx":
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        values = [cell.value for sheet in workbook.worksheets for row in sheet.iter_rows() for cell in row if cell.value is not None]
        result.update({"sheet_count": len(workbook.worksheets), "cell_values": [str(value) for value in values[:20]]})
        if operation == "pdf_to_excel":
            result["verified"] = len(workbook.worksheets) > 0 and bool(values)
        else:
            result["verified"] = "AUDIT_OFFICE_EXCEL_OUTPUT" in [str(value) for value in values]
        return result

    if extension == ".pptx":
        presentation = Presentation(io.BytesIO(content))
        texts = [shape.text for slide in presentation.slides for shape in slide.shapes if getattr(shape, "has_text_frame", False)]
        text = "\n".join(texts)
        result.update({"slide_count": len(presentation.slides), "text_sample": text[:600]})
        if operation == "pdf_to_powerpoint":
            image_slides = []
            for slide in presentation.slides:
                picture_shapes = [shape for shape in slide.shapes if getattr(shape, "shape_type", None) == 13]
                valid_images = []
                for shape in picture_shapes:
                    image = Image.open(io.BytesIO(shape.image.blob))
                    valid_images.append(image.width >= 500 and image.height >= 500)
                image_slides.append(any(valid_images))
            result.update({"slides_with_full_page_images": sum(image_slides), "verified": len(presentation.slides) == 2 and all(image_slides)})
        else:
            result["verified"] = "AUDIT_OFFICE_POWERPOINT_OUTPUT" in text
        return result

    if extension in {".jpg", ".jpeg", ".png", ".webp"}:
        image = Image.open(io.BytesIO(content))
        result.update({"dimensions": list(image.size), "format": image.format, "verified": image.width > 0 and image.height > 0})
        if operation == "photo_resizer":
            result["verified"] = image.size == (350, 450) and 20 * 1024 <= len(content) <= 50 * 1024
        return result

    result["reason"] = "output format not covered by the verifier"
    return result


def run_job(session: requests.Session, operation: str, paths: list[Path], options: dict[str, object]) -> dict[str, object]:
    opened = []
    files = []
    try:
        for path in paths:
            handle = path.open("rb")
            opened.append(handle)
            mime = "application/pdf" if path.suffix.lower() == ".pdf" else "image/png" if path.suffix.lower() == ".png" else "application/octet-stream"
            files.append(("files", (path.name, handle, mime)))
        response = session.post(
            f"{BASE_URL}/api/jobs/create",
            data={"operation": operation, "options": json.dumps(options, ensure_ascii=False)},
            files=files if files else None,
            timeout=60,
        )
    finally:
        for handle in opened:
            handle.close()

    if response.status_code != 202:
        try:
            detail = response.json()
        except Exception:
            detail = response.text[:500]
        return {"operation": operation, "status": "rejected", "http_status": response.status_code, "detail": detail}

    created = response.json()
    status_url = BASE_URL + created["status_url"] if created["status_url"].startswith("/") else created["status_url"]
    deadline = time.monotonic() + 240
    job = {}
    while time.monotonic() < deadline:
        status_response = session.get(status_url, timeout=30)
        if status_response.status_code != 200:
            return {"operation": operation, "status": "status_error", "http_status": status_response.status_code, "detail": status_response.text[:500]}
        job = status_response.json()
        if job.get("status") in {"completed", "failed"}:
            break
        time.sleep(0.15)
    else:
        return {"operation": operation, "status": "timeout", "job": job}

    record: dict[str, object] = {"operation": operation, "status": job.get("status"), "elapsed_seconds": round(240 - max(0, deadline - time.monotonic()), 2)}
    if job.get("status") != "completed":
        record["error"] = job.get("error")
        return record

    download_url = BASE_URL + created["download_url"] if created["download_url"].startswith("/") else created["download_url"]
    output_response = session.get(download_url, timeout=60)
    if output_response.status_code != 200:
        record.update({"status": "download_failed", "http_status": output_response.status_code, "detail": output_response.text[:500]})
        return record

    extension = extension_from_headers(output_response.headers)
    destination = OUTPUTS / f"{operation}{extension}"
    destination.write_bytes(output_response.content)
    verification = verify_output(operation, output_response.content, extension)
    record.update({"output_filename": Path(output_response.headers.get("Content-Disposition", "filename=output").split("filename=")[-1].strip('"; ')).name, "output_bytes": len(output_response.content), "output_path": str(destination), "verification": verification})
    if operation == "protect" and verification.get("encrypted"):
        record["protected_source"] = str(destination)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise the local 41-tool catalog through upload, job, download, and output validation.")
    parser.add_argument("--only", help="Comma-separated operation IDs to re-run while preserving earlier result records")
    args = parser.parse_args()
    selected = {item.strip() for item in args.only.split(",") if item.strip()} if args.only else None
    samples = create_samples()
    session = requests.Session()
    operations_response = session.get(f"{BASE_URL}/api/operations", timeout=30)
    operations_response.raise_for_status()
    catalog = operations_response.json()
    unavailable = {name: {"status": item.get("status"), "reason": item.get("prerequisite")} for name, item in catalog.items() if item.get("available") is False}
    target = ROOT / "catalog-output-audit.json"
    previous = json.loads(target.read_text(encoding="utf-8")) if args.only and target.exists() else {}
    by_operation: dict[str, dict[str, object]] = {item["operation"]: item for item in previous.get("results", [])}

    base = samples["pdf"]
    order = [
        "merge", "split", "remove", "rotate", "organize", "scan_pdf", "compress", "repair", "ocr",
        "jpg_to_pdf", "word_to_pdf", "excel_to_pdf", "powerpoint_to_pdf", "html_to_pdf",
        "pdf_to_jpg", "pdf_to_word", "pdf_to_excel", "pdf_to_powerpoint", "pdf_to_pdfa", "pdf_to_text", "pdf_to_markdown",
        "edit", "annotate", "crop", "redact", "watermark", "page_numbers", "protect", "unlock", "sign", "compare", "forms", "metadata",
        "ai_chat", "ai_extract", "summarize", "translate", "photo_resizer", "mask_aadhaar", "grayscale", "flatten",
    ]
    options_by_op: dict[str, dict[str, object]] = {
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
        "redact": {"terms": "TEST_SECRET"},
        "watermark": {"text": "AUDIT_WATERMARK", "opacity": 0.25},
        "page_numbers": {"format": "page_of_total", "start_number": 1, "start_page": 1},
        "protect": {"password": PASSWORD, "owner_password": "paperplane-owner-test-password"},
        "unlock": {"password": PASSWORD},
        "sign": {"mode": "visual", "signer_name": "PAPERPLANE AUDIT SIGNATURE"},
        "metadata": {"title": "PAPERPLANE_AUDIT_METADATA", "author": "Synthetic Audit"},
        "ai_extract": {"document_type": "auto"},
        "photo_resizer": {"preset": "ssc_photo", "target_kb": 50, "format": "jpg"},
        "html_to_pdf": {"url": "https://example.com"},
    }

    for operation in order:
        if selected is not None and operation not in selected:
            continue
        item = catalog.get(operation, {})
        if item.get("available") is False:
            by_operation[operation] = {"operation": operation, "status": "skipped_unavailable", "reason": item.get("prerequisite") or item.get("status")}
            continue

        if operation == "html_to_pdf":
            paths: list[Path] = []
        elif operation in {"merge", "compare"}:
            paths = [samples["pdf"], samples["changed_pdf"]]
        elif operation in {"scan_pdf", "photo_resizer"}:
            paths = [samples["image"]]
        elif operation == "jpg_to_pdf":
            paths = [samples["image"], samples["image2"]]
        elif operation in {"word_to_pdf"}:
            paths = [samples["docx"]]
        elif operation == "excel_to_pdf":
            paths = [samples["xlsx"]]
        elif operation == "powerpoint_to_pdf":
            paths = [samples["pptx"]]
        elif operation in {"forms", "flatten"}:
            paths = [samples["form"]]
        elif operation == "unlock" and "protected_source" in by_operation.get("protect", {}):
            paths = [Path(str(by_operation["protect"]["protected_source"]))]
        else:
            paths = [base]

        options = dict(options_by_op.get(operation, {}))
        if operation == "forms":
            options["fields"] = EXPECTED_FIELDS
        if operation == "flatten":
            options["flatten"] = True
        try:
            by_operation[operation] = run_job(session, operation, paths, options)
        except Exception as error:
            by_operation[operation] = {"operation": operation, "status": "audit_error", "error": f"{type(error).__name__}: {error}"}

    results = [by_operation.get(name, {"operation": name, "status": "not_run"}) for name in order]
    wrong_password_check = previous.get("wrong_password_unlock", {"status": "not_run"})
    protected_source = by_operation.get("protect", {}).get("protected_source")
    if protected_source and (selected is None or "protect" in selected):
        wrong_password_check = run_job(session, "unlock", [Path(str(protected_source))], {"password": "deliberately-wrong-audit-password"})
        wrong_password_check["rejected_as_expected"] = wrong_password_check.get("status") == "failed"
    report = {
        "catalog_operation_count": len(catalog),
        "attempted": sum(item.get("status") not in {"skipped_unavailable"} for item in results),
        "skipped_unavailable": unavailable,
        "results": results,
        "wrong_password_unlock": wrong_password_check,
        "environment_limitations": {
            "AI provider workflows": "unavailable in local environment; not invoked",
            "OCR": "Tesseract dependency is not installed; tool advertises unavailable and was not invoked",
            "HTML to PDF": "uses public example.com as a minimal external smoke input",
        },
    }
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    compact = [{"operation": item["operation"], "status": item.get("status"), "verified": item.get("verification", {}).get("verified"), "error": item.get("error", item.get("detail"))} for item in results]
    print(json.dumps({"report": str(target), "catalog_operation_count": len(catalog), "attempted": report["attempted"], "results": compact}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
