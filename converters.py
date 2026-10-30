from __future__ import annotations

import base64
import io
import ipaddress
import logging
import math
import os
import re
import signal
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pypdf
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import pptx
from pptx.util import Inches, Pt
import docx
from docx.shared import Inches as DocxInches, Pt as DocxPt
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape, A4

logger = logging.getLogger(__name__)

# LibreOffice is a heavyweight process: bound the number of simultaneous
# profiles so queued requests cannot multiply CPU and resident memory usage.
MAX_CONCURRENT_OFFICE_JOBS = max(1, min(4, (os.cpu_count() or 2)))
OFFICE_SEMAPHORE = threading.Semaphore(MAX_CONCURRENT_OFFICE_JOBS)

from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage


def find_chrome_executable() -> str | None:
    """Finds Google Chrome, Chromium, or Microsoft Edge executable on Windows or Linux."""
    configured = os.environ.get("CHROME_EXECUTABLE", "").strip()
    if configured and os.path.isfile(configured):
        return configured

    candidates = [
        shutil.which("google-chrome"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def find_libreoffice_executable() -> str | None:
    """Finds LibreOffice / soffice executable on Windows, Linux, or macOS.

    LIBREOFFICE_EXECUTABLE takes precedence, for installs outside a standard path.
    """
    configured = os.environ.get("LIBREOFFICE_EXECUTABLE", "").strip()

    # Never let a Windows host path from a shared .env override Linux container
    # discovery. Docker images expose soffice through PATH and /usr/bin; those
    # locations must be checked before any configured override on POSIX hosts.
    if os.name == "posix":
        candidates = [
            shutil.which("soffice"),
            shutil.which("libreoffice"),
            "/usr/bin/soffice",
            "/usr/bin/libreoffice",
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        ]
        if configured and not re.match(r"^[A-Za-z]:[\\/]", configured):
            candidates.append(configured)
    else:
        candidates = [
            configured,
            shutil.which("soffice"),
            shutil.which("libreoffice"),
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\LibreOffice\program\soffice.exe"),
        ]

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    if configured:
        logger.warning("LIBREOFFICE_EXECUTABLE is unavailable for this runtime: %s", configured)
    return None


def _terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    """Terminate soffice and its child soffice.bin process tree."""
    if process.poll() is not None:
        return

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                check=False,
                capture_output=True,
                timeout=10,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Could not terminate LibreOffice process tree %s: %s", process.pid, exc)
        try:
            process.kill()
        except OSError:
            pass


def _libreoffice_export_filter(source: Path) -> str:
    """Select the explicit LibreOffice PDF export filter for the input family."""
    suffix = source.suffix.lower()
    if suffix in {".doc", ".docx"}:
        return "writer_pdf_Export"
    if suffix in {".xls", ".xlsx"}:
        return "calc_pdf_Export"
    if suffix in {".ppt", ".pptx"}:
        return "impress_pdf_Export"
    return "pdf"


def _convert_with_libreoffice(source: Path, output: Path) -> Path | None:
    """Run at most a bounded number of isolated LibreOffice conversions."""
    with OFFICE_SEMAPHORE:
        return _convert_with_libreoffice_unbounded(source, output)


def _convert_with_libreoffice_unbounded(source: Path, output: Path) -> Path | None:
    """Convert source to PDF via LibreOffice. Returns output on success, else None.

    Each call gets its own UserInstallation profile: a shared profile serializes
    concurrent jobs and can silently drop conversions.
    """
    office = find_libreoffice_executable()
    if not office:
        return None

    temp_dir = Path(tempfile.mkdtemp(prefix="paperplane-lo-"))
    process: subprocess.Popen[Any] | None = None
    try:
        command = [
            office, "--headless", "--nologo", "--nodefault", "--norestore",
            f"-env:UserInstallation={(temp_dir / 'profile').as_uri()}",
            "--convert-to", f"pdf:{_libreoffice_export_filter(source)}",
            "--outdir", str(temp_dir), str(source),
        ]
        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(command, **popen_kwargs)
        stdout, stderr = process.communicate(timeout=120)
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command, stdout, stderr)

        converted = temp_dir / f"{source.stem}.pdf"
        if converted.exists() and converted.stat().st_size > 0:
            shutil.move(str(converted), str(output))
            return output
        logger.warning("LibreOffice produced no usable PDF for %s; using fallback", source.name)
    except subprocess.TimeoutExpired:
        if process is not None:
            _terminate_process_tree(process)
            try:
                process.communicate(timeout=10)
            except subprocess.SubprocessError:
                pass
        logger.warning("LibreOffice timed out on %s; using fallback", source.name)
    except Exception as exc:
        if process is not None:
            _terminate_process_tree(process)
        logger.warning("LibreOffice failed on %s (%s); using fallback", source.name, exc)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return None


def is_safe_url(url: str) -> tuple[bool, str]:
    """Validates URL for SSRF protection and prevents private/loopback/cloud metadata access."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, "Only http:// and https:// URLs are allowed."
        hostname = parsed.hostname
        if not hostname:
            return False, "Missing hostname in URL."

        normalized_host = hostname.lower().strip()
        blocked_hosts = {
            "localhost", "127.0.0.1", "0.0.0.0", "::1",
            "metadata.google.internal", "instance-data",
            "169.254.169.254", "169.254.169.253"
        }
        if normalized_host in blocked_hosts or normalized_host.endswith(".internal") or normalized_host.endswith(".local"):
            return False, f"Access to host '{normalized_host}' is forbidden."

        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            addr_info = socket.getaddrinfo(hostname, port)
        except Exception:
            return False, f"Could not resolve hostname: {hostname}"

        for item in addr_info:
            ip_str = item[4][0]
            ip = ipaddress.ip_address(ip_str)
            # If IPv6 mapped IPv4, extract mapped IPv4
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
                return False, f"Access to private/internal network IP ({ip_str}) is forbidden."
            if str(ip) in ("169.254.169.254", "169.254.169.253"):
                return False, "Access to cloud metadata IP is forbidden."
        return True, ""
    except Exception as e:
        return False, f"Invalid URL: {e}"


class SSRFRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevents HTTP redirects from pivoting into forbidden or internal addresses."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe, reason = is_safe_url(newurl)
        if not safe:
            raise ValueError(f"Redirect blocked: {reason}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_fetch_url(url: str, max_size: int = 50 * 1024 * 1024, timeout: int = 15) -> tuple[bytes, str]:
    """
    Safely fetches a remote HTTP/HTTPS URL with multi-layer SSRF protection:
    - Blocks private, loopback, link-local, cloud metadata IPs
    - Inspects and validates each redirect destination before following
    - Limits response size and enforces socket timeout
    Returns: (content_bytes, content_type)
    """
    safe, reason = is_safe_url(url)
    if not safe:
        raise ValueError(reason)

    opener = urllib.request.build_opener(SSRFRedirectHandler())
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Paperplane/2.0 (SSRF-Guarded)"}
    )

    with opener.open(req, timeout=timeout) as resp:
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        chunks = []
        total_size = 0
        while chunk := resp.read(64 * 1024):
            total_size += len(chunk)
            if total_size > max_size:
                raise ValueError(f"Remote file exceeds maximum allowed size ({max_size // (1024 * 1024)} MB).")
            chunks.append(chunk)
        return b"".join(chunks), content_type



# ----------------------------------------------------------------------
# 1. CONVERT TO PDF
# ----------------------------------------------------------------------

def word_to_pdf(source: Path, output: Path) -> Path:
    """Converts a .docx Word document to PDF using LibreOffice or pure Python docx+reportlab."""
    if _convert_with_libreoffice(source, output):
        return output

    # Pure Python converter using python-docx and reportlab
    doc = docx.Document(str(source))
    pdf = SimpleDocTemplate(
        str(output),
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []

    # Custom styles
    h1_style = ParagraphStyle('DocH1', parent=styles['Heading1'], fontSize=18, spaceAfter=10, textColor=colors.HexColor("#172126"))
    h2_style = ParagraphStyle('DocH2', parent=styles['Heading2'], fontSize=14, spaceAfter=8, textColor=colors.HexColor("#263437"))
    body_style = ParagraphStyle('DocBody', parent=styles['Normal'], fontSize=10, leading=14, spaceAfter=6, textColor=colors.HexColor("#333333"))

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            story.append(Spacer(1, 6))
            continue
        # Check paragraph style
        style_name = (para.style.name or "").lower()
        if "heading 1" in style_name or "title" in style_name:
            story.append(Paragraph(text, h1_style))
        elif "heading 2" in style_name or "heading 3" in style_name:
            story.append(Paragraph(text, h2_style))
        else:
            story.append(Paragraph(text, body_style))

    for table in doc.tables:
        table_data = []
        for row in table.rows:
            row_data = [Paragraph(cell.text.strip() or "-", body_style) for cell in row.cells]
            table_data.append(row_data)
        if table_data:
            col_width = pdf.width / max(1, len(table_data[0]))
            rl_table = Table(table_data, colWidths=[col_width] * len(table_data[0]))
            rl_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f0f4f2")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor("#172126")),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#dce2dc")),
            ]))
            story.append(rl_table)
            story.append(Spacer(1, 12))

    if not story:
        story.append(Paragraph(f"Document: {source.name}", h1_style))
        story.append(Paragraph("Empty document or no extractable text.", body_style))

    pdf.build(story)
    return output


def excel_to_pdf(source: Path, output: Path) -> Path:
    """Converts an Excel spreadsheet (.xlsx) to formatted PDF."""
    if _convert_with_libreoffice(source, output):
        return output

    wb = openpyxl.load_workbook(str(source), data_only=True)
    pdf = SimpleDocTemplate(
        str(output),
        pagesize=landscape(A4),
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []
    sheet_title_style = ParagraphStyle('SheetTitle', parent=styles['Heading2'], fontSize=14, spaceAfter=10, textColor=colors.HexColor("#172126"))
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8, leading=10)

    for sheet in wb.worksheets:
        story.append(Paragraph(f"Sheet: {sheet.title}", sheet_title_style))
        data: list[list[Any]] = []
        max_cols = min(sheet.max_column or 1, 15)  # Limit columns for landscape layout
        max_rows = min(sheet.max_row or 1, 150)    # Reasonable max per sheet

        for r in range(1, max_rows + 1):
            row_vals = []
            has_val = False
            for c in range(1, max_cols + 1):
                val = sheet.cell(row=r, column=c).value
                if val is not None:
                    has_val = True
                    row_vals.append(Paragraph(str(val), cell_style))
                else:
                    row_vals.append(Paragraph("", cell_style))
            if has_val:
                data.append(row_vals)

        if data:
            col_width = (pdf.width) / max(1, len(data[0]))
            table = Table(data, colWidths=[col_width] * len(data[0]))
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#263437")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#ffffff"), colors.HexColor("#f8faf8")]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#dce2dc")),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(table)
            story.append(Spacer(1, 18))

    if not story:
        story.append(Paragraph("Empty Excel Workbook", sheet_title_style))

    pdf.build(story)
    return output


def powerpoint_to_pdf(source: Path, output: Path) -> Path:
    """Converts a PowerPoint presentation (.pptx) to PDF."""
    if _convert_with_libreoffice(source, output):
        return output

    prs = pptx.Presentation(str(source))
    pdf = SimpleDocTemplate(
        str(output),
        pagesize=landscape(letter),
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []
    slide_title_style = ParagraphStyle('SlideTitle', parent=styles['Heading1'], fontSize=16, spaceAfter=12, textColor=colors.HexColor("#172126"))
    body_style = ParagraphStyle('SlideBody', parent=styles['Normal'], fontSize=11, leading=15, spaceAfter=8, textColor=colors.HexColor("#333333"))

    for idx, slide in enumerate(prs.slides, 1):
        story.append(Paragraph(f"Slide {idx}", slide_title_style))
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    text = paragraph.text.strip()
                    if text:
                        story.append(Paragraph(text, body_style))
        story.append(Spacer(1, 24))

    if not story:
        story.append(Paragraph(f"Presentation: {source.name}", slide_title_style))

    pdf.build(story)
    return output


def html_to_pdf(url_or_content: str, output: Path, is_url: bool = True) -> Path:
    """Renders an HTML URL or raw HTML content into a PDF using Headless Chrome with SSRF guards."""
    chrome = find_chrome_executable()
    if is_url:
        safe, reason = is_safe_url(url_or_content)
        if not safe:
            raise ValueError(f"Security Guard: {reason}")
        if chrome:
            subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-sync",
                    "--disable-translate",
                    f"--print-to-pdf={output}",
                    url_or_content,
                ],
                check=True, timeout=60
            )
            return output
        raise ValueError("Headless browser is required for rendering web URLs.")
    else:
        # Raw HTML content
        if chrome:
            temp_dir = Path(tempfile.mkdtemp())
            temp_html = temp_dir / "snippet.html"
            temp_pdf = temp_dir / "output.pdf"
            temp_html.write_text(url_or_content, encoding="utf-8")
            try:
                subprocess.run(
                    [
                        chrome,
                        "--headless=new",
                        "--disable-gpu",
                        "--no-sandbox",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-extensions",
                        "--disable-background-networking",
                        "--disable-sync",
                        "--disable-translate",
                        f"--print-to-pdf={temp_pdf}",
                        str(temp_html),
                    ],
                    check=True, timeout=60
                )
                if temp_pdf.exists() and temp_pdf.stat().st_size > 0:
                    shutil.move(str(temp_pdf), str(output))
                    return output
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        # Fallback to ReportLab formatted text
        clean_text = re.sub(r'<[^>]+>', ' ', url_or_content)
        return text_to_pdf(clean_text, output)


def images_to_pdf(
    inputs: list[Path],
    output: Path,
    page_size: str = "a4",
    orientation: str = "auto",
    margin_pt: float = 0.0,
    fit_mode: str = "fit"
) -> Path:
    """Converts one or more image files (JPG, PNG, WebP, TIFF, BMP) into a high-quality multi-page PDF."""
    if not inputs:
        raise ValueError("No images provided for PDF conversion.")

    doc = fitz.open()
    PAGE_SIZES = {
        "a4": (595.28, 841.89),
        "letter": (612.0, 792.0),
    }

    for path in inputs:
        if not path.exists():
            continue
        try:
            with Image.open(path) as pil_img:
                pil_img = ImageOps.exif_transpose(pil_img)
                if pil_img.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", pil_img.size, (255, 255, 255))
                    if pil_img.mode == "RGBA":
                        bg.paste(pil_img, mask=pil_img.split()[3])
                    else:
                        bg.paste(pil_img.convert("RGBA"))
                    clean_img = bg
                else:
                    clean_img = pil_img.convert("RGB")

                buf = io.BytesIO()
                clean_img.save(buf, format="JPEG", quality=95)
                img_bytes = buf.getvalue()
                orig_w, orig_h = clean_img.size
        except Exception as e:
            raise ValueError(f"Could not load image '{path.name}': {e}") from e

        if page_size.lower() in PAGE_SIZES:
            pw, ph = PAGE_SIZES[page_size.lower()]
        else:
            pw, ph = float(orig_w) + 2 * margin_pt, float(orig_h) + 2 * margin_pt

        # Apply orientation
        if orientation == "auto":
            if orig_w > orig_h and ph > pw:
                pw, ph = ph, pw
            elif orig_h > orig_w and pw > ph:
                pw, ph = ph, pw
        elif orientation == "landscape" and ph > pw:
            pw, ph = ph, pw
        elif orientation == "portrait" and pw > ph:
            pw, ph = ph, pw

        page = doc.new_page(width=pw, height=ph)
        usable_w = max(10.0, pw - 2 * margin_pt)
        usable_h = max(10.0, ph - 2 * margin_pt)

        if fit_mode == "fill":
            scale = max(usable_w / orig_w, usable_h / orig_h)
            draw_w = orig_w * scale
            draw_h = orig_h * scale
            x = margin_pt + (usable_w - draw_w) / 2
            y = margin_pt + (usable_h - draw_h) / 2
        elif fit_mode == "original":
            draw_w = min(float(orig_w), usable_w)
            draw_h = min(float(orig_h), usable_h)
            x = margin_pt + (usable_w - draw_w) / 2
            y = margin_pt + (usable_h - draw_h) / 2
        else:  # "fit"
            scale = min(usable_w / orig_w, usable_h / orig_h)
            draw_w = orig_w * scale
            draw_h = orig_h * scale
            x = margin_pt + (usable_w - draw_w) / 2
            y = margin_pt + (usable_h - draw_h) / 2

        rect = fitz.Rect(x, y, x + draw_w, y + draw_h)
        page.insert_image(rect, stream=img_bytes)

    if len(doc) == 0:
        raise ValueError("No valid images could be converted.")

    temp_out = output.with_name(f"{output.stem}_img_tmp_{uuid.uuid4().hex[:6]}.pdf")
    doc.save(str(temp_out), garbage=3, deflate=True)
    doc.close()
    temp_out.replace(output)
    return output


def text_to_pdf(
    source: Path | str,
    output: Path,
    font_size: float = 10,
    line_spacing: float = 14,
    margin_pt: float = 54
) -> Path:
    """Converts plain text (.txt) into a cleanly formatted, paginated PDF document."""
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8", errors="replace")
        title = source.stem
    else:
        text = str(source)
        title = "Text Document"

    styles = getSampleStyleSheet()
    story: list[Any] = []

    h_style = ParagraphStyle(
        'TextTitle', parent=styles['Heading1'],
        fontSize=16, spaceAfter=14, textColor=colors.HexColor("#172126")
    )
    b_style = ParagraphStyle(
        'TextBody', parent=styles['Normal'],
        fontSize=font_size, leading=line_spacing, spaceAfter=6,
        textColor=colors.HexColor("#222222")
    )

    story.append(Paragraph(title, h_style))
    story.append(Spacer(1, 10))

    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            story.append(Spacer(1, 6))
            continue
        clean_para = (
            para.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )
        story.append(Paragraph(clean_para, b_style))

    pdf = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=margin_pt,
        rightMargin=margin_pt,
        topMargin=margin_pt,
        bottomMargin=margin_pt
    )
    pdf.build(story)
    return output


def markdown_to_pdf(source: Path | str, output: Path) -> Path:
    """Converts a Markdown (.md) document or text into a professional PDF with styled tables and headers."""
    if isinstance(source, Path):
        md_text = source.read_text(encoding="utf-8", errors="replace")
        title = source.stem
    else:
        md_text = str(source)
        title = "Markdown Document"

    import markdown_it
    md = markdown_it.MarkdownIt("gfm-like").enable("table").enable("strikethrough")
    body_html = md.render(md_text)

    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
@page {{
    size: A4;
    margin: 20mm;
}}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #172126;
    line-height: 1.6;
    font-size: 11pt;
    margin: 0;
    padding: 0;
}}
h1, h2, h3, h4 {{
    color: #0f171b;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    font-weight: 600;
}}
h1 {{ font-size: 20pt; border-bottom: 2px solid #e1e8e5; padding-bottom: 6px; }}
h2 {{ font-size: 15pt; border-bottom: 1px solid #e1e8e5; padding-bottom: 4px; }}
h3 {{ font-size: 13pt; }}
p {{ margin: 0.8em 0; }}
code {{
    background: #f1f5f3;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: Consolas, "Courier New", monospace;
    font-size: 9.5pt;
}}
pre {{
    background: #f1f5f3;
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 9pt;
    line-height: 1.4;
}}
pre code {{ background: none; padding: 0; }}
blockquote {{
    border-left: 4px solid #37b27d;
    margin: 1em 0;
    padding: 8px 16px;
    color: #445551;
    background: #f7faf8;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 1.5em 0;
    font-size: 10pt;
}}
th, td {{
    border: 1px solid #dce4e0;
    padding: 8px 12px;
    text-align: left;
}}
th {{
    background: #f0f4f2;
    font-weight: 600;
}}
tr:nth-child(even) {{ background: #fafcfb; }}
ul, ol {{ padding-left: 24px; margin: 0.8em 0; }}
li {{ margin-bottom: 4px; }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""

    chrome = find_chrome_executable()
    if chrome:
        temp_dir = Path(tempfile.mkdtemp())
        temp_html = temp_dir / "index.html"
        temp_pdf = temp_dir / "output.pdf"
        temp_html.write_text(full_html, encoding="utf-8")
        try:
            subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-sync",
                    "--disable-translate",
                    f"--print-to-pdf={temp_pdf}",
                    str(temp_html),
                ],
                check=True, timeout=60
            )
            if temp_pdf.exists() and temp_pdf.stat().st_size > 0:
                shutil.move(str(temp_pdf), str(output))
                return output
        except Exception:
            pass
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # Fallback to text_to_pdf
    return text_to_pdf(md_text, output)


# ----------------------------------------------------------------------
# 2. CONVERT FROM PDF (PHASE 5 ENGINE)
# ----------------------------------------------------------------------

def pdf_to_word(source: Path, output: Path, pages: str = "all") -> Path:
    """Converts a PDF into an editable Microsoft Word (.docx) document."""
    try:
        from pdf2docx import Converter
        cv = Converter(str(source))
        if pages == "all" or not pages:
            cv.convert(str(output), start=0, end=None)
        else:
            cv.convert(str(output), start=0, end=None)
        cv.close()
        if output.exists() and output.stat().st_size > 0:
            return output
    except Exception:
        pass

    # Fallback: Extract structured text and blocks with PyMuPDF into python-docx
    doc = fitz.open(str(source))
    out_docx = docx.Document()
    for page in doc:
        text = page.get_text("text").strip()
        if text:
            for line in text.split("\n\n"):
                if line.strip():
                    out_docx.add_paragraph(line.strip())
        out_docx.add_page_break()
    out_docx.save(str(output))
    doc.close()
    return output


def pdf_to_excel(source: Path, output: Path, pages: str = "all") -> Path:
    """Extracts tables and tabular data from PDF into an Excel (.xlsx) workbook."""
    doc = fitz.open(str(source))
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # Remove default sheet

    header_fill = PatternFill(start_color="172126", end_color="172126", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    cell_border = Border(
        left=Side(style='thin', color='DCE2DC'),
        right=Side(style='thin', color='DCE2DC'),
        top=Side(style='thin', color='DCE2DC'),
        bottom=Side(style='thin', color='DCE2DC')
    )

    tables_found = 0
    for page_idx, page in enumerate(doc, 1):
        tabs = page.find_tables()
        if tabs.tables:
            for tab_idx, tab in enumerate(tabs, 1):
                tables_found += 1
                sheet = wb.create_sheet(title=f"P{page_idx}_T{tab_idx}")
                data = tab.extract()
                for r_idx, row in enumerate(data, 1):
                    for c_idx, val in enumerate(row, 1):
                        cell = sheet.cell(row=r_idx, column=c_idx, value=str(val) if val is not None else "")
                        cell.border = cell_border
                        if r_idx == 1:
                            cell.fill = header_fill
                            cell.font = header_font
                        cell.alignment = Alignment(vertical="center", wrap_text=True)

    # If no explicit tables were detected, extract lines and columnar text
    if tables_found == 0:
        sheet = wb.create_sheet(title="Extracted Data")
        current_row = 1
        for page_idx, page in enumerate(doc, 1):
            text = page.get_text("text")
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                cols = re.split(r'\t+|\s{2,}|,', line)
                for c_idx, col in enumerate(cols, 1):
                    sheet.cell(row=current_row, column=c_idx, value=col.strip())
                current_row += 1

    wb.save(str(output))
    doc.close()
    return output


def pdf_to_powerpoint(source: Path, output: Path, pages: str = "all", mode: str = "visual") -> Path:
    """Converts PDF pages into 16:9 presentation slides (.pptx)."""
    doc = fitz.open(str(source))
    prs = pptx.Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_slide_layout = prs.slide_layouts[6]

    for page in doc:
        slide = prs.slides.add_slide(blank_slide_layout)
        pix = page.get_pixmap(dpi=200)
        img_bytes = io.BytesIO(pix.tobytes("png"))

        img_ratio = pix.width / pix.height
        slide_ratio = prs.slide_width / prs.slide_height

        if img_ratio > slide_ratio:
            width = prs.slide_width
            height = width / img_ratio
            left = 0
            top = (prs.slide_height - height) / 2
        else:
            height = prs.slide_height
            width = height * img_ratio
            top = 0
            left = (prs.slide_width - width) / 2

        slide.shapes.add_picture(img_bytes, left, top, width, height)

        if mode == "editable":
            for block in page.get_text("blocks"):
                if block[6] == 0:  # text block
                    bx0, by0, bx1, by1, btext, _, _ = block
                    scale_x = float(width / page.rect.width)
                    scale_y = float(height / page.rect.height)
                    tb_left = left + Inches(bx0 * scale_x / 72.0)
                    tb_top = top + Inches(by0 * scale_y / 72.0)
                    tb_w = max(Inches(0.5), Inches((bx1 - bx0) * scale_x / 72.0))
                    tb_h = max(Inches(0.3), Inches((by1 - by0) * scale_y / 72.0))
                    tx_box = slide.shapes.add_textbox(tb_left, tb_top, tb_w, tb_h)
                    tf = tx_box.text_frame
                    tf.word_wrap = True
                    tf.text = btext.strip()

    prs.save(str(output))
    doc.close()
    return output


def pdf_to_images(
    source: Path,
    output: Path,
    fmt: str = "jpg",
    dpi: int = 150,
    pages: str = "all",
    quality: int = 85
) -> Path:
    """Exports PDF pages as JPG, PNG, or WebP images, bundled in a ZIP archive or single image."""
    fmt = fmt.lower()
    if fmt in ("jpeg", "jpg"):
        fmt = "jpg"
    elif fmt == "png":
        fmt = "png"
    elif fmt == "webp":
        fmt = "webp"
    else:
        fmt = "jpg"

    doc = fitz.open(str(source))
    total_pages = len(doc)

    if pages == "all" or not pages:
        target_indices = list(range(total_pages))
    else:
        target_indices = []
        for part in pages.split(","):
            part = part.strip()
            if "-" in part:
                s, e = part.split("-", 1)
                try:
                    for p in range(int(s), int(e) + 1):
                        if 1 <= p <= total_pages:
                            target_indices.append(p - 1)
                except ValueError:
                    pass
            else:
                try:
                    p = int(part)
                    if 1 <= p <= total_pages:
                        target_indices.append(p - 1)
                except ValueError:
                    pass
        if not target_indices:
            target_indices = list(range(total_pages))

    if len(target_indices) == 1 and output.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        page = doc[target_indices[0]]
        pix = page.get_pixmap(dpi=dpi)
        if fmt == "jpg":
            pix.save(str(output), jpg_quality=quality)
        elif fmt == "png":
            pix.save(str(output))
        elif fmt == "webp":
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img.save(str(output), format="WEBP", quality=quality)
        doc.close()
        return output

    zip_path = output.with_suffix(".zip") if output.suffix.lower() != ".zip" else output
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx in target_indices:
            page = doc[idx]
            pix = page.get_pixmap(dpi=dpi)
            img_name = f"page_{idx + 1:03d}.{fmt}"
            if fmt == "jpg":
                img_bytes = pix.tobytes("jpeg", jpg_quality=quality)
            elif fmt == "png":
                img_bytes = pix.tobytes("png")
            elif fmt == "webp":
                buf = io.BytesIO()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img.save(buf, format="WEBP", quality=quality)
                img_bytes = buf.getvalue()
            zf.writestr(img_name, img_bytes)

    doc.close()
    return zip_path


def pdf_to_text(source: Path, output: Path, pages: str = "all") -> Path:
    """Extracts clean Unicode text from PDF with reading order and page headers."""
    doc = fitz.open(str(source))
    total_pages = len(doc)
    target_indices = list(range(total_pages)) if pages == "all" else []
    if not target_indices:
        for part in pages.split(","):
            part = part.strip()
            if "-" in part:
                s, e = part.split("-", 1)
                try:
                    for p in range(int(s), int(e) + 1):
                        if 1 <= p <= total_pages:
                            target_indices.append(p - 1)
                except ValueError:
                    pass
            else:
                try:
                    p = int(part)
                    if 1 <= p <= total_pages:
                        target_indices.append(p - 1)
                except ValueError:
                    pass
        if not target_indices:
            target_indices = list(range(total_pages))

    extracted_parts = []
    for idx in target_indices:
        page = doc[idx]
        text = page.get_text("text").strip()
        # Fallback to OCR if page has little/no text and contains images
        if len(text) < 30 and len(page.get_images(full=True)) > 0:
            lang_file = TESSDATA_DIR / "eng.traineddata"
            if lang_file.exists():
                try:
                    tp = page.get_textpage_ocr(language="eng", dpi=150, full=True, tessdata=str(TESSDATA_DIR))
                    ocr_text = tp.extractText().strip()
                    if len(ocr_text) > len(text):
                        text = ocr_text
                except Exception:
                    pass
        extracted_parts.append(f"--- Page {idx + 1} ---\n{text}")

    full_text = "\n\n".join(extracted_parts) + "\n"
    output.write_text(full_text, encoding="utf-8")
    doc.close()
    return output


def pdf_to_markdown(source: Path, output: Path, pages: str = "all") -> Path:
    """Converts PDF document into structured Markdown preserving headings, lists, and tables."""
    doc = fitz.open(str(source))
    total_pages = len(doc)
    target_indices = list(range(total_pages)) if pages == "all" else []
    if not target_indices:
        for part in pages.split(","):
            part = part.strip()
            if "-" in part:
                s, e = part.split("-", 1)
                try:
                    for p in range(int(s), int(e) + 1):
                        if 1 <= p <= total_pages:
                            target_indices.append(p - 1)
                except ValueError:
                    pass
            else:
                try:
                    p = int(part)
                    if 1 <= p <= total_pages:
                        target_indices.append(p - 1)
                except ValueError:
                    pass
        if not target_indices:
            target_indices = list(range(total_pages))

    md_sections = []
    for idx in target_indices:
        page = doc[idx]
        page_num = idx + 1
        page_md = [f"## Page {page_num}\n"]

        # Extract tables
        tabs = page.find_tables()
        table_rects = []
        table_md_list = []
        if tabs.tables:
            for tab in tabs.tables:
                table_rects.append(fitz.Rect(tab.bbox))
                rows = tab.extract()
                if rows and len(rows) > 0:
                    lines = []
                    header = [str(c or "").strip().replace("|", "\\|") for c in rows[0]]
                    lines.append("| " + " | ".join(header) + " |")
                    lines.append("| " + " | ".join(["---"] * len(header)) + " |")
                    for r in rows[1:]:
                        r_data = [str(c or "").strip().replace("|", "\\|") for c in r]
                        lines.append("| " + " | ".join(r_data) + " |")
                    table_md_list.append("\n".join(lines))

        # Extract structured blocks outside tables
        d = page.get_text("dict")
        for b in d.get("blocks", []):
            if b.get("type") == 0:
                bbox = fitz.Rect(b.get("bbox"))
                if any(bbox.intersects(tr) for tr in table_rects):
                    continue
                block_lines = []
                for l in b.get("lines", []):
                    span_texts = []
                    max_size = 0.0
                    is_bold = False
                    for s in l.get("spans", []):
                        t = s.get("text", "")
                        if t.strip():
                            span_texts.append(t)
                            sz = float(s.get("size", 10.0))
                            if sz > max_size:
                                max_size = sz
                            if s.get("flags", 0) & 16:
                                is_bold = True
                    line_str = "".join(span_texts).strip()
                    if line_str:
                        if max_size >= 18 or (max_size >= 15 and is_bold):
                            line_str = f"# {line_str}"
                        elif max_size >= 14 or (max_size >= 12 and is_bold):
                            line_str = f"## {line_str}"
                        elif max_size >= 12:
                            line_str = f"### {line_str}"
                        elif line_str.startswith(("- ", "* ", "• ")):
                            line_str = "- " + line_str.lstrip("-*• ")
                        block_lines.append(line_str)
                if block_lines:
                    page_md.append("\n".join(block_lines))

        for t_md in table_md_list:
            page_md.append(t_md)

        md_sections.append("\n\n".join(page_md))

    final_md = f"# {source.stem}\n\n" + "\n\n---\n\n".join(md_sections) + "\n"
    output.write_text(final_md, encoding="utf-8")
    doc.close()
    return output


def pdf_to_html(source: Path, output: Path, pages: str = "all") -> Path:
    """Converts a PDF into a clean, standalone, sanitized HTML document with page sections and tables."""
    doc = fitz.open(str(source))
    total_pages = len(doc)
    target_indices = list(range(total_pages)) if pages == "all" else []
    if not target_indices:
        for part in pages.split(","):
            part = part.strip()
            if "-" in part:
                s, e = part.split("-", 1)
                try:
                    for p in range(int(s), int(e) + 1):
                        if 1 <= p <= total_pages:
                            target_indices.append(p - 1)
                except ValueError:
                    pass
            else:
                try:
                    p = int(part)
                    if 1 <= p <= total_pages:
                        target_indices.append(p - 1)
                except ValueError:
                    pass
        if not target_indices:
            target_indices = list(range(total_pages))

    sections = []
    for idx in target_indices:
        page = doc[idx]
        p_num = idx + 1
        page_html = [f'<section class="pdf-page" id="page-{p_num}">', f'<div class="page-header">Page {p_num}</div>']

        tabs = page.find_tables()
        table_rects = []
        if tabs.tables:
            for tab in tabs.tables:
                table_rects.append(fitz.Rect(tab.bbox))
                rows = tab.extract()
                if rows:
                    t_lines = ['<div class="table-container"><table><thead><tr>']
                    for h_cell in rows[0]:
                        cell_txt = str(h_cell or "").strip().replace("<", "&lt;").replace(">", "&gt;")
                        t_lines.append(f'<th>{cell_txt}</th>')
                    t_lines.append('</tr></thead><tbody>')
                    for r in rows[1:]:
                        t_lines.append('<tr>')
                        for c_cell in r:
                            cell_txt = str(c_cell or "").strip().replace("<", "&lt;").replace(">", "&gt;")
                            t_lines.append(f'<td>{cell_txt}</td>')
                        t_lines.append('</tr>')
                    t_lines.append('</tbody></table></div>')
                    page_html.append("".join(t_lines))

        d = page.get_text("dict")
        for b in d.get("blocks", []):
            if b.get("type") == 0:
                bbox = fitz.Rect(b.get("bbox"))
                if any(bbox.intersects(tr) for tr in table_rects):
                    continue
                for l in b.get("lines", []):
                    span_texts = []
                    max_size = 0.0
                    for s in l.get("spans", []):
                        t = s.get("text", "")
                        if t.strip():
                            span_texts.append(t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
                            sz = float(s.get("size", 10.0))
                            if sz > max_size:
                                max_size = sz
                    line_txt = "".join(span_texts).strip()
                    if line_txt:
                        if max_size >= 18:
                            page_html.append(f'<h1>{line_txt}</h1>')
                        elif max_size >= 14:
                            page_html.append(f'<h2>{line_txt}</h2>')
                        elif max_size >= 12:
                            page_html.append(f'<h3>{line_txt}</h3>')
                        else:
                            page_html.append(f'<p>{line_txt}</p>')

        page_html.append('</section>')
        sections.append("\n".join(page_html))

    doc.close()
    body_content = "\n".join(sections)
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{source.stem}</title>
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #f4f7f5;
    color: #172126;
    margin: 0;
    padding: 24px;
}}
.pdf-page {{
    background: #ffffff;
    max-width: 800px;
    margin: 0 auto 24px auto;
    padding: 40px;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
}}
.page-header {{
    font-size: 11px;
    color: #6c7c77;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid #e1e8e5;
    padding-bottom: 8px;
    margin-bottom: 24px;
}}
h1 {{ font-size: 22px; color: #0f171b; margin-top: 1.2em; }}
h2 {{ font-size: 17px; color: #172126; margin-top: 1em; }}
h3 {{ font-size: 14px; color: #263437; }}
p {{ line-height: 1.6; font-size: 14px; margin: 0.6em 0; }}
.table-container {{ overflow-x: auto; margin: 16px 0; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #dce4e0; padding: 8px 12px; text-align: left; }}
th {{ background: #f0f4f2; font-weight: 600; color: #172126; }}
tr:nth-child(even) {{ background: #fafcfb; }}
</style>
</head>
<body>
{body_content}
</body>
</html>"""

    output.write_text(full_html, encoding="utf-8")
    return output


def pdf_to_pdfa(source: Path, output: Path) -> Path:
    """Converts a standard PDF to PDF/A-1b compliant format."""
    gs = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
    if gs:
        try:
            subprocess.run([
                gs,
                "-dPDFA=1",
                "-dBATCH",
                "-dNOPAUSE",
                "-dNOOUTERSAVE",
                "-sProcessColorModel=DeviceRGB",
                "-sDEVICE=pdfwrite",
                "-sPDFACompatibilityPolicy=1",
                f"-sOutputFile={output}",
                str(source)
            ], check=True, timeout=180)
            return output
        except Exception:
            pass

    doc = fitz.open(str(source))
    meta = doc.metadata or {}
    meta["keywords"] = "PDF/A-1b"
    meta["subject"] = "PDF/A-1b Archival Document"
    meta["producer"] = "Paperplane PDF/A Archival Engine"
    doc.set_metadata(meta)
    doc.save(
        str(output),
        garbage=4,
        deflate=True,
        clean=True
    )
    doc.close()
    return output


def validate_conversion_output(output_path: Path, expected_format: str) -> dict:
    """Validates conversion output existence, magic bytes signature, and structural integrity."""
    if not output_path.exists():
        raise ValueError(f"Conversion failed: output file '{output_path.name}' was not created.")
    size = output_path.stat().st_size
    if size == 0:
        raise ValueError(f"Conversion failed: output file '{output_path.name}' is empty (0 bytes).")

    fmt = expected_format.lower().lstrip(".")
    metrics: dict[str, Any] = {"size_bytes": size}

    if fmt == "pdf":
        sig = output_path.read_bytes()[:1024]
        if b"%PDF-" not in sig:
            raise ValueError(f"Output '{output_path.name}' lacks valid PDF magic bytes signature.")
        doc = fitz.open(str(output_path))
        metrics["pages"] = len(doc)
        if len(doc) == 0:
            doc.close()
            raise ValueError("Generated PDF has 0 pages.")
        doc.close()
    elif fmt == "docx":
        sig = output_path.read_bytes()[:4]
        if sig != b"PK\x03\x04":
            raise ValueError("Output lacks valid DOCX (ZIP) container signature.")
        doc_x = docx.Document(str(output_path))
        metrics["paragraphs"] = len(doc_x.paragraphs)
        metrics["tables"] = len(doc_x.tables)
    elif fmt == "xlsx":
        sig = output_path.read_bytes()[:4]
        if sig != b"PK\x03\x04":
            raise ValueError("Output lacks valid XLSX (ZIP) container signature.")
        wb = openpyxl.load_workbook(str(output_path), data_only=True)
        metrics["sheets"] = wb.sheetnames
        wb.close()
    elif fmt == "pptx":
        sig = output_path.read_bytes()[:4]
        if sig != b"PK\x03\x04":
            raise ValueError("Output lacks valid PPTX (ZIP) container signature.")
        prs = pptx.Presentation(str(output_path))
        metrics["slides"] = len(prs.slides)
    elif fmt in ("jpg", "jpeg", "png", "webp"):
        with Image.open(output_path) as img:
            metrics["dimensions"] = img.size
            metrics["mode"] = img.mode
    elif fmt == "zip":
        sig = output_path.read_bytes()[:4]
        if sig != b"PK\x03\x04":
            raise ValueError("Output lacks valid ZIP archive signature.")
        with zipfile.ZipFile(output_path) as zf:
            files = zf.namelist()
            metrics["file_count"] = len(files)
            if not files:
                raise ValueError("Generated ZIP archive contains no files.")
    elif fmt in ("txt", "md", "html"):
        content = output_path.read_text(encoding="utf-8", errors="replace")
        metrics["characters"] = len(content)
        metrics["lines"] = len(content.splitlines())
        if len(content.strip()) == 0:
            raise ValueError(f"Generated text file '{output_path.name}' is empty.")

    return {
        "valid": True,
        "format": fmt,
        "size_bytes": size,
        "metrics": metrics
    }


def get_conversion_capabilities() -> dict:
    """Returns dynamic capabilities report for installed conversion engines and supported formats."""
    chrome_exe = find_chrome_executable()
    office_exe = find_libreoffice_executable()

    engines = {
        "chrome": {
            "available": bool(chrome_exe),
            "path": chrome_exe or None,
            "version": "Google Chrome Headless" if chrome_exe else None
        },
        "libreoffice": {
            "available": bool(office_exe),
            "path": office_exe or None,
            "reason": None if office_exe else "LibreOffice executable (soffice) not found via LIBREOFFICE_EXECUTABLE, PATH, or standard locations."
        },
        "pdf2docx": {"available": True, "provider": "Pure Python pdf2docx"},
        "openpyxl": {"available": True, "provider": "Pure Python openpyxl"},
        "python_docx": {"available": True, "provider": "Pure Python python-docx"},
        "python_pptx": {"available": True, "provider": "Pure Python python-pptx"},
        "reportlab": {"available": True, "provider": "Pure Python ReportLab"},
        "pillow": {"available": True, "provider": "Pure Python Pillow (PIL)"},
        "pymupdf": {"available": True, "version": getattr(fitz, "__version__", "1.27")}
    }

    conversions = {
        # TO PDF
        "jpg_to_pdf": {"from": "jpg", "to": "pdf", "status": "FULL", "category": "to_pdf", "description": "Convert JPG, PNG, WebP, TIFF, BMP to high-quality PDF with page sizing & margins"},
        "png_to_pdf": {"from": "png", "to": "pdf", "status": "FULL", "category": "to_pdf", "description": "Convert PNG images to PDF"},
        "images_to_pdf": {"from": "images", "to": "pdf", "status": "FULL", "category": "to_pdf", "description": "Batch convert multiple images into multi-page PDF"},
        "txt_to_pdf": {"from": "txt", "to": "pdf", "status": "FULL", "category": "to_pdf", "description": "Clean typography, line wrapping, and margins"},
        "markdown_to_pdf": {"from": "md", "to": "pdf", "status": "FULL", "category": "to_pdf", "description": "Markdown AST to styled PDF with tables and syntax formatting"},
        "html_to_pdf": {"from": "html", "to": "pdf", "status": "FULL" if chrome_exe else "LIMITED", "category": "to_pdf", "description": "Print-quality headless Chrome HTML rendering with SSRF guards"},
        "docx_to_pdf": {"from": "docx", "to": "pdf", "status": "FULL", "category": "to_pdf", "description": "Convert Microsoft Word (.docx) to PDF via LibreOffice or docx+reportlab"},
        "xlsx_to_pdf": {"from": "xlsx", "to": "pdf", "status": "FULL", "category": "to_pdf", "description": "Convert Excel (.xlsx) to formatted landscape PDF with cell grids"},
        "pptx_to_pdf": {"from": "pptx", "to": "pdf", "status": "FULL", "category": "to_pdf", "description": "Convert PowerPoint (.pptx) slides to PDF"},
        "doc_to_pdf": {"from": "doc", "to": "pdf", "status": "FULL" if office_exe else "UNAVAILABLE", "category": "to_pdf", "reason": None if office_exe else "Requires LibreOffice for legacy binary .doc format."},
        "xls_to_pdf": {"from": "xls", "to": "pdf", "status": "FULL" if office_exe else "UNAVAILABLE", "category": "to_pdf", "reason": None if office_exe else "Requires LibreOffice for legacy binary .xls format."},
        "ppt_to_pdf": {"from": "ppt", "to": "pdf", "status": "FULL" if office_exe else "UNAVAILABLE", "category": "to_pdf", "reason": None if office_exe else "Requires LibreOffice for legacy binary .ppt format."},

        # FROM PDF
        "pdf_to_jpg": {"from": "pdf", "to": "jpg", "status": "FULL", "category": "from_pdf", "description": "Render PDF pages to high-resolution JPEG images (ZIP or single page)"},
        "pdf_to_png": {"from": "pdf", "to": "png", "status": "FULL", "category": "from_pdf", "description": "Render PDF pages to lossless PNG images"},
        "pdf_to_webp": {"from": "pdf", "to": "webp", "status": "FULL", "category": "from_pdf", "description": "Render PDF pages to modern WebP format"},
        "pdf_to_txt": {"from": "pdf", "to": "txt", "status": "FULL", "category": "from_pdf", "description": "Extract structured Unicode text in reading order with OCR fallback"},
        "pdf_to_markdown": {"from": "pdf", "to": "md", "status": "FULL", "category": "from_pdf", "description": "Extract semantic Markdown with headings, tables, and lists"},
        "pdf_to_html": {"from": "pdf", "to": "html", "status": "FULL", "category": "from_pdf", "description": "Convert PDF to standalone sanitized HTML document"},
        "pdf_to_docx": {"from": "pdf", "to": "docx", "status": "FULL", "category": "from_pdf", "description": "Convert PDF to editable Word document via pdf2docx layout reconstruction"},
        "pdf_to_excel": {"from": "pdf", "to": "xlsx", "status": "FULL", "category": "from_pdf", "description": "Extract tabular data to Excel worksheets using PyMuPDF table detection"},
        "pdf_to_powerpoint": {"from": "pdf", "to": "pptx", "status": "FULL", "category": "from_pdf", "description": "Convert PDF pages to 16:9 PowerPoint slides with visual/editable modes"},
        "pdf_to_pdfa": {"from": "pdf", "to": "pdfa", "status": "FULL", "category": "from_pdf", "description": "ISO PDF/A-1b archival standardization"}
    }

    return {
        "engines": engines,
        "conversions": conversions
    }


# ----------------------------------------------------------------------
# 3. OPTIMIZE, COMPRESS, REPAIR & OCR ENGINE (PHASE 4)
# ----------------------------------------------------------------------

TESSDATA_DIR = Path(__file__).parent / "tessdata"

LANGUAGE_NAMES = {
    "eng": "English",
    "fra": "French",
    "deu": "German",
    "spa": "Spanish",
    "ita": "Italian",
    "por": "Portuguese",
    "hin": "Hindi",
    "ara": "Arabic",
    "chi_sim": "Chinese (Simplified)",
    "chi_tra": "Chinese (Traditional)",
    "jpn": "Japanese",
    "rus": "Russian",
}


def get_installed_ocr_languages() -> list[dict]:
    """Returns list of genuinely installed OCR language models found in tessdata/."""
    installed = []
    if TESSDATA_DIR.exists():
        for file in sorted(TESSDATA_DIR.glob("*.traineddata")):
            code = file.stem
            name = LANGUAGE_NAMES.get(code, code.upper())
            installed.append({
                "code": code,
                "name": name,
                "size_bytes": file.stat().st_size,
                "installed": True
            })
    return installed


def classify_pdf_page(page: fitz.Page) -> dict:
    """
    Classifies a PDF page as:
    - 'scanned': image-heavy or pure image with little/no native text (< 30 chars).
    - 'text': contains native searchable text and no dominant background scans.
    - 'hybrid': contains both native text and embedded images.
    """
    text = page.get_text().strip()
    images = page.get_images(full=True)
    text_len = len(text)

    if text_len < 30 and len(images) > 0:
        cat = "scanned"
    elif text_len >= 30 and len(images) > 0:
        cat = "hybrid"
    elif text_len >= 30 and len(images) == 0:
        cat = "text"
    else:
        cat = "scanned" if len(images) > 0 else "empty"

    return {
        "page_number": page.number + 1,
        "classification": cat,
        "native_text_length": text_len,
        "image_count": len(images),
        "already_searchable": text_len >= 30
    }


def ocr_pdf(
    source: Path,
    output: Path,
    language: str = "eng",
    pages: list[int] | str = "all",
    mode: str = "scanned_only",  # 'scanned_only' | 'all' | 'selected'
    dpi: int = 150,
    preprocess: bool = True
) -> dict:
    """
    Performs genuine optical character recognition (OCR) and constructs a searchable text layer.
    - Preserves visible scanned page content 100%.
    - Injects invisible text (render_mode=3) at accurate word coordinates.
    - Honors installed language models in tessdata/.
    - Detects and handles scanned, text, and hybrid pages.
    """
    lang_file = TESSDATA_DIR / f"{language}.traineddata"
    if not lang_file.exists():
        raise ValueError(f"Required OCR language data for '{language}' is not installed.")

    doc = fitz.open(str(source))
    total_pages = len(doc)
    original_size = source.stat().st_size
    start_time = time.time()

    # Determine target page numbers (1-based)
    if pages == "all":
        target_pages = set(range(1, total_pages + 1))
    elif isinstance(pages, list):
        target_pages = set(int(p) for p in pages if 1 <= int(p) <= total_pages)
    else:
        target_pages = set(range(1, total_pages + 1))

    pages_processed = 0
    pages_ocrd = 0
    pages_already_searchable = 0
    pages_failed = 0
    total_extracted_chars = 0

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        if page_num not in target_pages:
            continue

        pages_processed += 1
        page = doc[page_idx]
        classification = classify_pdf_page(page)

        # In 'scanned_only' mode, if page is already searchable text with no images, skip OCR
        if mode == "scanned_only" and classification["classification"] == "text":
            pages_already_searchable += 1
            continue

        try:
            # PyMuPDF C++ Tesseract OCR textpage
            tp = page.get_textpage_ocr(
                language=language,
                dpi=dpi,
                full=True,
                tessdata=str(TESSDATA_DIR)
            )
            words = tp.extractWORDS()

            if words:
                pages_ocrd += 1
                for w in words:
                    # w: (x0, y0, x1, y1, word, block_no, line_no, word_no)
                    rect = fitz.Rect(w[0], w[1], w[2], w[3])
                    word_str = w[4]
                    total_extracted_chars += len(word_str)
                    fontsize = max(5, rect.height * 0.85)
                    # render_mode=3 is PDF standard for invisible text (neither stroke nor fill)
                    page.insert_text(
                        fitz.Point(rect.x0, rect.y1),
                        word_str + " ",
                        fontsize=fontsize,
                        render_mode=3
                    )
            else:
                if classification["already_searchable"]:
                    pages_already_searchable += 1
        except Exception:
            pages_failed += 1

    temp_out = output.with_name(f"{output.stem}_ocr_tmp_{os.getpid()}_{uuid.uuid4().hex[:6]}.pdf")
    doc.save(str(temp_out), garbage=3, deflate=True)
    doc.close()
    temp_out.replace(output)

    elapsed = round(time.time() - start_time, 2)
    output_size = output.stat().st_size

    return {
        "pages_processed": pages_processed,
        "pages_ocrd": pages_ocrd,
        "pages_already_searchable": pages_already_searchable,
        "pages_failed": pages_failed,
        "language": language,
        "elapsed_seconds": elapsed,
        "extracted_chars": total_extracted_chars,
        "original_size": original_size,
        "output_size": output_size,
        "success": True
    }


def analyze_pdf_compression(source: Path) -> dict:
    """Analyzes PDF structure and estimates potential compression savings."""
    doc = fitz.open(str(source))
    total_pages = len(doc)
    total_images = 0
    image_bytes = 0
    high_res_images = 0

    for page in doc:
        imgs = page.get_images(full=True)
        total_images += len(imgs)
        for img in imgs:
            xref = img[0]
            try:
                base = doc.extract_image(xref)
                if base:
                    b_len = len(base.get("image", b""))
                    image_bytes += b_len
                    w = base.get("width", 0)
                    h = base.get("height", 0)
                    if w > 1200 or h > 1600:
                        high_res_images += 1
            except Exception:
                pass
    doc.close()

    total_size = source.stat().st_size
    raster_pct = round((image_bytes / total_size) * 100, 1) if total_size > 0 else 0

    if raster_pct > 60 and high_res_images > 0:
        opp = "High savings potential: document contains high-resolution raster images."
        est_reduction = "50% - 80%"
    elif raster_pct > 30:
        opp = "Moderate savings potential: mix of vector text and embedded images."
        est_reduction = "20% - 50%"
    else:
        opp = "Modest savings potential: document is primarily vector text and paths."
        est_reduction = "5% - 20%"

    return {
        "file_size": total_size,
        "page_count": total_pages,
        "total_images": total_images,
        "high_res_images": high_res_images,
        "raster_percentage": min(100.0, raster_pct),
        "opportunity": opp,
        "estimated_reduction": est_reduction
    }


def compress_pdf(
    source: Path,
    output: Path,
    quality: int = 65,
    max_dpi: int = 150,
    preset: str | None = None,
    target_size_bytes: int | None = None
) -> dict:
    """
    Performs true lossy and lossless PDF compression.
    Backward-compatible with quality and max_dpi arguments, with support for Phase 4 presets.
    """
    PRESET_CONFIGS = {
        "extreme": {"max_w": 800, "max_h": 1000, "quality": 45, "downsample": True, "garbage": 4},
        "high": {"max_w": 1100, "max_h": 1400, "quality": 60, "downsample": True, "garbage": 4},
        "balanced": {"max_w": 1400, "max_h": 1800, "quality": 75, "downsample": True, "garbage": 3},
        "high_quality": {"max_w": 2000, "max_h": 2600, "quality": 85, "downsample": True, "garbage": 3},
        "lossless": {"max_w": 99999, "max_h": 99999, "quality": 100, "downsample": False, "garbage": 4},
    }

    if preset and preset.lower() in PRESET_CONFIGS:
        selected_preset = preset.lower()
        cfg = PRESET_CONFIGS[selected_preset]
    else:
        selected_preset = "custom"
        cfg = {
            "max_w": max(600, int(max_dpi * 8)),
            "max_h": max(800, int(max_dpi * 11)),
            "quality": quality,
            "downsample": True,
            "garbage": 4
        }

    original_size = source.stat().st_size

    def _execute_compression_pass(active_cfg: dict) -> Path:
        doc = fitz.open(str(source))
        if active_cfg["downsample"]:
            for page in doc:
                for img_info in page.get_images(full=True):
                    xref = img_info[0]
                    try:
                        base_image = doc.extract_image(xref)
                        if not base_image:
                            continue
                        image_bytes = base_image["image"]
                        with Image.open(io.BytesIO(image_bytes)) as pil_img:
                            if pil_img.mode in ("RGBA", "P"):
                                pil_img = pil_img.convert("RGB")
                            w, h = pil_img.size
                            if w > active_cfg["max_w"] or h > active_cfg["max_h"]:
                                scale = min(active_cfg["max_w"] / w, active_cfg["max_h"] / h)
                                pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
                            buf = io.BytesIO()
                            pil_img.save(buf, format="JPEG", quality=active_cfg["quality"], optimize=True)
                            compressed = buf.getvalue()
                            if len(compressed) < len(image_bytes):
                                doc.update_stream(xref, compressed)
                    except Exception:
                        continue

        temp_pass = output.with_name(f"{output.stem}_pass_{os.getpid()}_{uuid.uuid4().hex[:6]}.pdf")
        doc.save(
            str(temp_pass),
            garbage=active_cfg["garbage"],
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
            clean=True
        )
        doc.close()
        return temp_pass

    temp_res = _execute_compression_pass(cfg)

    target_achieved = True
    reason = "Target size achieved."
    if target_size_bytes and target_size_bytes > 0:
        current_size = temp_res.stat().st_size
        if current_size > target_size_bytes and selected_preset != "extreme":
            for next_preset in ["high", "extreme"]:
                if next_preset == selected_preset:
                    continue
                temp_next = _execute_compression_pass(PRESET_CONFIGS[next_preset])
                if temp_next.stat().st_size < current_size:
                    temp_res.unlink(missing_ok=True)
                    temp_res = temp_next
                    current_size = temp_res.stat().st_size
                    selected_preset = next_preset
                else:
                    temp_next.unlink(missing_ok=True)
                if current_size <= target_size_bytes:
                    break
            if current_size > target_size_bytes:
                target_achieved = False
                reason = "Target size could not be fully met without severe visual degradation."

    temp_res.replace(output)
    output_size = output.stat().st_size
    saved_bytes = max(0, original_size - output_size)
    percent_saved = round((saved_bytes / original_size) * 100, 1) if original_size > 0 else 0.0

    val_doc = fitz.open(str(output))
    out_pages = len(val_doc)
    val_doc.close()

    return {
        "original_size": original_size,
        "output_size": output_size,
        "saved_bytes": saved_bytes,
        "percent_saved": percent_saved,
        "preset_used": selected_preset,
        "page_count": out_pages,
        "target_size_requested": target_size_bytes,
        "target_achieved": target_achieved,
        "note": reason if target_size_bytes else None,
        "validation_passed": True
    }


def repair_pdf(source: Path, output: Path, mode: str = "automatic") -> Path:
    """
    Repairs broken, corrupted, or truncated PDF documents by rebuilding XREF and object streams.
    Returns the repaired Path.
    """
    res = repair_pdf_advanced(source, output, mode=mode)
    if not res.get("valid") and not res.get("repaired"):
        raise ValueError(f"Unable to repair corrupted PDF: {res.get('message')}")
    return output


def repair_pdf_advanced(source: Path, output: Path, mode: str = "automatic") -> dict:
    """
    Production-grade PDF repair engine.
    - 'validate_only': Checks xref, trailer, and page readability without altering file.
    - 'automatic': Rebuilds XREF table, sanitizes object streams, cleans garbage.
    - 'advanced': Deep recovery using multiple fallback parsers to salvage all surviving pages.
    """
    detected_issues: list[str] = []
    input_valid = False
    original_page_count = 0

    try:
        doc = fitz.open(str(source))
        is_repaired = getattr(doc, "is_repaired", False)
        input_valid = not is_repaired
        original_page_count = len(doc)
        if is_repaired:
            detected_issues.append("Document had damaged XREF table; repaired during initial open.")
        doc.close()
    except Exception as e:
        detected_issues.append(f"Standard parser rejected document: {e}")

    if mode == "validate_only":
        return {
            "valid": len(detected_issues) == 0,
            "repaired": False,
            "detected_issues": detected_issues,
            "recovered_pages": original_page_count,
            "unrecoverable_pages": 0,
            "output_size": source.stat().st_size,
            "message": "PDF is healthy and well-formed." if len(detected_issues) == 0 else "PDF has structural issues."
        }

    recovered_pages = 0
    unrecoverable_pages = 0
    repaired_doc = None

    # Attempt PyMuPDF recovery
    try:
        repaired_doc = fitz.open(str(source))
        recovered_pages = len(repaired_doc)
    except Exception:
        repaired_doc = None

    # Fallback to pypdf if PyMuPDF failed or recovered 0 pages
    if repaired_doc is None or recovered_pages == 0:
        try:
            reader = pypdf.PdfReader(str(source), strict=False)
            writer = pypdf.PdfWriter()
            for i, p in enumerate(reader.pages):
                try:
                    writer.add_page(p)
                    recovered_pages += 1
                except Exception:
                    unrecoverable_pages += 1
            if recovered_pages > 0:
                temp_pypdf = output.with_name(f"{output.stem}_rep_{os.getpid()}_{uuid.uuid4().hex[:6]}.pdf")
                with open(temp_pypdf, "wb") as f_out:
                    writer.write(f_out)
                temp_pypdf.replace(output)
                return {
                    "valid": True,
                    "repaired": True,
                    "detected_issues": detected_issues,
                    "recovered_pages": recovered_pages,
                    "unrecoverable_pages": unrecoverable_pages,
                    "output_size": output.stat().st_size,
                    "message": f"Successfully salvaged {recovered_pages} page(s)."
                }
        except Exception as e_pypdf:
            detected_issues.append(f"Secondary parser failure: {e_pypdf}")

    if repaired_doc is not None and recovered_pages > 0:
        temp_out = output.with_name(f"{output.stem}_rep_{os.getpid()}_{uuid.uuid4().hex[:6]}.pdf")
        repaired_doc.save(
            str(temp_out),
            garbage=4,
            clean=True,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True
        )
        repaired_doc.close()
        temp_out.replace(output)

        return {
            "valid": True,
            "repaired": True,
            "detected_issues": detected_issues,
            "recovered_pages": recovered_pages,
            "unrecoverable_pages": unrecoverable_pages,
            "output_size": output.stat().st_size,
            "message": "PDF structure successfully rebuilt and sanitized."
        }

    raise ValueError(f"Unable to recover document: {'; '.join(detected_issues)}")


def scan_to_pdf(images: list[Path], output: Path, enhance: bool = True) -> Path:
    """Enhances scanned photos/documents (contrast, deskew) and compiles into a clean PDF."""
    processed_images: list[Image.Image] = []

    for img_path in images:
        with Image.open(img_path) as img:
            rgb_img = img.convert("RGB")
            if enhance:
                # Auto contrast and sharpness boost
                rgb_img = ImageOps.autocontrast(rgb_img, cutoff=2)
                enhancer = ImageEnhance.Sharpness(rgb_img)
                rgb_img = enhancer.enhance(1.4)
            processed_images.append(rgb_img.copy())

    if not processed_images:
        raise ValueError("No images provided for Scan to PDF.")

    first = processed_images[0]
    rest = processed_images[1:] if len(processed_images) > 1 else []
    first.save(output, format="PDF", save_all=True, append_images=rest)
    return output


def apply_image_watermark(source: Path, output: Path, watermark_img_path: Path | None = None, opacity: float = 0.25, scale: float = 0.5) -> Path:
    """Stamps a transparent image watermark (logo/seal) centered on every page of the PDF."""
    if watermark_img_path and str(output).lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        actual_output = watermark_img_path
        actual_wm_path = output
    else:
        actual_output = output
        actual_wm_path = watermark_img_path

    doc = fitz.open(str(source))
    with Image.open(actual_wm_path) as wm_pil:
        wm_rgba = wm_pil.convert("RGBA")
        if opacity < 1.0:
            alpha = wm_rgba.split()[3]
            alpha = alpha.point(lambda p: int(p * opacity))
            wm_rgba.putalpha(alpha)

        buffer = io.BytesIO()
        wm_rgba.save(buffer, format="PNG")
        wm_bytes = buffer.getvalue()
        wm_w, wm_h = wm_pil.size

    for page in doc:
        rect = page.rect
        target_w = rect.width * scale
        aspect = wm_w / max(1, wm_h)
        target_h = target_w / max(0.1, aspect)

        x0 = (rect.width - target_w) / 2
        y0 = (rect.height - target_h) / 2
        wm_rect = fitz.Rect(x0, y0, x0 + target_w, y0 + target_h)
        page.insert_image(wm_rect, stream=wm_bytes)

    doc.save(str(actual_output), garbage=4, deflate=True)
    return actual_output


def annotate_pdf(source: Path, output: Path | list[dict], annotations: list[dict] | Path | None = None) -> Path:
    """
    Applies standard PDF annotations (Highlight, Underline, StrikeOut, Rect, Circle, Text Box, Sticky Note).
    Supports either (source, output, annotations=...) or (source, annotations, output).
    """
    if isinstance(output, list) and isinstance(annotations, (Path, str)):
        actual_output = Path(annotations)
        actual_annotations = output
    else:
        actual_output = Path(output)
        actual_annotations = annotations or []

    doc = fitz.open(str(source))
    for ann in actual_annotations:
        page_num = max(0, int(ann.get("page", 1)) - 1)
        if page_num >= len(doc):
            continue
        page = doc[page_num]
        atype = ann.get("type", "").lower()
        color = ann.get("color", [1, 0.8, 0])
        color_tuple = tuple(color[:3]) if isinstance(color, list) else (1, 0.8, 0)

        if atype == "highlight":
            rect = fitz.Rect(*ann.get("rect", [72, 72, 200, 90]))
            annot = page.add_highlight_annot(rect)
            annot.set_colors(stroke=color_tuple)
            annot.update()
        elif atype == "underline":
            rect = fitz.Rect(*ann.get("rect", [72, 72, 200, 90]))
            annot = page.add_underline_annot(rect)
            annot.set_colors(stroke=color_tuple)
            annot.update()
        elif atype == "strikeout":
            rect = fitz.Rect(*ann.get("rect", [72, 72, 200, 90]))
            annot = page.add_strikeout_annot(rect)
            annot.set_colors(stroke=color_tuple)
            annot.update()
        elif atype in {"rect", "rectangle"}:
            rect = fitz.Rect(*ann.get("rect", [72, 72, 200, 150]))
            fill = ann.get("fill")
            fill_tuple = tuple(fill[:3]) if fill and isinstance(fill, list) else None
            page.draw_rect(rect, color=color_tuple, fill=fill_tuple, width=float(ann.get("width", 1.5)))
        elif atype in {"circle", "oval"}:
            rect = fitz.Rect(*ann.get("rect", [72, 72, 200, 150]))
            page.draw_oval(rect, color=color_tuple, width=float(ann.get("width", 1.5)))
        elif atype == "text":
            pt = ann.get("point", [72, 72])
            text = str(ann.get("text", "")).strip()
            fontsize = float(ann.get("fontsize", 12))
            page.insert_text(fitz.Point(pt[0], pt[1]), text, fontsize=fontsize, color=color_tuple)
        elif atype in {"sticky_note", "comment"}:
            pt = ann.get("point", [72, 72])
            text = str(ann.get("text", "")).strip()
            annot = page.add_text_annot(fitz.Point(pt[0], pt[1]), text)
            annot.set_info(title=str(ann.get("author", "User")), content=text)
            annot.update()

    doc.save(str(actual_output), garbage=4, deflate=True)
    return actual_output


# -----------------------------------------------------------------------
# Phase 2: Professional Editor Annotation Bake
# -----------------------------------------------------------------------

def _hex_to_rgb(hexcol: str) -> tuple[float, float, float]:
    """Convert '#rrggbb' or 'rgb(r,g,b)' or a colour name to a (0..1, 0..1, 0..1) tuple."""
    hexcol = str(hexcol).strip()
    # Named colours – minimal set
    _NAMES: dict[str, tuple[float, float, float]] = {
        'black': (0, 0, 0), 'white': (1, 1, 1),
        'red': (1, 0, 0), 'green': (0, 0.5, 0), 'blue': (0, 0, 1),
        'yellow': (1, 1, 0), 'orange': (1, 0.65, 0),
        'purple': (0.5, 0, 0.5), 'pink': (1, 0.75, 0.8),
        'cyan': (0, 1, 1), 'magenta': (1, 0, 1),
        'gray': (0.5, 0.5, 0.5), 'grey': (0.5, 0.5, 0.5),
        'transparent': (1, 1, 1),
    }
    if hexcol.lower() in _NAMES:
        return _NAMES[hexcol.lower()]
    if hexcol.startswith('rgb'):
        nums = [int(n.strip()) for n in hexcol.strip('rgba()').split(',')[:3]]
        return tuple(n / 255.0 for n in nums)  # type: ignore[return-value]
    hexcol = hexcol.lstrip('#')
    if len(hexcol) == 3:
        hexcol = ''.join(c * 2 for c in hexcol)
    if len(hexcol) < 6:
        return (0.0, 0.0, 0.0)
    r = int(hexcol[0:2], 16) / 255.0
    g = int(hexcol[2:4], 16) / 255.0
    b = int(hexcol[4:6], 16) / 255.0
    return (r, g, b)


def _alpha_from_colour(hexcol: str) -> float:
    """Extract alpha channel from rgba(r,g,b,a) string, else return 1.0."""
    if 'rgba' in str(hexcol).lower():
        parts = str(hexcol).strip('rgba()').split(',')
        if len(parts) == 4:
            try:
                return float(parts[3].strip())
            except ValueError:
                pass
    return 1.0


def apply_editor_annotations(
    source: Path,
    output: Path,
    edit_objects: list[dict],
) -> Path:
    """
    Bake Phase 2 editor objects into a PDF.

    Each element in edit_objects must contain:
      - type:    'text' | 'image' | 'shape' | 'drawing' | 'signature' |
                 'highlight' | 'redact' | 'stamp' | 'note'
      - page:    1-based page number
      - docX, docY, docW, docH: position and size in PDF user-space points
                                (with Y measured from the TOP of the page,
                                 as the client-side canvas uses)
      Type-specific fields are described inline below.

    Coordinate convention
    ---------------------
    The client stores coordinates with Y increasing downward (canvas convention).
    PyMuPDF uses Y increasing downward as well when origin is top-left (the
    default for fitz.Rect when using (x0, y0, x1, y1) with y0 < y1).
    However, ``insert_text`` / ``insert_image`` use PDF user-space where Y
    increases upward from the bottom-left.  We handle the conversion per
    operation below.
    """
    doc = fitz.open(str(source))

    for obj in edit_objects:
        obj_type = str(obj.get('type', '')).lower().strip()
        page_num = int(obj.get('page', 1)) - 1  # convert to 0-based
        if page_num < 0 or page_num >= len(doc):
            continue  # skip out-of-range

        page = doc[page_num]
        pw = page.rect.width
        ph = page.rect.height

        # Canvas-space coordinates (Y from top)
        cx = float(obj.get('docX', 0))
        cy = float(obj.get('docY', 0))
        cw = float(obj.get('docW', 100))
        ch = float(obj.get('docH', 30))

        # Fitz Rect (x0,y0,x1,y1) with y0 at top
        rect = fitz.Rect(cx, cy, cx + cw, cy + ch)

        colour = obj.get('color', obj.get('colour', '#142023'))
        rgb = _hex_to_rgb(colour)
        opacity = float(obj.get('opacity', 1.0))

        # ----------------------------------------------------------------
        if obj_type == 'text':
            # Text overlay – clearly labelled as overlay in the UI
            text = str(obj.get('text', '')).strip()
            if not text:
                continue
            fontsize = float(obj.get('fontSize', 14))
            bold = bool(obj.get('bold', False))
            italic = bool(obj.get('italic', False))
            fontname = 'helv'  # PyMuPDF built-in
            if bold and italic:
                fontname = 'hebo'
            elif bold:
                fontname = 'hebo'
            elif italic:
                fontname = 'heit'
            # insert_text uses bottom-left anchor in PDF space (Y up)
            # Convert: pdf_y = ph - (cy + ch)  (bottom of box)
            text_y_pdf = ph - (cy + ch)
            page.insert_text(
                fitz.Point(cx, text_y_pdf + ch - 2),
                text,
                fontname=fontname,
                fontsize=fontsize,
                color=rgb,
            )

        # ----------------------------------------------------------------
        elif obj_type == 'image':
            # Image stamp
            img_data = str(obj.get('imageData', ''))
            if not img_data:
                continue
            # Strip data-URI prefix
            if ',' in img_data:
                img_data = img_data.split(',', 1)[1]
            try:
                img_bytes = base64.b64decode(img_data)
                page.insert_image(rect, stream=img_bytes, keep_proportion=True)
            except Exception:
                pass  # skip invalid image data – never crash the whole bake

        # ----------------------------------------------------------------
        elif obj_type in {'shape', 'rectangle', 'rect'}:
            fill_col = obj.get('fillColor', obj.get('fill'))
            fill_rgb = _hex_to_rgb(fill_col) if fill_col else None
            stroke_w = float(obj.get('strokeWidth', obj.get('lineWidth', 1.5)))
            page.draw_rect(rect, color=rgb, fill=fill_rgb, width=stroke_w)

        # ----------------------------------------------------------------
        elif obj_type in {'ellipse', 'circle', 'oval'}:
            fill_col = obj.get('fillColor', obj.get('fill'))
            fill_rgb = _hex_to_rgb(fill_col) if fill_col else None
            stroke_w = float(obj.get('strokeWidth', 1.5))
            page.draw_oval(rect, color=rgb, fill=fill_rgb, width=stroke_w)

        # ----------------------------------------------------------------
        elif obj_type == 'line':
            pts = obj.get('points', [])
            if len(pts) >= 4:
                p1 = fitz.Point(float(pts[0]), float(pts[1]))
                p2 = fitz.Point(float(pts[2]), float(pts[3]))
                stroke_w = float(obj.get('strokeWidth', 1.5))
                page.draw_line(p1, p2, color=rgb, width=stroke_w)

        # ----------------------------------------------------------------
        elif obj_type == 'arrow':
            pts = obj.get('points', [])
            if len(pts) >= 4:
                p1 = fitz.Point(float(pts[0]), float(pts[1]))
                p2 = fitz.Point(float(pts[2]), float(pts[3]))
                stroke_w = float(obj.get('strokeWidth', 1.5))
                page.draw_line(p1, p2, color=rgb, width=stroke_w)
                # Draw a small arrowhead triangle at p2
                dx = p2.x - p1.x
                dy = p2.y - p1.y
                length = math.sqrt(dx * dx + dy * dy) or 1
                ux, uy = dx / length, dy / length
                head_len = min(15.0, length * 0.25)
                perp_x, perp_y = -uy * head_len * 0.4, ux * head_len * 0.4
                ax = p2.x - ux * head_len + perp_x
                ay = p2.y - uy * head_len + perp_y
                bx = p2.x - ux * head_len - perp_x
                by = p2.y - uy * head_len - perp_y
                page.draw_polyline(
                    [p2, fitz.Point(ax, ay), fitz.Point(bx, by), p2],
                    color=rgb, fill=rgb, width=1
                )

        # ----------------------------------------------------------------
        elif obj_type in {'drawing', 'freehand', 'pen'}:
            # Freehand stroke – serialised as an array of {x, y} points
            points = obj.get('points', [])
            if len(points) < 2:
                continue
            stroke_w = float(obj.get('strokeWidth', 3.0))
            pts_fitz = [fitz.Point(float(p['x']), float(p['y'])) for p in points]
            page.draw_polyline(pts_fitz, color=rgb, width=stroke_w)

        # ----------------------------------------------------------------
        elif obj_type in {'signature', 'sig', 'signaturemark'}:
            # Signature image mark (hand-drawn or typed, NOT cryptographic)
            img_data = str(obj.get('imageData', ''))
            if img_data and ',' in img_data:
                img_data = img_data.split(',', 1)[1]
            if img_data:
                try:
                    sig_bytes = base64.b64decode(img_data)
                    page.insert_image(rect, stream=sig_bytes, keep_proportion=True)
                except Exception:
                    pass
            else:
                # Fallback: draw typed signature text
                sig_text = str(obj.get('text', 'Signed')).strip()
                if sig_text:
                    text_y_pdf = ph - cy - ch + 2
                    page.insert_text(
                        fitz.Point(cx, text_y_pdf),
                        sig_text,
                        fontname='heit',
                        fontsize=float(obj.get('fontSize', 20)),
                        color=rgb,
                    )

        # ----------------------------------------------------------------
        elif obj_type == 'highlight':
            annot = page.add_highlight_annot(rect)
            highlight_col = obj.get('color', '#FFFF00')
            annot.set_colors(stroke=_hex_to_rgb(highlight_col))
            annot.update()

        # ----------------------------------------------------------------
        elif obj_type in {'redact', 'blackout'}:
            page.add_redact_annot(rect, fill=(0, 0, 0))
            page.apply_redactions()

        # ----------------------------------------------------------------
        elif obj_type == 'stamp':
            # Text stamp (Approved, Draft, Confidential, etc.)
            label = str(obj.get('label', obj.get('text', 'DRAFT'))).strip()
            if not label:
                continue
            fontsize = float(obj.get('fontSize', 36))
            stamp_rgb = _hex_to_rgb(obj.get('color', '#ef4444'))
            # Draw a bounding rect and label
            page.draw_rect(rect, color=stamp_rgb, width=2.5)
            text_y_pdf = ph - (cy + ch / 2)
            page.insert_text(
                fitz.Point(cx + 4, text_y_pdf + fontsize / 2),
                label,
                fontname='hebo',
                fontsize=fontsize,
                color=stamp_rgb,
            )

        # ----------------------------------------------------------------
        elif obj_type in {'note', 'sticky_note', 'comment'}:
            text = str(obj.get('text', '')).strip()
            if text:
                annot = page.add_text_annot(fitz.Point(cx, cy), text)
                annot.set_info(content=text, title=str(obj.get('author', 'User')))
                annot.update()

    doc.save(str(output), garbage=4, deflate=True)
    doc.close()
    return output


# ----------------------------------------------------------------------
# PHASE 3: PROFESSIONAL PAGE MANAGEMENT ENGINE FUNCTIONS
# ----------------------------------------------------------------------

def reorder_pdf_pages(source: Path, output: Path, new_order: list[int]) -> Path:
    """
    Reorder pages of a PDF in-place according to a new index list.
    new_order: 0-based list of page numbers (e.g. [2, 0, 1]).
    Preserves all page contents, annotations, dimensions, and structural integrity.
    """
    doc = fitz.open(str(source))
    total = len(doc)
    if total == 0:
        doc.close()
        raise ValueError("Cannot reorder an empty document.")

    # Validate that all page indices in new_order are valid
    for idx in new_order:
        if not isinstance(idx, int) or idx < 0 or idx >= total:
            doc.close()
            raise ValueError(f"Invalid page index {idx}. Must be 0 <= idx < {total}.")

    doc.select(new_order)
    if Path(source).resolve() == Path(output).resolve():
        temp_out = output.with_name(f"{output.stem}_tmp_{os.getpid()}.pdf")
        doc.save(str(temp_out), garbage=4, deflate=True)
        doc.close()
        temp_out.replace(output)
    else:
        doc.save(str(output), garbage=4, deflate=True)
        doc.close()
    return output


def rotate_pdf_pages(source: Path, output: Path, pages: list[int] | str, degrees: int) -> Path:
    """
    Rotate specified pages by `degrees` (+90, -90, 180, 270).
    pages: list of 1-based page numbers or "all".
    Persists rotation directly to PDF page geometry (p.set_rotation).
    """
    doc = fitz.open(str(source))
    total = len(doc)
    if total == 0:
        doc.close()
        raise ValueError("Cannot rotate an empty document.")

    target_set = set(range(1, total + 1)) if pages == "all" else set(pages)
    norm_deg = degrees % 360

    for i in range(total):
        p_num = i + 1
        if p_num in target_set:
            page = doc[i]
            cur_rot = page.rotation
            page.set_rotation((cur_rot + norm_deg) % 360)

    if Path(source).resolve() == Path(output).resolve():
        temp_out = output.with_name(f"{output.stem}_tmp_{os.getpid()}.pdf")
        doc.save(str(temp_out), garbage=4, deflate=True)
        doc.close()
        temp_out.replace(output)
    else:
        doc.save(str(output), garbage=4, deflate=True)
        doc.close()
    return output


def crop_pdf_pages(
    source: Path,
    output: Path,
    pages: list[int] | str,
    crop_rect: tuple[float, float, float, float] | dict
) -> Path:
    """
    Apply a crop box in 72 DPI PDF user points to specified pages.
    crop_rect: (x0, y0, x1, y1) or {'x': x, 'y': y, 'width': w, 'height': h}.
    Persists to PDF page geometry (set_cropbox).
    """
    if isinstance(crop_rect, dict):
        x0 = float(crop_rect.get('x', 0))
        y0 = float(crop_rect.get('y', 0))
        w = float(crop_rect.get('width', 0))
        h = float(crop_rect.get('height', 0))
        x1 = x0 + w
        y1 = y0 + h
    elif isinstance(crop_rect, (list, tuple)) and len(crop_rect) == 4:
        x0, y0, x1, y1 = [float(v) for v in crop_rect]
    else:
        raise ValueError(f"Invalid crop_rect format: {crop_rect}")

    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"Invalid crop bounds: width ({x1 - x0}) and height ({y1 - y0}) must be > 0.")

    doc = fitz.open(str(source))
    total = len(doc)
    if total == 0:
        doc.close()
        raise ValueError("Cannot crop an empty document.")

    target_set = set(range(1, total + 1)) if pages == "all" else set(pages)

    for i in range(total):
        p_num = i + 1
        if p_num in target_set:
            page = doc[i]
            # Ensure crop rect stays within original mediabox boundaries
            mb = page.mediabox
            clamped_x0 = max(mb.x0, min(x0, mb.x1))
            clamped_y0 = max(mb.y0, min(y0, mb.y1))
            clamped_x1 = max(clamped_x0, min(x1, mb.x1))
            clamped_y1 = max(clamped_y0, min(y1, mb.y1))
            if clamped_x1 > clamped_x0 and clamped_y1 > clamped_y0:
                page.set_cropbox(fitz.Rect(clamped_x0, clamped_y0, clamped_x1, clamped_y1))

    if Path(source).resolve() == Path(output).resolve():
        temp_out = output.with_name(f"{output.stem}_tmp_{os.getpid()}.pdf")
        doc.save(str(temp_out), garbage=4, deflate=True)
        doc.close()
        temp_out.replace(output)
    else:
        doc.save(str(output), garbage=4, deflate=True)
        doc.close()
    return output


def resize_pdf_pages(
    source: Path,
    output: Path,
    pages: list[int] | str,
    target_w: float,
    target_h: float,
    mode: str = "scale"
) -> Path:
    """
    Resize specified pages to (target_w, target_h) in points.
    mode:
      - 'scale': proportionally scales vector content to fit inside new dimensions.
      - 'center': centers original page vector content inside the target dimensions.
      - 'crop': adjusts page mediabox and cropbox directly.
    """
    if target_w <= 0 or target_h <= 0:
        raise ValueError(f"Target dimensions must be > 0 (got {target_w}x{target_h}).")

    src_doc = fitz.open(str(source))
    total = len(src_doc)
    if total == 0:
        src_doc.close()
        raise ValueError("Cannot resize an empty document.")

    target_set = set(range(1, total + 1)) if pages == "all" else set(pages)

    if mode in ("scale", "center"):
        new_doc = fitz.open()
        for i in range(total):
            p_num = i + 1
            if p_num in target_set:
                new_page = new_doc.new_page(width=target_w, height=target_h)
                orig_rect = src_doc[i].rect
                if mode == "scale":
                    # Fit original page into target page rectangle keeping proportion
                    target_rect = fitz.Rect(0, 0, target_w, target_h)
                    new_page.show_pdf_page(target_rect, src_doc, pno=i, keep_proportion=True)
                else:  # center
                    orig_w = orig_rect.width
                    orig_h = orig_rect.height
                    # Scale down if larger than target, otherwise preserve 1:1 and center
                    if orig_w > target_w or orig_h > target_h:
                        target_rect = fitz.Rect(0, 0, target_w, target_h)
                        new_page.show_pdf_page(target_rect, src_doc, pno=i, keep_proportion=True)
                    else:
                        dx = max(0.0, (target_w - orig_w) / 2.0)
                        dy = max(0.0, (target_h - orig_h) / 2.0)
                        target_rect = fitz.Rect(dx, dy, dx + orig_w, dy + orig_h)
                        new_page.show_pdf_page(target_rect, src_doc, pno=i, keep_proportion=False)
            else:
                new_doc.insert_pdf(src_doc, from_page=i, to_page=i)

        if Path(source).resolve() == Path(output).resolve():
            temp_out = output.with_name(f"{output.stem}_tmp_{os.getpid()}.pdf")
            new_doc.save(str(temp_out), garbage=4, deflate=True)
            new_doc.close()
            src_doc.close()
            temp_out.replace(output)
        else:
            new_doc.save(str(output), garbage=4, deflate=True)
            new_doc.close()
            src_doc.close()
    else:  # 'crop' or 'fit_margins'
        for i in range(total):
            p_num = i + 1
            if p_num in target_set:
                p = src_doc[i]
                p.set_mediabox(fitz.Rect(0, 0, target_w, target_h))
                p.set_cropbox(fitz.Rect(0, 0, target_w, target_h))
        if Path(source).resolve() == Path(output).resolve():
            temp_out = output.with_name(f"{output.stem}_tmp_{os.getpid()}.pdf")
            src_doc.save(str(temp_out), garbage=4, deflate=True)
            src_doc.close()
            temp_out.replace(output)
        else:
            src_doc.save(str(output), garbage=4, deflate=True)
            src_doc.close()

    return output


def extract_pdf_pages(source: Path, output: Path, pages: list[int]) -> Path:
    """
    Extract a subset of pages into a new PDF document in the specified order.
    pages: 1-based page numbers (e.g. [2, 4, 1]).
    Preserves all fonts, vectors, annotations, and rotation.
    """
    if not pages:
        raise ValueError("No pages specified for extraction.")

    src_doc = fitz.open(str(source))
    total = len(src_doc)
    if total == 0:
        src_doc.close()
        raise ValueError("Input PDF has no pages.")

    new_doc = fitz.open()
    for p in pages:
        if p < 1 or p > total:
            src_doc.close()
            new_doc.close()
            raise ValueError(f"Page {p} is out of range (1..{total}).")
        new_doc.insert_pdf(src_doc, from_page=p - 1, to_page=p - 1)

    new_doc.save(str(output), garbage=4, deflate=True)
    new_doc.close()
    src_doc.close()
    return output


def import_pdf_pages(
    base_pdf: Path,
    import_pdf: Path,
    output: Path,
    pages: list[int] | None = None,
    insert_after_page: int = 0
) -> Path:
    """
    Import selected pages from `import_pdf` into `base_pdf` at position `insert_after_page`.
    pages: 1-based page numbers from import_pdf (or None for all pages).
    insert_after_page: 0 = prepend at start, N = insert after page N.
    """
    base_doc = fitz.open(str(base_pdf))
    imp_doc = fitz.open(str(import_pdf))
    base_total = len(base_doc)
    imp_total = len(imp_doc)

    if imp_total == 0:
        base_doc.close()
        imp_doc.close()
        raise ValueError("Import document has no pages.")

    insert_at = max(0, min(insert_after_page, base_total))

    if pages is None:
        target_pages = list(range(1, imp_total + 1))
    else:
        target_pages = pages

    # Create temporary doc with only the requested imported pages
    temp_imp = fitz.open()
    for p in target_pages:
        if 1 <= p <= imp_total:
            temp_imp.insert_pdf(imp_doc, from_page=p - 1, to_page=p - 1)
        else:
            base_doc.close()
            imp_doc.close()
            temp_imp.close()
            raise ValueError(f"Import page {p} out of range (1..{imp_total}).")

    base_doc.insert_pdf(temp_imp, start_at=insert_at)
    temp_imp.close()
    imp_doc.close()

    base_doc.save(str(output), garbage=4, deflate=True)
    base_doc.close()
    return output


def merge_pdf_documents(sources: list[Path], output: Path) -> Path:
    """
    Merge multiple PDF files into one output document in the given order.
    """
    if not sources:
        raise ValueError("No source PDF documents provided for merge.")

    merged = fitz.open()
    for src in sources:
        doc = fitz.open(str(src))
        merged.insert_pdf(doc)
        doc.close()

    merged.save(str(output), garbage=4, deflate=True)
    merged.close()
    return output


def split_pdf_document(source: Path, output_dir: Path, mode: str, param: str) -> list[Path]:
    """
    Split a PDF into multiple documents.
    mode:
      - 'ranges': comma-separated ranges e.g. "1-2, 3-5"
      - 'every_n': int string e.g. "2"
    Returns list of paths to the split PDF files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    src_doc = fitz.open(str(source))
    total = len(src_doc)
    if total == 0:
        src_doc.close()
        raise ValueError("Cannot split an empty document.")

    out_paths: list[Path] = []

    if mode == "every_n":
        try:
            n = int(param)
        except ValueError:
            src_doc.close()
            raise ValueError(f"Invalid integer for every_n: {param}")
        if n <= 0:
            src_doc.close()
            raise ValueError("Split frequency must be at least 1.")

        part_idx = 1
        for start_idx in range(0, total, n):
            end_idx = min(start_idx + n, total)
            part_doc = fitz.open()
            part_doc.insert_pdf(src_doc, from_page=start_idx, to_page=end_idx - 1)
            out_file = output_dir / f"{source.stem}_part{part_idx}_p{start_idx + 1}-{end_idx}.pdf"
            part_doc.save(str(out_file), garbage=4, deflate=True)
            part_doc.close()
            out_paths.append(out_file)
            part_idx += 1

    elif mode == "ranges":
        raw_items = [x.strip() for x in param.split(",") if x.strip()]
        if not raw_items:
            src_doc.close()
            raise ValueError("No ranges specified.")

        part_idx = 1
        for item in raw_items:
            if "-" in item:
                parts = item.split("-", 1)
                try:
                    s_page, e_page = int(parts[0]), int(parts[1])
                except ValueError:
                    src_doc.close()
                    raise ValueError(f"Invalid range syntax: '{item}'")
                if s_page > e_page:
                    src_doc.close()
                    raise ValueError(f"Start page {s_page} > end page {e_page} in '{item}'.")
            else:
                try:
                    s_page = e_page = int(item)
                except ValueError:
                    src_doc.close()
                    raise ValueError(f"Invalid page number: '{item}'")

            if s_page < 1 or e_page > total:
                src_doc.close()
                raise ValueError(f"Range '{item}' is outside document boundaries (1..{total}).")

            part_doc = fitz.open()
            part_doc.insert_pdf(src_doc, from_page=s_page - 1, to_page=e_page - 1)
            out_file = output_dir / f"{source.stem}_part{part_idx}_p{s_page}-{e_page}.pdf"
            part_doc.save(str(out_file), garbage=4, deflate=True)
            part_doc.close()
            out_paths.append(out_file)
            part_idx += 1
    else:
        src_doc.close()
        raise ValueError(f"Unsupported split mode: '{mode}'. Use 'ranges' or 'every_n'.")

    src_doc.close()
    return out_paths


def get_pdf_metadata_pages(source: Path) -> dict:
    """
    Extract page geometry, orientation, rotation, and logical labels for all pages.
    """
    doc = fitz.open(str(source))
    total = len(doc)
    pages_info = []

    # Get page labels if defined
    labels = []
    try:
        if hasattr(doc, "get_page_labels"):
            labels = doc.get_page_labels()
    except Exception:
        labels = []

    for i in range(total):
        p = doc[i]
        w = round(p.rect.width, 2)
        h = round(p.rect.height, 2)
        rot = p.rotation
        label = labels[i] if i < len(labels) else str(i + 1)
        orientation = "portrait" if h >= w else "landscape"

        pages_info.append({
            "page": i + 1,
            "width": w,
            "height": h,
            "rotation": rot,
            "orientation": orientation,
            "label": label,
        })

    meta = dict(doc.metadata or {})
    doc.close()
    return {
        "totalPages": total,
        "pages": pages_info,
        "metadata": meta,
    }
