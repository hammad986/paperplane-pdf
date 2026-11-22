"""Isolated worker entry point for bounded watermark and page-number jobs."""
from __future__ import annotations

import io
import re
from multiprocessing.connection import Connection
from pathlib import Path

import fitz
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import converters


def _overlay(width: float, height: float, text: str, kind: str, options: dict) -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(width, height))
    size = int(options.get("font_size", 11))
    font_path = converters.unicode_font_path(bold=kind == "watermark", text=text)
    font_name = "PaperplaneUnicodeBold" if kind == "watermark" else "PaperplaneUnicode"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font_name, font_path))
    render_size = size if kind != "watermark" else min(44, max(20, width / 12))
    pdf.setFont(font_name, render_size)
    mark_color = str(options.get("mark_color", "#243b53"))
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", mark_color):
        mark_color = "#243b53"
    red, green, blue = (int(mark_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    background = str(options.get("mark_background", "unknown")).lower()
    outline = (1, 1, 1) if background == "dark" else (0, 0, 0)

    if kind == "watermark":
        pdf.saveState()
        pdf.setFillAlpha(float(options.get("opacity", 0.18)))
        pdf.setFillColorRGB(red, green, blue)
        pdf.setStrokeColorRGB(*outline)
        pdf.setLineWidth(max(0.8, render_size / 18))
        pdf.translate(width / 2, height / 2)
        pdf.rotate(35)
        mark = pdf.beginText(-pdf.stringWidth(text, font_name, render_size) / 2, 0)
        mark.setTextRenderMode(2)
        mark.textOut(text)
        pdf.drawText(mark)
        pdf.restoreState()
    else:
        position = options.get("position", "Footer center")
        text_width = pdf.stringWidth(text, font_name, size)
        x = 28 if position.endswith("left") else width - text_width - 28 if position.endswith("right") else (width - text_width) / 2
        y = 24 if position.startswith("Footer") else height - 34
        pdf.setFillColorRGB(red, green, blue)
        pdf.setStrokeColorRGB(*outline)
        pdf.setLineWidth(max(0.8, size / 10))
        mark = pdf.beginText(x, y)
        mark.setTextRenderMode(2)
        mark.textOut(text)
        pdf.drawText(mark)

    pdf.save()
    return output.getvalue()


def _safe_int(value, default: int) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return int(value)
        value = str(value).strip().split()[0]
        return int(value)
    except (TypeError, ValueError):
        return default


def _run_job(source: Path, output: Path, operation: str, options: dict, image_path: Path | None) -> None:
    if operation == "watermark" and image_path is not None:
        converters.apply_image_watermark(
            source, output, image_path,
            opacity=float(options.get("opacity", 0.3)),
        )
        return

    label = str(options.get("text", "CONFIDENTIAL")).strip() if operation == "watermark" else ""
    if operation == "watermark" and not label:
        raise ValueError("Please provide watermark text or select an image.")
    format_pattern = str(options.get("format", "page_of_total")).lower()
    start_number = _safe_int(options.get("start_number"), 1)
    start_page = _safe_int(options.get("start_page"), 1)

    with fitz.open(str(source)) as document:
        total_pages = document.page_count
        for number, page in enumerate(document, 1):
            if operation == "watermark":
                text = label
            else:
                if number < start_page:
                    continue
                current = start_number + (number - start_page)
                if format_pattern in {"number_only", "number only", "{n}"}:
                    text = str(current)
                elif "{n}" in format_pattern or "{total}" in format_pattern:
                    text = re.sub(r"\{n\}", str(current), str(options.get("format", "")), flags=re.IGNORECASE)
                    text = re.sub(r"\{total\}", str(total_pages), text, flags=re.IGNORECASE)
                elif format_pattern == "page_n":
                    text = f"Page {current}"
                else:
                    text = f"Page {current} of {total_pages}"

            overlay_bytes = _overlay(float(page.rect.width), float(page.rect.height), text, operation, options)
            with fitz.open(stream=overlay_bytes, filetype="pdf") as overlay_document:
                page.show_pdf_page(page.rect, overlay_document, 0, overlay=True)
        document.save(str(output), garbage=4, deflate=True)


def run_watermark_job(
    result_pipe: Connection,
    source: str,
    output: str,
    operation: str,
    options: dict,
    image_path: str | None,
) -> None:
    """Run in a child process so the parent can terminate unresponsive native work."""
    try:
        _run_job(Path(source), Path(output), operation, options, Path(image_path) if image_path else None)
        result_pipe.send((True, None, None))
    except BaseException as error:
        try:
            result_pipe.send((False, type(error).__name__, str(error)))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        result_pipe.close()
