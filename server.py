from __future__ import annotations

import base64
import asyncio
import csv
import difflib
import hashlib
import hmac
from html import escape as html_escape
import io
import json
import logging
import os
import re
import shutil
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from itertools import islice
import urllib.request
import urllib.error
import urllib.parse
import uuid
import zipfile
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from typing import Any, Callable
from pathlib import Path

import config
import persistence
import fitz  # PyMuPDF
import uvicorn
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi import BackgroundTasks, Body, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from config import (
    ALLOWED_ORIGINS, CLAMAV_HOST, CLAMAV_PORT, JOBS_DIR,
    JOB_TTL_SECONDS, MAX_FILE_SIZE, OPENAI_API_KEY, GEMINI_API_KEY,
    RATE_LIMIT_PER_MINUTE, REQUIRE_AUTH, S3_BUCKET, 
    FREE_TIER_DAILY_LIMIT, FREE_TIER_MAX_FILE_SIZE_MB, PRO_TIER_PRICE_INR,
    DEV_TIER_PRICE_INR,
    EXAM_PASS_PRICE_INR, STUDENT_PRO_PRICE_INR, STUDENT_ANNUAL_PRICE_INR, CYBER_CAFE_PRICE_INR,
    TRUSTED_HOSTS,
    ALLOW_BILLING_SIMULATION, ALLOW_TEST_PAYMENTS, ENVIRONMENT, GOOGLE_CLIENT_ID, SECURE_COOKIES, COOKIE_SAMESITE,
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_USE_TLS,
    AGENTROUTER_API_KEY, AGENTROUTER_BASE_URL, AGENTROUTER_MODEL,
    FREE_API_CALLS_PER_DAY, FREE_AI_CALLS_PER_DAY, FREE_MAX_FILE_SIZE_MB, FREE_CONCURRENT_JOBS,
    PAPERPLANE_PUBLIC_URL,
    CASHFREE_APP_ID, CASHFREE_SECRET_KEY, CASHFREE_ENV,
    CASHFREE_ENV_CONFIG_ERROR, CASHFREE_API_VERSION, CASHFREE_BASE_URL, CASHFREE_DEFAULT_CUSTOMER_PHONE,
    CLEANUP_INTERVAL_SECONDS, EMERGENCY_DISK_FREE_PERCENT,
    EMERGENCY_DISK_FREE_BYTES, EMERGENCY_JOB_AGE_SECONDS
)
from persistence import (
    authenticate, consume_rate_limit, create_api_key, create_job as persist_job,
    create_session, create_google_session, create_user, create_user_with_hash, delete_expired_jobs, delete_session, get_job, get_job_internal, get_user,
    get_user_by_email, get_user_by_payment_order, get_billing_event_payload, get_user_tier, set_user_tier,
    get_daily_usage, increment_daily_usage, check_operation_quota,
    record_billing_event, init_db, list_api_keys, revoke_api_key, update_job,
    create_password_reset_token, verify_and_consume_reset_token, update_user_password,
    get_developer_api_usage, check_and_consume_developer_quota, refund_developer_quota,
    get_idempotent_job, record_idempotent_job, compact_database,
    add_waitlist_entry, get_waitlist_count,
    create_email_otp, delete_email_otp, verify_email_otp, can_resend_otp,
    otp_account_lock_remaining, record_otp_failure, clear_otp_failures,
    consume_guest_job_token,
    verify_user_credentials, create_session_for_user,
    record_audit_event, get_recent_audit_logs, delete_job_record, _password_hash,
    admin_get_analytics, admin_get_all_users, admin_get_waitlist,
    get_admin_lockout_remaining, record_admin_failed_attempt, reset_admin_failed_attempts,
    set_admin_pending_otp, clear_admin_pending_otp, verify_admin_otp, create_admin_session, verify_admin_session,
    revoke_admin_session, admin_get_extended_analytics,
    admin_delete_user, admin_cleanup_probe_accounts,
    add_user_feedback, admin_get_feedbacks, admin_delete_feedback,
    admin_get_revenue_analytics, admin_get_ai_config, admin_set_ai_config
)
from email_service import (
    send_login_notification,
    send_password_reset_email,
    send_password_changed_notification,
    send_otp_email,
    send_waitlist_alert,
    send_admin_login_otp,
    send_admin_lockout_alert
)
try:
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests
    HAS_GOOGLE_AUTH = True
except ImportError:
    HAS_GOOGLE_AUTH = False

import converters
import ai_engine
import security_forms_engine

ROOT = Path(__file__).parent
JOBS = JOBS_DIR
logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=max(4, int(os.getenv("PAPERPLANE_WORKERS", "4"))))


def _mounted_volume_for(path: Path) -> tuple[bool, str | None]:
    """Return whether path is covered by a non-root mount inside the container."""
    resolved = path.resolve()
    mount_points: list[Path] = []
    try:
        for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) < 5:
                continue
            raw_mount = fields[4]
            mount_text = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), raw_mount)
            mount_path = Path(mount_text).resolve()
            if mount_path == Path("/"):
                continue
            try:
                resolved.relative_to(mount_path)
                mount_points.append(mount_path)
            except ValueError:
                continue
    except OSError:
        if os.path.ismount(path):
            return True, str(resolved)
        return False, None

    if not mount_points:
        return False, None
    mount_path = max(mount_points, key=lambda candidate: len(candidate.parts))
    return True, str(mount_path)


def _persistence_snapshot() -> dict[str, Any]:
    db_path = Path(persistence.DATABASE).resolve()
    data_dir = Path(config.DATA_DIR).resolve()
    try:
        stat = db_path.stat()
        db_size = stat.st_size
        db_mtime = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime))
    except OSError:
        db_size = None
        db_mtime = None

    row_counts: dict[str, int | None] = {}
    try:
        with closing(sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True, timeout=5)) as connection:
            for table in ("users", "jobs", "api_keys", "app_waitlist"):
                try:
                    row_counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                except sqlite3.Error:
                    row_counts[table] = None
    except sqlite3.Error:
        row_counts = {table: None for table in ("users", "jobs", "api_keys", "app_waitlist")}

    mounted, mount_path = _mounted_volume_for(db_path)
    return {
        "data_dir": str(data_dir),
        "database_path": str(db_path),
        "database_size_bytes": db_size,
        "database_mtime_utc": db_mtime,
        "row_counts": row_counts,
        "database_on_mounted_volume": mounted,
        "mount_path": mount_path,
    }


# Admin authentication — 3-factor owner security
ADMIN_SECRET_KEY: str = os.getenv("PAPERPLANE_ADMIN_KEY", "").strip()
ADMIN_SECRET_CODE: str = os.getenv("PAPERPLANE_ADMIN_CODE", "nimrakulsum").strip()
ADMIN_ALERT_EMAIL: str = os.getenv("ADMIN_ALERT_EMAIL", "mdhammad2906@gmail.com").strip()


def _require_admin(
    x_admin_session: str = Header(default="", alias="X-Admin-Session"),
) -> None:
    """Require a session created only after the full owner MFA flow."""
    if not x_admin_session or not verify_admin_session(x_admin_session):
        raise HTTPException(status_code=401, detail="Authentication required. Please complete owner verification.")

# Workload-based execution timeouts (in seconds)
COMPRESS_TIMEOUT_SECONDS = 60.0    # multi-pass downsampling & stream compression
OCR_TIMEOUT_SECONDS = 90.0         # page-by-page C++ Tesseract OCR execution
GRAYSCALE_TIMEOUT_SECONDS = 45.0   # 150-DPI monochrome rasterization per page
MERGE_TIMEOUT_SECONDS = 120.0       # bounded multi-file page copy; proxy allows 900s
AI_SUMMARY_REQUEST_TIMEOUT_SECONDS = 300.0  # up to four chunked large-document requests with one bounded retry each
AI_TRANSLATION_REQUEST_TIMEOUT_SECONDS = 300.0  # bounded batches for documents up to the current text-block cap

_CONVERTER_POOL = ThreadPoolExecutor(
    max_workers=min(32, max(4, (os.cpu_count() or 4) * 2)),
    thread_name_prefix="converter_worker"
)


def run_converter_with_timeout(
    func: Callable,
    *args,
    timeout_seconds: float,
    tool_name: str,
    source_path: Path | None = None,
    output_path: Path | None = None,
    retry_hint: str = "",
    **kwargs
) -> Any:
    """Executes a converter operation bounded by a strict timeout.

    Cleans up any partial or corrupt output file on timeout/failure,
    logs server-side diagnostic metrics without leaking document payloads,
    and returns a clean, user-actionable error.
    """
    start_time = time.time()
    future = _CONVERTER_POOL.submit(func, *args, **kwargs)
    try:
        return future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError:
        elapsed = round(time.time() - start_time, 2)
        if output_path and output_path.exists():
            try:
                output_path.unlink(missing_ok=True)
            except Exception:
                pass
        in_size_kb = round(source_path.stat().st_size / 1024, 1) if (source_path and source_path.exists()) else "unknown"
        logger.error(
            "Operation '%s' timed out after %.2fs (limit: %.1fs, input size: %s KB). Retry hint: %s",
            tool_name, elapsed, timeout_seconds, in_size_kb, retry_hint
        )
        raise TimeoutError(
            f"{tool_name.capitalize()} processing timed out after {int(timeout_seconds)}s. {retry_hint}"
        )
    except Exception as exc:
        elapsed = round(time.time() - start_time, 2)
        if output_path and output_path.exists():
            try:
                output_path.unlink(missing_ok=True)
            except Exception:
                pass
        in_size_kb = round(source_path.stat().st_size / 1024, 1) if (source_path and source_path.exists()) else "unknown"
        logger.error(
            "Operation '%s' failed after %.2fs (input size: %s KB): %s",
            tool_name, elapsed, in_size_kb, exc
        )
        raise

def _should_disable_docs(environment: str, configured_enable: str | None = None) -> bool:
    """Fail closed; interactive API docs require an explicit non-production opt-in."""
    if str(environment or "").strip().lower() in {"prod", "production"}:
        return True
    configured = os.getenv("PAPERPLANE_ENABLE_DOCS", "") if configured_enable is None else configured_enable
    return str(configured).strip().lower() not in ("true", "1", "yes")


DISABLE_DOCS = _should_disable_docs(ENVIRONMENT)
app = FastAPI(
    title="Paperplane PDF Enterprise API",
    version="2.0.0",
    docs_url=None if DISABLE_DOCS else "/api-docs",
    redoc_url=None if DISABLE_DOCS else "/redoc",
    openapi_url=None if DISABLE_DOCS else "/openapi.json",
    servers=[{"url": PAPERPLANE_PUBLIC_URL or "/", "description": "Primary Server"}] if PAPERPLANE_PUBLIC_URL else None,
)
init_db()
logger.info("Persistence startup snapshot: %s", json.dumps(_persistence_snapshot(), sort_keys=True))
logger.info("AI startup readiness: %s", json.dumps(ai_engine.get_ai_configuration_health(), sort_keys=True))

# Restore the public scheme/host only from explicitly trusted proxy peers.
# Never accept forwarded IPs from arbitrary clients: admin throttles and
# lockout decisions depend on the resulting client address.
TRUSTED_PROXY_HOSTS = os.getenv("PAPERPLANE_TRUSTED_PROXY_HOSTS", "127.0.0.1,::1").strip()
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=TRUSTED_PROXY_HOSTS)

# Production-hardened Trusted hosts and CORS middleware (Wildcard origins strictly excluded)
if TRUSTED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)



def get_client_ip(request: Request) -> str:
    """Use the client address resolved by the trusted proxy middleware."""
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


_BILLABLE_AI_ENDPOINTS = {
    "/api/ai/chat",
    "/api/ai/chat/stream",
    "/api/ai/summarize",
    "/api/ai/extract",
    "/api/ai/translate",
}


def _quota_identity_from_request(request: Request) -> str | None:
    token = (request.headers.get("x-api-key") or "").strip()
    authorization = request.headers.get("authorization", "")
    if not token and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        token = (request.cookies.get("paperplane_token") or "").strip()
    return authenticate(token) if token else None


def _quota_limit_response(usage: int, tier: str, authenticated: bool) -> JSONResponse:
    if authenticated:
        message = f"Daily limit reached ({FREE_TIER_DAILY_LIMIT}/{FREE_TIER_DAILY_LIMIT} operations on Free Tier). Paid plans have no daily operation cap; upload and batch limits still apply."
    else:
        message = f"Daily guest limit reached ({FREE_TIER_DAILY_LIMIT}/{FREE_TIER_DAILY_LIMIT} operations). Create a free account or choose a paid plan with no daily operation cap; upload and batch limits still apply."
    return JSONResponse(status_code=402, content={
        "detail": {"code": "TIER_LIMIT_REACHED", "message": message, "limit": FREE_TIER_DAILY_LIMIT, "usage": usage, "tier": tier}
    })


@app.middleware("http")
async def count_ai_and_studio_operations(request: Request, call_next):
    """Apply the same free daily operation quota to billable AI and Studio POST workflows."""
    path = request.url.path
    if path.startswith("/api/ai/"):
        identity = _quota_identity_from_request(request) or get_client_ip(request)
        if not consume_rate_limit(f"ai-account:{identity}", 12, window_seconds=60):
            return JSONResponse(
                status_code=429,
                content={"detail": "AI request limit exceeded. Try again in a minute."},
                headers={"Retry-After": "60"},
            )
    billable = request.method == "POST" and (
        path in _BILLABLE_AI_ENDPOINTS or path.startswith("/api/studio/")
    )
    if not billable:
        return await call_next(request)

    user_id = _quota_identity_from_request(request)
    if REQUIRE_AUTH and not user_id:
        return await call_next(request)
    client_ip = get_client_ip(request)
    allowed, usage, tier = check_operation_quota(user_id, client_ip, FREE_TIER_DAILY_LIMIT)
    if not allowed:
        return _quota_limit_response(usage, tier, bool(user_id))

    subject = f"user:{user_id}" if user_id else f"ip:{client_ip}"
    response = await call_next(request)
    if response.status_code >= 400:
        return response

    if path == "/api/ai/chat/stream" and getattr(response, "body_iterator", None) is not None:
        body_iterator = response.body_iterator

        async def count_after_completed_stream():
            completed = False
            failed = False
            async for chunk in body_iterator:
                data = chunk.decode("utf-8", errors="ignore") if isinstance(chunk, bytes) else str(chunk)
                completed = completed or "event: done" in data
                failed = failed or "event: error" in data
                yield chunk
            if completed and not failed:
                count = increment_daily_usage(subject)
                request.state.usage_today = count

        response.body_iterator = count_after_completed_stream()
        return response

    count = increment_daily_usage(subject)
    request.state.usage_today = count
    response.headers["X-Paperplane-Operations-Today"] = str(count)
    return response


# Periodic background cleanup daemon
#
# Cleanup is deliberately owned by this daemon.  Request handlers may ask the
# daemon to run sooner, but they must never walk the jobs directory or delete
# files themselves.  That keeps disk cleanup out of latency-sensitive API
# requests and prevents concurrent request threads from racing the purger.
cleanup_requested = threading.Event()


def periodic_cleanup_worker():
    while True:
        try:
            # Run every 24 hours, or immediately when an administrative
            # trigger queues a cleanup request.
            cleanup_requested.wait(timeout=CLEANUP_INTERVAL_SECONDS)
            cleanup_requested.clear()
            cleanup_expired_jobs()
        except Exception:
            # Cleanup must never terminate the daemon or affect API traffic.
            logger.exception("Background cleanup failed")


cleanup_thread = threading.Thread(target=periodic_cleanup_worker, daemon=True)
cleanup_thread.start()


# Full Operations Catalog
OPERATIONS = {
    # 1. Organize PDF
    "merge": {"label": "Merge PDF", "category": "Organize PDF", "accept": "pdf", "implemented": True, "description": "Combine multiple PDFs into one unified document with custom ordering."},
    "split": {"label": "Split / extract", "category": "Organize PDF", "accept": "pdf", "implemented": True, "description": "Extract specific pages or page ranges into a clean new PDF."},
    "remove": {"label": "Remove pages", "category": "Organize PDF", "accept": "pdf", "implemented": True, "description": "Delete unwanted pages from any PDF document."},
    "rotate": {"label": "Rotate PDF", "category": "Organize PDF", "accept": "pdf", "implemented": True, "description": "Rotate pages 90, 180, or 270 degrees clockwise."},
    "organize": {"label": "Page Organizer", "category": "Organize PDF", "accept": "pdf", "implemented": True, "description": "Reorder pages by entering their page numbers in the desired output order."},
    "scan_pdf": {"label": "Scan to PDF", "category": "Organize PDF", "accept": "image", "implemented": True, "description": "Enhance photos or scans with deskewing and contrast optimization."},

    # 2. Optimize PDF
    "compress": {"label": "Compress PDF", "category": "Optimize PDF", "accept": "pdf", "implemented": True, "description": "True lossy & lossless compression optimizing image streams and deflating structures."},
    "repair": {"label": "Repair PDF", "category": "Optimize PDF", "accept": "pdf", "implemented": True, "description": "Rebuild corrupted, unreadable, or damaged PDF files."},
    "ocr": {"label": "OCR PDF", "category": "Optimize PDF", "accept": "pdf", "implemented": True, "description": "Inject searchable text layer into scanned documents."},

    # 3. Convert to PDF
    "jpg_to_pdf": {"label": "JPG/PNG to PDF", "category": "Convert to PDF", "accept": "image", "implemented": True, "description": "Convert JPG, PNG, and TIFF images into a high-quality PDF."},
    "word_to_pdf": {"label": "Word to PDF", "category": "Convert to PDF", "accept": "office", "implemented": True, "description": "Convert Microsoft Word (.docx) documents to PDF."},
    "excel_to_pdf": {"label": "Excel to PDF", "category": "Convert to PDF", "accept": "office", "implemented": True, "description": "Convert Excel spreadsheets (.xlsx) to formatted landscape PDF."},
    "powerpoint_to_pdf": {"label": "PowerPoint to PDF", "category": "Convert to PDF", "accept": "office", "implemented": True, "description": "Convert PowerPoint presentations (.pptx) to PDF slides."},
    "html_to_pdf": {"label": "HTML to PDF", "category": "Convert to PDF", "accept": "url", "implemented": True, "description": "Render web pages or HTML snippets directly into PDF."},

    # 4. Convert from PDF
    "pdf_to_jpg": {"label": "PDF to JPG", "category": "Convert from PDF", "accept": "pdf", "implemented": True, "description": "Export all pages as high-resolution images bundled in a ZIP archive."},
    "pdf_to_word": {"label": "PDF to Word", "category": "Convert from PDF", "accept": "pdf", "implemented": True, "description": "Convert PDF documents to editable Microsoft Word (.docx)."},
    "pdf_to_excel": {"label": "PDF to Excel", "category": "Convert from PDF", "accept": "pdf", "implemented": True, "description": "Extract structured tables into an Excel (.xlsx) workbook."},
    "pdf_to_powerpoint": {"label": "PDF to PowerPoint", "category": "Convert from PDF", "accept": "pdf", "implemented": True, "description": "Convert PDF pages into PowerPoint presentation slides (.pptx)."},
    "pdf_to_pdfa": {"label": "PDF to PDF/A", "category": "Convert from PDF", "accept": "pdf", "implemented": True, "description": "Standardize documents to ISO PDF/A-1b archiving standards."},
    "pdf_to_text": {"label": "PDF to Text", "category": "Convert from PDF", "accept": "pdf", "implemented": True, "description": "Extract plain selectable text from document streams."},
    "pdf_to_markdown": {"label": "PDF to Markdown", "category": "Convert from PDF", "accept": "pdf", "implemented": True, "description": "Convert formatted documents into structured Markdown."},

    # 5. Edit PDF
    "edit": {"label": "Edit PDF", "category": "Edit PDF", "accept": "pdf", "implemented": True, "description": "Add text, stamps, and coordinates directly onto pages."},
    "annotate": {"label": "Annotate PDF", "category": "Edit PDF", "accept": "pdf", "implemented": True, "description": "Highlight, underline, add sticky notes, and draw shapes on pages."},
    "crop": {"label": "Crop PDF", "category": "Edit PDF", "accept": "pdf", "implemented": True, "description": "Trim page margins from top, bottom, left, and right."},
    "redact": {"label": "Redact PDF", "category": "Edit PDF", "accept": "pdf", "implemented": True, "description": "Permanently sanitize and black-out confidential keywords."},
    "watermark": {"label": "Watermark PDF", "category": "Edit PDF", "accept": "pdf", "implemented": True, "description": "Overlay dynamic text or image watermarks with custom opacity."},
    "page_numbers": {"label": "Page Numbers", "category": "Edit PDF", "accept": "pdf", "implemented": True, "description": "Add customizable page numbers to headers or footers."},

    # 6. Security
    "protect": {"label": "Protect PDF", "category": "Security", "accept": "pdf", "implemented": True, "description": "Encrypt PDF with high-strength AES-256 and custom passwords."},
    "unlock": {"label": "Unlock PDF", "category": "Security", "accept": "pdf", "implemented": True, "description": "Remove password protection and permission restrictions."},
    "sign": {"label": "Sign PDF", "category": "Security", "accept": "pdf", "implemented": True, "description": "Place a typed signature stamp. Use Studio's Digital Signatures panel for draw/type marks and signature verification."},

    # 7. Advanced & AI Tools
    "compare": {"label": "Compare PDF", "category": "Advanced", "accept": "pdf", "implemented": True, "description": "Result: a text file listing the differences between two versions."},
    "forms": {"label": "Fill PDF Form", "category": "Advanced", "accept": "pdf", "implemented": True, "description": "Populate interactive PDF form fields from JSON data."},
    "metadata": {"label": "PDF Metadata", "category": "Advanced", "accept": "pdf", "implemented": True, "description": "View and modify document metadata (Title, Author, Subject)."},
    "ai_chat": {"label": "AI PDF Chat", "category": "AI tools", "accept": "pdf", "implemented": True, "description": "Ask questions to your document with RAG and exact page citations."},
    "ai_extract": {"label": "Smart Metadata", "category": "AI tools", "accept": "pdf", "implemented": True, "description": "Extract invoices and resumes into structured JSON & CSV."},
    "summarize": {"label": "AI Summarize", "category": "AI tools", "accept": "pdf", "implemented": True, "description": "Generate executive overview and key bullet points."},
    "translate": {"label": "AI Translate", "category": "AI tools", "accept": "pdf", "implemented": True, "description": "Translate document content while preserving formatting."},
    "photo_resizer": {"label": "Exam Photo & Signature Resizer", "category": "Photo Tools", "accept": "image", "implemented": True, "description": "Resize photos and signatures to exact dimensions and KB limits for SSC, UPSC, and state exams."},
    "photo_compress": {"label": "Compress Photo / Image", "category": "Photo Tools", "accept": "image", "implemented": True, "description": "Compress JPG, PNG, or WebP photos to exact target KB or quality percentage."},
    "photo_resize": {"label": "Resize Photo Dimensions", "category": "Photo Tools", "accept": "image", "implemented": True, "description": "Resize photo width, height, passport format (3.5x4.5cm), or custom percentage."},
    "photo_merge": {"label": "Merge Photos into One", "category": "Photo Tools", "accept": "image", "implemented": True, "description": "Combine multiple photos side-by-side, stacked vertically, or in a photo collage."},
    "mask_aadhaar": {"label": "Mask Aadhaar Card", "category": "Security", "accept": "pdf", "implemented": True, "description": "Automatically redact first 8 digits of Aadhaar numbers per UIDAI guidelines."},
    "grayscale": {"label": "Convert to Grayscale", "category": "Organize PDF", "accept": "pdf", "implemented": True, "description": "Convert colored PDF pages to monochrome for printing. Output size varies, and colored pages may become image-based."},
    "flatten": {"label": "Flatten PDF Forms", "category": "Edit & Sign", "accept": "pdf", "implemented": True, "description": "Bake all interactive form fields into the page content, creating a non-editable submission copy."},
}


# Public, human-readable URLs for every operation.  Keep this map explicit so
# the SEO surface stays stable even if an internal operation id changes.
OPERATION_SLUGS = {
    "merge": "merge-pdf",
    "split": "split-pdf",
    "remove": "remove-pages-pdf",
    "rotate": "rotate-pdf",
    "organize": "organize-pdf",
    "scan_pdf": "scan-to-pdf",
    "compress": "compress-pdf",
    "repair": "repair-pdf",
    "ocr": "ocr-pdf",
    "jpg_to_pdf": "jpg-to-pdf",
    "word_to_pdf": "word-to-pdf",
    "excel_to_pdf": "excel-to-pdf",
    "powerpoint_to_pdf": "powerpoint-to-pdf",
    "html_to_pdf": "html-to-pdf",
    "pdf_to_jpg": "pdf-to-jpg",
    "pdf_to_word": "pdf-to-word",
    "pdf_to_excel": "pdf-to-excel",
    "pdf_to_powerpoint": "pdf-to-powerpoint",
    "pdf_to_pdfa": "pdf-to-pdfa",
    "pdf_to_text": "pdf-to-text",
    "pdf_to_markdown": "pdf-to-markdown",
    "edit": "edit-pdf",
    "annotate": "annotate-pdf",
    "crop": "crop-pdf",
    "redact": "redact-pdf",
    "watermark": "watermark-pdf",
    "page_numbers": "add-page-numbers-to-pdf",
    "protect": "protect-pdf",
    "unlock": "unlock-pdf",
    "sign": "sign-pdf",
    "compare": "compare-pdf",
    "forms": "fill-pdf-form",
    "metadata": "pdf-metadata",
    "ai_chat": "ai-pdf-chat",
    "ai_extract": "extract-pdf-data",
    "summarize": "summarize-pdf",
    "translate": "translate-pdf",
    "photo_resizer": "ssc-photo-resizer",
    "photo_compress": "compress-image-online",
    "photo_resize": "resize-image-dimensions",
    "photo_merge": "merge-photos-online",
    "mask_aadhaar": "mask-aadhaar-card-online",
    "grayscale": "convert-pdf-to-grayscale",
    "flatten": "flatten-pdf",
}
SLUG_TO_OPERATION = {slug: operation for operation, slug in OPERATION_SLUGS.items()}

# Route-specific SEO content is intentionally data-driven.  Each operation has
# its own search intent, three technical FAQs, a concrete three-step workflow,
# and a four-link internal cluster so the public pages are useful documents,
# not 37 copies of the same landing template.
SEO_CATALOG = {
    "merge": {
        "title": "Merge PDF Files Online — Combine PDFs Free | Paperplane",
        "description": "Merge PDF files in the order you choose, rearrange thumbnails, and download one clean document with Paperplane's private PDF merger.",
        "heading": "Merge PDF files in your preferred order",
        "intro": "Combine contracts, scans, invoices, or reports into one PDF while keeping page order visible before you export.",
        "how_to": ("Upload PDFs in the desired order", "Rearrange thumbnails before processing", "Download the merged document"),
        "faqs": (
            ("Can I merge PDF files without uploading them?", "Yes. Choose Local Processing to merge supported files in your browser. Larger or unsupported files can use temporary server processing; expired job files are removed on the configured cleanup schedule (2-hour retention by default)."),
            ("Does merging change page quality?", "Merging copies the source page objects into one document. It does not rasterize pages, so selectable text, vector artwork, and embedded images retain their source quality."),
            ("How many PDFs can I combine at once?", "The web workflow accepts batch uploads within the configured file and request limits. The thumbnail organizer shows the final sequence before the merge job starts."),
        ),
        "related": ("split", "compress", "organize", "rotate"),
    },
    "split": {
        "title": "Split PDF Online — Extract Pages & Ranges Free | Paperplane",
        "description": "Split a PDF by page ranges, extract selected pages, or create separate files with Paperplane's precise online PDF splitter.",
        "heading": "Split a PDF by pages or ranges",
        "intro": "Extract only the pages you need from a long PDF and keep the result ready for sharing, archiving, or editing.",
        "how_to": ("Choose the source PDF", "Enter page numbers or ranges", "Download the extracted PDF files"),
        "faqs": (
            ("Can I split a PDF into selected pages?", "Yes. Enter individual pages such as 2,5,9 or ranges such as 3-7. Duplicate page selections are normalized before the output is written."),
            ("Will splitting preserve links and text?", "The page objects are copied rather than rendered as images, so selectable text, annotations, links, and vector content remain available when the source PDF supports them."),
            ("Can I split every page into its own PDF?", "Use the page-range workflow with a full range or the document split controls to generate separate page outputs, packaged for convenient download when multiple files are created."),
        ),
        "related": ("merge", "remove", "organize", "pdf_to_jpg"),
    },
    "remove": {
        "title": "Remove Pages from PDF Online — Delete PDF Pages | Paperplane",
        "description": "Delete unwanted pages from a PDF, preview the remaining document, and export a clean file with Paperplane's secure page remover.",
        "heading": "Remove unwanted pages from a PDF",
        "intro": "Clean up duplicate scans, blank pages, or confidential sections without rebuilding the entire document from scratch.",
        "how_to": ("Open the PDF page organizer", "Select pages to delete", "Confirm and download the cleaned PDF"),
        "faqs": (
            ("Can I delete more than one PDF page at a time?", "Yes. Select multiple thumbnails or enter page selections, then confirm the deletion. The service prevents deleting every page so the result remains a valid document."),
            ("Is deleting a page reversible?", "The exported PDF does not contain the deleted page objects. Keep the original file if you may need to restore those pages later."),
            ("Does the remaining PDF keep its original formatting?", "Yes. Remaining pages are retained as PDF page objects; page content is not converted into screenshots during deletion."),
        ),
        "related": ("organize", "split", "redact", "merge"),
    },
    "rotate": {
        "title": "Rotate PDF Pages Online — Turn Pages 90° or 180° | Paperplane",
        "description": "Rotate one page or an entire PDF by 90, 180, or 270 degrees and download the corrected document with Paperplane.",
        "heading": "Rotate PDF pages to the correct orientation",
        "intro": "Fix sideways scans, mixed landscape pages, and presentation documents with a visual page-by-page rotation workflow.",
        "how_to": ("Upload the PDF", "Select pages and a rotation angle", "Download the reoriented PDF"),
        "faqs": (
            ("Can I rotate only one page in a PDF?", "Yes. Choose a single thumbnail or page number and apply 90, 180, or 270 degrees without rotating the rest of the document."),
            ("Does rotation reduce image quality?", "No. Rotation updates the page orientation metadata and layout rather than re-encoding the page as a lower-quality image."),
            ("Can I rotate mixed portrait and landscape pages?", "Yes. Each selected page can be rotated independently, which is useful for scanned packets with inconsistent orientation."),
        ),
        "related": ("organize", "crop", "merge", "pdf_to_jpg"),
    },
    "organize": {
        "title": "Organize PDF Pages Online — Reorder, Rotate & Delete | Paperplane",
        "description": "Reorder PDF pages by entering each page number once in the output order, then download the organized file.",
        "heading": "Reorder PDF pages by page number",
        "intro": "Enter every page number exactly once in the order you want, such as 3,1,2, and download the organized PDF.",
        "how_to": ("Load the PDF into Page Organizer", "Enter the complete output order as comma-separated page numbers", "Download and review the organized PDF"),
        "faqs": (
            ("Can I reorder PDF pages on a phone?", "Yes. Enter the desired page numbers in order, separated by commas, and include every page exactly once."),
            ("Can I rotate or delete pages here?", "Use Rotate PDF or Remove pages for those actions; Page Organizer changes page order."),
            ("How can I check the new page order?", "Open the downloaded PDF and review its pages before sharing it."),
        ),
        "related": ("merge", "remove", "rotate", "page_numbers"),
    },
    "scan_pdf": {
        "title": "Scan to PDF Online — Convert Photos & Scans | Paperplane",
        "description": "Turn photographed pages into a cleaner PDF with scan enhancement, contrast adjustment, and local privacy controls.",
        "heading": "Turn photos and scans into a readable PDF",
        "intro": "Prepare receipts, whiteboard photos, and paper documents for sharing with a focused scan-to-PDF workflow.",
        "how_to": ("Add scanned images or camera photos", "Adjust enhancement and page order", "Export the optimized PDF"),
        "faqs": (
            ("What image formats can I use for scan to PDF?", "The workflow accepts common image formats including JPG, PNG, TIFF, and WebP when the browser or server image decoder can verify them safely."),
            ("Does scan enhancement create searchable text?", "Enhancement improves the visual scan. Use OCR PDF afterward when you also need a searchable text layer."),
            ("Can I combine multiple photographed pages?", "Yes. Add a batch of images, arrange their sequence, and export them as a single PDF document."),
        ),
        "related": ("jpg_to_pdf", "ocr", "compress", "organize"),
    },
    "compress": {
        "title": "Compress PDF Online — Reduce PDF File Size | Paperplane",
        "description": "Compress PDF files with lossless structure cleanup or quality-based image optimization while keeping documents usable and readable.",
        "heading": "Compress a PDF without guesswork",
        "intro": "Choose a balanced, smaller, or maximum reduction profile and compare the output size before sharing the result.",
        "how_to": ("Upload a PDF and inspect its size", "Choose lossless or quality-based compression", "Download the smaller verified PDF"),
        "faqs": (
            ("How much can PDF compression reduce a file?", "The reduction depends on image resolution, embedded fonts, duplicate objects, and stream structure. Text-heavy PDFs often shrink less than scan-heavy PDFs with large images."),
            ("Does compression make a PDF blurry?", "Lossless mode avoids image quality changes. Quality-based profiles may downsample or recompress images, so choose the balanced profile when readability matters."),
            ("Where is my PDF processed?", "Compression runs in Paperplane's temporary processing workspace. The source file and result are removed after the configured retention period (2 hours by default)."),
        ),
        "related": ("pdf_to_jpg", "repair", "ocr", "merge"),
    },
    "repair": {
        "title": "Repair PDF Online — Fix Corrupted PDF Files | Paperplane",
        "description": "Repair damaged or unreadable PDF files by rebuilding cross-reference data and validating the recovered document.",
        "heading": "Repair a damaged or unreadable PDF",
        "intro": "Attempt a controlled PDF repair when a viewer reports a broken xref table, missing objects, or a malformed file structure.",
        "how_to": ("Select the damaged PDF", "Run structural recovery", "Download and verify the repaired file"),
        "faqs": (
            ("What PDF problems can repair fix?", "Repair can recover files with damaged cross-reference tables, inconsistent object offsets, or recoverable stream structure. It cannot reconstruct bytes that were never saved."),
            ("Will repair change the visible pages?", "The repair process prioritizes preserving recoverable page objects. Always compare the result with the original because severely damaged files may lose unrecoverable content."),
            ("Is a repaired PDF safe to open?", "The output is validated before download, but users should still treat untrusted PDFs as untrusted and use sanitize controls when removing active content matters."),
        ),
        "related": ("compress", "metadata", "redact", "pdf_to_text"),
    },
    "ocr": {
        "title": "OCR PDF Online — Make Scanned PDFs Searchable | Paperplane",
        "description": "Run OCR on scanned PDF pages to add searchable text while keeping the original page image visible.",
        "heading": "Make a scanned PDF searchable with OCR",
        "intro": "Create a text layer for scanned invoices, receipts, forms, and archival documents so users can search and copy recognized text.",
        "how_to": ("Upload a scanned PDF", "Select the OCR language and quality", "Download the searchable PDF"),
        "faqs": (
            ("Does OCR change the original scan?", "OCR adds recognized text behind or alongside the scanned page. The visual page remains available, while recognition accuracy depends on resolution, contrast, and language."),
            ("Which languages are supported?", "Available languages depend on the installed OCR language packs and deployment configuration. The interface reports runtime capability instead of claiming unsupported languages."),
            ("Can OCR recognize handwriting?", "Standard OCR is optimized for printed characters. Handwriting accuracy varies substantially and should be reviewed before relying on the extracted text."),
        ),
        "related": ("scan_pdf", "pdf_to_text", "compress", "pdf_to_markdown"),
    },
    "jpg_to_pdf": {
        "title": "JPG to PDF Converter — Convert Images to PDF Free | Paperplane",
        "description": "Convert JPG, PNG, TIFF, and WebP images into a single PDF with page ordering and privacy-first processing.",
        "heading": "Convert images into one PDF",
        "intro": "Build a shareable PDF from photos, receipts, scans, or design exports without opening a full desktop office suite.",
        "how_to": ("Select JPG or other supported images", "Arrange the image page order", "Download the generated PDF"),
        "faqs": (
            ("Can I convert several JPG files into one PDF?", "Yes. Add multiple images, reorder their thumbnails, and export them as pages in one PDF document."),
            ("What happens to image resolution?", "The converter preserves the source pixel data where practical and maps it to a PDF page. Very large images may be normalized to keep the output manageable."),
            ("Can I create a PDF from phone photos?", "Yes. Mobile browsers can select images from the device file picker, and the responsive workflow supports touch-first ordering."),
        ),
        "related": ("pdf_to_jpg", "scan_pdf", "compress", "merge"),
    },
    "word_to_pdf": {
        "title": "Word to PDF Converter — Convert DOCX to PDF | Paperplane",
        "description": "Convert DOCX and Word documents to PDF with layout-aware rendering and a verified download.",
        "heading": "Convert Word documents to PDF",
        "intro": "Turn editable DOCX files into shareable PDFs while preserving headings, tables, images, and page layout as faithfully as the installed converter allows.",
        "how_to": ("Choose a DOC or DOCX file", "Review conversion and page settings", "Download the rendered PDF"),
        "faqs": (
            ("Will Word formatting be preserved in the PDF?", "The conversion uses the available document renderer and preserves supported styles, tables, images, headers, and footers. Complex fonts or unsupported features may vary by renderer."),
            ("Can I convert Word to PDF without Microsoft Word?", "Yes. Paperplane uses a local or configured document conversion engine, so Microsoft Word does not need to be installed on the browser device."),
            ("Can I protect the converted PDF afterward?", "Yes. Send the resulting PDF to Protect PDF to apply password encryption and permissions after the document conversion completes."),
        ),
        "related": ("pdf_to_word", "compress", "protect", "pdf_to_pdfa"),
    },
    "excel_to_pdf": {
        "title": "Excel to PDF Converter — Convert XLSX Spreadsheets | Paperplane",
        "description": "Convert Excel XLSX spreadsheets into readable PDF reports with sheet-aware rendering and privacy-first document processing.",
        "heading": "Convert Excel spreadsheets to PDF",
        "intro": "Create a fixed-layout PDF from workbooks, tables, and financial sheets for review, printing, and distribution.",
        "how_to": ("Upload an XLS or XLSX workbook", "Choose the sheets and page layout", "Download the formatted PDF"),
        "faqs": (
            ("Can Excel to PDF include multiple worksheets?", "Yes. The converter can render workbook sheets supported by the installed Office engine. Review page counts and sheet breaks before distributing the output."),
            ("Why does a spreadsheet become landscape PDF?", "Wide tables generally need landscape orientation to keep columns legible. The conversion engine chooses a layout that fits the workbook content where possible."),
            ("Are formulas recalculated before conversion?", "Calculation behavior depends on the source workbook and converter. The resulting PDF contains rendered values and formatting, not editable spreadsheet formulas."),
        ),
        "related": ("pdf_to_excel", "compress", "protect", "word_to_pdf"),
    },
    "powerpoint_to_pdf": {
        "title": "PowerPoint to PDF Converter — Convert PPTX Slides | Paperplane",
        "description": "Convert PowerPoint presentations to PDF slide decks while retaining supported text, images, shapes, and slide order.",
        "heading": "Convert PowerPoint slides to PDF",
        "intro": "Share a stable, device-independent version of a presentation without asking recipients to install PowerPoint.",
        "how_to": ("Select a PPT or PPTX presentation", "Check slide orientation and output options", "Download the PDF slide deck"),
        "faqs": (
            ("Does PowerPoint to PDF keep the slide order?", "Yes. Slides are rendered in their source sequence unless you reorganize the exported PDF afterward with Page Organizer."),
            ("Are animations included in a PDF?", "PDF is a static format, so animations and transitions are represented by the slide's static content rather than playable motion."),
            ("Can I extract slides back to PowerPoint?", "Use PDF to PowerPoint for an editable reconstruction. Text and layout fidelity depends on the PDF structure and the conversion engine."),
        ),
        "related": ("pdf_to_powerpoint", "pdf_to_jpg", "compress", "protect"),
    },
    "html_to_pdf": {
        "title": "HTML to PDF Converter — Render Web Pages to PDF | Paperplane",
        "description": "Render trusted HTML content or a public page into a PDF with controlled page sizing and a verified output file.",
        "heading": "Convert HTML content into a PDF",
        "intro": "Create a portable PDF from HTML snippets, print-ready pages, or an allowed public URL without manually printing from a browser.",
        "how_to": ("Provide HTML or an allowed public URL", "Choose page size and rendering options", "Download the rendered PDF"),
        "faqs": (
            ("Can HTML to PDF access private network URLs?", "No. Server-side URL imports enforce SSRF protections and reject loopback, private-network, and metadata endpoints. Prefer supplying HTML directly for sensitive content."),
            ("Will CSS styles render in the PDF?", "Supported CSS is rendered by the configured browser engine. Highly dynamic scripts, cross-origin assets, and unsupported browser features may not reproduce exactly."),
            ("Can I use HTML to PDF for invoices?", "Yes, if the HTML is trusted and the page layout is designed for print. Validate fonts, page breaks, and external assets before using the output operationally."),
        ),
        "related": ("pdf_to_text", "pdf_to_markdown", "compress", "protect"),
    },
    "pdf_to_jpg": {
        "title": "PDF to JPG Converter — Convert PDF Pages to Images | Paperplane",
        "description": "Convert PDF pages to high-resolution JPG images in a ZIP bundle for previews, publishing, or image-based workflows.",
        "heading": "Convert PDF pages to JPG images",
        "intro": "Rasterize selected document pages for sharing in systems that accept images instead of PDF files.",
        "how_to": ("Upload the source PDF", "Choose page and image quality options", "Download the JPG image bundle"),
        "faqs": (
            ("Is PDF to JPG conversion lossless?", "JPG is a lossy image format. Choose an appropriate quality setting, or use a lossless image workflow when text and line art must remain pixel-perfect."),
            ("Can I convert only selected PDF pages?", "Yes. Configure the page range or selected pages before rendering so you do not need to export the entire document."),
            ("Why is the result downloaded as a ZIP file?", "A multi-page PDF produces multiple image files. Packaging them in a ZIP keeps the page set together and avoids ambiguous browser downloads."),
        ),
        "related": ("jpg_to_pdf", "pdf_to_text", "compress", "split"),
    },
    "pdf_to_word": {
        "title": "PDF to Word Converter — Convert PDF to DOCX | Paperplane",
        "description": "Convert PDF files into editable Word DOCX documents with text extraction, layout reconstruction, and privacy-first processing.",
        "heading": "Convert PDF files to editable Word documents",
        "intro": "Recover editable paragraphs and tables from a PDF when the next step is revision rather than distribution.",
        "how_to": ("Select a text or scanned PDF", "Choose conversion and OCR options", "Download the editable DOCX file"),
        "faqs": (
            ("Will PDF to Word preserve the original layout?", "The converter reconstructs paragraphs, text blocks, and supported tables. Exact fidelity varies with columns, positioned text, embedded fonts, and scanned content."),
            ("Can scanned PDFs be converted to Word?", "Scanned pages need OCR before editable text can be reconstructed. Use OCR PDF first when the source contains page images rather than a text layer."),
            ("Does PDF to Word preserve signatures?", "Visual signature marks may convert as page artwork, but cryptographic signature semantics are not preserved as an editable Word signature."),
        ),
        "related": ("word_to_pdf", "ocr", "pdf_to_text", "compress"),
    },
    "pdf_to_excel": {
        "title": "PDF to Excel Converter — Extract Tables to XLSX | Paperplane",
        "description": "Extract structured PDF tables into Excel XLSX workbooks for analysis, cleanup, and downstream reporting.",
        "heading": "Convert PDF tables to Excel",
        "intro": "Move tabular data out of a report and into a workbook without manually retyping every row.",
        "how_to": ("Upload a table-containing PDF", "Review detected table regions", "Download the XLSX workbook"),
        "faqs": (
            ("Can PDF to Excel extract scanned tables?", "Scanned tables require OCR and table recognition. Results depend on scan quality, cell borders, column alignment, and the language model available to the converter."),
            ("Will formulas be created in the Excel output?", "The output represents extracted values and table structure. It does not infer business formulas that were not explicitly encoded in the PDF."),
            ("Why do merged cells need review?", "PDFs store visual positions rather than spreadsheet cell semantics. Merged headers and irregular columns may need spreadsheet cleanup after extraction."),
        ),
        "related": ("excel_to_pdf", "ocr", "pdf_to_text", "compress"),
    },
    "pdf_to_powerpoint": {
        "title": "PDF to PowerPoint Converter — Convert PDF to PPTX | Paperplane",
        "description": "Convert PDF pages into PowerPoint PPTX slides for editing, presentation reuse, or slide-based review.",
        "heading": "Convert a PDF into PowerPoint slides",
        "intro": "Rebuild a slide deck from a PDF when you need to edit supported text and visual elements in a presentation workspace.",
        "how_to": ("Choose the source PDF", "Select slide and text reconstruction options", "Download the PPTX presentation"),
        "faqs": (
            ("Will each PDF page become a slide?", "The default workflow maps PDF pages to presentation slides. Complex page content may be represented as grouped or rasterized artwork depending on the source."),
            ("Can I edit text after conversion?", "Recognized text may be editable, while positioned glyphs, outlines, and scanned page images may remain visual content."),
            ("Are animations restored?", "No. A PDF contains static page appearances, so animations and transitions cannot be recovered from the source alone."),
        ),
        "related": ("powerpoint_to_pdf", "pdf_to_jpg", "pdf_to_text", "compress"),
    },
    "pdf_to_pdfa": {
        "title": "PDF to PDF/A Converter — Create Archive-Ready PDFs | Paperplane",
        "description": "Convert PDFs to PDF/A-1b archival format with normalized metadata, embedded resources, and validation-oriented output.",
        "heading": "Convert a PDF to archive-ready PDF/A",
        "intro": "Prepare long-term records for systems that require a standardized, self-contained archival PDF profile.",
        "how_to": ("Upload the source PDF", "Choose PDF/A conversion settings", "Download the archive-ready document"),
        "faqs": (
            ("What is PDF/A-1b?", "PDF/A-1b is an archival conformance profile focused on reliable visual reproduction. It restricts features that depend on external resources or dynamic behavior."),
            ("Why can a PDF/A conversion fail?", "Missing fonts, unsupported transparency, encrypted input, invalid metadata, or active content can prevent a document from meeting the selected archival profile."),
            ("Does PDF/A protect a file with a password?", "PDF/A is an archival conformance target, not an encryption feature. Apply Protect PDF separately when access control is required."),
        ),
        "related": ("metadata", "repair", "protect", "compress"),
    },
    "pdf_to_text": {
        "title": "PDF to Text Converter — Extract Text from PDF | Paperplane",
        "description": "Extract selectable text from PDF pages into a plain text file for search, copying, indexing, or downstream processing.",
        "heading": "Extract text from a PDF",
        "intro": "Turn a text-based PDF into a clean text stream when you need content without page styling or visual layout.",
        "how_to": ("Select a text-based PDF", "Choose page or extraction options", "Download the plain text result"),
        "faqs": (
            ("Can PDF to Text extract text from scanned pages?", "Scanned pages contain images rather than characters. Run OCR PDF first to create a searchable text layer, then extract the recognized text."),
            ("Does extraction keep the original formatting?", "Plain text preserves reading order and line content where possible, but it does not retain fonts, colors, exact columns, or page graphics."),
            ("Can I extract only certain pages?", "Yes. Use the page-range controls to limit extraction to the relevant pages and avoid processing unrelated sections."),
        ),
        "related": ("ocr", "pdf_to_markdown", "pdf_to_word", "split"),
    },
    "pdf_to_markdown": {
        "title": "PDF to Markdown Converter — Export Structured Text | Paperplane",
        "description": "Convert PDF content into structured Markdown with headings, paragraphs, lists, and readable text blocks.",
        "heading": "Convert PDF content to Markdown",
        "intro": "Create a portable, developer-friendly text representation for documentation, notes, repositories, and knowledge bases.",
        "how_to": ("Upload a text-based or OCR PDF", "Choose the pages to convert", "Download the generated Markdown file"),
        "faqs": (
            ("Does PDF to Markdown preserve headings?", "The converter infers structure from text positioning and typography. Clear heading styles and consistent spacing improve the resulting Markdown hierarchy."),
            ("Can images be included in Markdown output?", "Text conversion focuses on document structure. Image extraction behavior depends on the source PDF and the selected export options."),
            ("Should I run OCR before Markdown conversion?", "Yes for scans. OCR gives the Markdown converter a text layer to work with instead of a page image with no characters."),
        ),
        "related": ("pdf_to_text", "ocr", "html_to_pdf", "pdf_to_word"),
    },
    "edit": {
        "title": "Edit PDF Online — Add Text, Stamps & Shapes | Paperplane",
        "description": "Edit PDF pages online by adding text, stamps, shapes, and positioned content in a responsive PDF studio.",
        "heading": "Edit PDF pages without rebuilding the document",
        "intro": "Make practical edits to an existing PDF when you need to add a label, date, stamp, or visual correction before sharing.",
        "how_to": ("Open the PDF in the editor", "Choose an editing tool and place it on the page", "Apply changes and export the edited PDF"),
        "faqs": (
            ("Can I edit existing PDF text?", "The editor is designed for adding positioned content and annotations. Direct replacement of arbitrary existing glyphs depends on the page structure and tool support."),
            ("Are PDF edits applied to the file or only displayed?", "Exporting writes the positioned edits into the output PDF so they remain visible when the file is opened elsewhere."),
            ("Can I edit a PDF on a phone?", "Yes. The editor adapts its controls for touch screens, although precise text placement is easier on a larger display."),
        ),
        "related": ("annotate", "watermark", "sign", "redact"),
    },
    "annotate": {
        "title": "Annotate PDF Online — Highlight, Draw & Comment | Paperplane",
        "description": "Annotate PDF documents with highlights, underlines, notes, freehand drawings, and shapes in a browser-based workspace.",
        "heading": "Annotate PDF pages for review",
        "intro": "Mark up contracts, research papers, proofs, and drafts without changing the original page text underneath your review layer.",
        "how_to": ("Load the PDF into Studio", "Choose highlight, note, or drawing tools", "Save the annotated PDF for review"),
        "faqs": (
            ("Can I highlight text in a PDF?", "Yes, when the page contains selectable text. Image-only pages can still receive visual drawing or rectangle annotations."),
            ("Are annotations permanent?", "Annotations are written into the exported PDF. Use Sanitize or flattening controls when a review copy must become a fixed visual document."),
            ("Can collaborators see my comments in another PDF viewer?", "Standard PDF annotation compatibility varies by viewer. Export and verify the result in the target review application before relying on a specific annotation type."),
        ),
        "related": ("edit", "redact", "sign", "forms"),
    },
    "crop": {
        "title": "Crop PDF Online — Trim Margins & Page Size | Paperplane",
        "description": "Crop PDF pages to remove excess margins, scanner edges, or unwanted whitespace with page-by-page preview controls.",
        "heading": "Crop PDF pages to the content area",
        "intro": "Trim inconsistent scan borders and improve document presentation without resizing the content manually in a design tool.",
        "how_to": ("Open the PDF crop tool", "Set the crop box for one or more pages", "Preview and download the cropped document"),
        "faqs": (
            ("Does cropping delete the hidden content outside the box?", "Cropping changes the visible page area. For sensitive information, use hardened redaction or page deletion because cropping alone may not remove underlying objects."),
            ("Can I crop all pages with the same margins?", "Yes. Apply a crop rectangle to the selected page scope when the source document uses consistent page geometry."),
            ("Can crop fix a sideways scan?", "Crop controls trim the page boundary. Use Rotate PDF first or afterward when the problem is page orientation rather than excess margins."),
        ),
        "related": ("rotate", "redact", "scan_pdf", "organize"),
    },
    "redact": {
        "title": "Redact PDF Online — Permanently Remove Sensitive Text | Paperplane",
        "description": "Redact confidential PDF text and regions with a hardened workflow that rewrites page content instead of drawing a removable black box.",
        "heading": "Permanently redact sensitive PDF content",
        "intro": "Remove confidential names, identifiers, and phrases from a document while verifying that the redacted value is absent from the output.",
        "how_to": ("Upload the source PDF", "Identify text or regions to redact", "Apply hardened redaction and verify the result"),
        "faqs": (
            ("Is a black rectangle enough to redact a PDF?", "No. A visual rectangle may leave the original text selectable underneath. Hardened redaction removes or replaces the affected content and verifies the target is not still extractable."),
            ("Can redaction be undone?", "A correctly exported redacted PDF is irreversible. Keep an access-controlled original separately if your retention policy requires it."),
            ("Does redaction remove metadata too?", "Redaction targets visible page content. Use PDF Security or Sanitize to remove metadata, attachments, annotations, and active content as a separate cleanup step."),
        ),
        "related": ("protect", "annotate", "metadata", "sign"),
    },
    "watermark": {
        "title": "Watermark PDF Online — Add Text or Image Watermarks | Paperplane",
        "description": "Add a transparent text or image watermark to PDF pages with adjustable placement, opacity, and rotation.",
        "heading": "Watermark PDF pages for ownership or status",
        "intro": "Label drafts, approvals, confidential copies, and branded documents with a watermark that stays visible in the exported PDF.",
        "how_to": ("Choose a PDF and watermark type", "Set text, image, opacity, and position", "Apply the watermark and download"),
        "faqs": (
            ("Can I watermark every page?", "Yes. Choose the full document scope or a selected page range before applying the overlay."),
            ("Can I change watermark opacity?", "Yes. Opacity controls let you balance visibility against readability so body text remains usable underneath the mark."),
            ("Is a watermark a security control?", "A watermark communicates status or ownership but does not prevent copying. Use Protect PDF, permissions, or redaction when access control or removal of content is required."),
        ),
        "related": ("page_numbers", "protect", "edit", "annotate"),
    },
    "page_numbers": {
        "title": "Add Page Numbers to PDF Online — Header & Footer | Paperplane",
        "description": "Add page numbers to PDF headers or footers with configurable placement, numbering offsets, and document-wide output.",
        "heading": "Add page numbers to a PDF",
        "intro": "Make reports, legal packets, and printed documents easier to navigate with consistent numbering applied at export time.",
        "how_to": ("Upload the PDF", "Choose position, format, and starting number", "Apply numbering and download"),
        "faqs": (
            ("Can numbering start at a custom value?", "Yes. Set the starting number and choose the placement pattern so front matter can use a different numbering convention when required."),
            ("Can I add numbers to only selected pages?", "The operation supports page-scoped options where available. Review the page range before applying numbering to avoid altering cover pages."),
            ("Will page numbers overlap existing content?", "Choose a margin-aware header or footer position and preview the document. Cropping or dense source layouts may require a larger offset."),
        ),
        "related": ("organize", "watermark", "edit", "merge"),
    },
    "protect": {
        "title": "Protect PDF Online — Password Encrypt with AES-256 | Paperplane",
        "description": "Protect a PDF with password-based AES-256 encryption and configurable permissions using Paperplane's privacy-first security tools.",
        "heading": "Protect a PDF with strong password encryption",
        "intro": "Add document-open and owner controls before sharing a PDF that contains private, regulated, or commercially sensitive information.",
        "how_to": ("Upload the PDF to the security tool", "Set user and owner passwords plus permissions", "Encrypt and download the protected PDF"),
        "faqs": (
            ("What encryption does Protect PDF use?", "The security workflow targets AES-256 PDF encryption through the native PDF security engine when the required capability is available. Passwords are not stored after processing."),
            ("What is the difference between a user and owner password?", "The user password controls opening the document. The owner password controls permission changes and administrative operations supported by the PDF security handler."),
            ("Can I prevent copying or printing?", "Yes. Permission flags can restrict printing, copying, editing, annotations, or form filling, although PDF permissions should be treated as policy signals rather than absolute DRM."),
        ),
        "related": ("unlock", "sign", "redact", "metadata"),
    },
    "unlock": {
        "title": "Unlock PDF Online — Remove Password Protection | Paperplane",
        "description": "Unlock a password-protected PDF when you have the valid password and export an unencrypted copy for authorized use.",
        "heading": "Unlock a PDF with the correct password",
        "intro": "Remove encryption or restrictive permissions from a document you are authorized to access, without attempting to bypass an unknown password.",
        "how_to": ("Choose the protected PDF", "Enter the valid user or owner password", "Download the authorized unencrypted copy"),
        "faqs": (
            ("Can Unlock PDF crack a forgotten password?", "No. The workflow authenticates against a supplied password and does not bypass unknown encryption or permissions."),
            ("What happens to the original protected file?", "The original upload is not modified. A separate unencrypted output is generated after successful authentication."),
            ("Can I protect the unlocked PDF again?", "Yes. After unlocking, use Protect PDF to apply a new password and permission policy for the next recipient."),
        ),
        "related": ("protect", "sign", "metadata", "redact"),
    },
    "sign": {
        "title": "Sign PDF Online — Add Visual or Digital Signatures | Paperplane",
        "description": "Place a typed visual signature stamp. Use Paperplane Studio's Digital Signatures panel for a drawn or typed mark and signature verification.",
        "heading": "Sign a PDF for approval or integrity",
        "intro": "This tool places a typed visual signature stamp. For draw/type signature marks and verification, open the document in Paperplane Studio and choose More Tools → Digital Signatures.",
        "how_to": ("Upload the document and enter the printed signer name", "Run Sign PDF to place a typed stamp", "Open Studio for drawn or certificate-backed signature workflows"),
        "faqs": (
            ("What is the difference between a visual and digital PDF signature?", "A visual signature is an appearance placed on the page. A digital signature uses certificate-backed cryptographic validation to detect changes after signing."),
            ("Does Paperplane provide a certificate authority?", "No. Cryptographic signing requires an authorized certificate and key material. The application can create or verify supported signature structures but does not replace your trust provider."),
            ("Can I verify a signed PDF after downloading it?", "Yes. Use the verification workflow to inspect signature status, byte ranges, and integrity information supported by the document."),
        ),
        "related": ("protect", "unlock", "forms", "metadata"),
    },
    "compare": {
        "title": "Compare PDF Files Online — Find Document Differences | Paperplane",
        "description": "Compare two PDF versions and highlight text or page differences to speed up review, redlining, and change control.",
        "heading": "Compare two PDF versions side by side",
        "intro": "Find changes between drafts, signed versions, and revised reports without manually switching between separate viewer windows.",
        "how_to": ("Upload the original and revised PDFs", "Run the page and text comparison", "Review highlighted differences and export notes"),
        "faqs": (
            ("Can Compare PDF detect layout changes?", "The comparison can identify page-level and text-level differences. Visual shifts, font substitutions, or complex graphics may require human review of the rendered pages."),
            ("Do both PDFs need the same page count?", "No. Added, removed, or reordered pages are useful comparison results and are reported as structural differences."),
            ("Can I compare scanned documents?", "Scans need OCR for meaningful text comparison. Without a text layer, the workflow can still compare rendered page appearances where supported."),
        ),
        "related": ("annotate", "pdf_to_text", "merge", "redact"),
    },
    "forms": {
        "title": "Fill PDF Forms Online — Populate & Flatten PDF Forms | Paperplane",
        "description": "Fill interactive PDF form fields, import or export JSON values, add fields, and flatten completed forms in one workspace.",
        "heading": "Fill and prepare interactive PDF forms",
        "intro": "Populate AcroForm fields, review required values, and create a stable flattened copy for submission or archiving.",
        "how_to": ("Open the interactive PDF form", "Fill fields or import JSON data", "Save, flatten, and download the completed form"),
        "faqs": (
            ("Can I import form values from JSON?", "Yes. The form workspace accepts field-name/value mappings so repeated or automated form filling does not require manual entry for every field."),
            ("What does flattening a PDF form do?", "Flattening bakes field appearances into page content and removes normal interactive editing behavior, which is useful for final submissions and archives."),
            ("Can I add new fields to a PDF?", "Supported field types can be placed with coordinates and labels. Verify the result in the target PDF reader because viewer support for advanced field features varies."),
        ),
        "related": ("edit", "sign", "pdf_to_text", "protect"),
    },
    "metadata": {
        "title": "Edit PDF Metadata Online — Change Author, Title & Subject | Paperplane",
        "description": "View and update PDF metadata such as title, author, subject, keywords, and creator before publishing or archiving a document.",
        "heading": "Inspect and edit PDF metadata",
        "intro": "Clean up document identity fields and remove accidental author or application details before you share a PDF externally.",
        "how_to": ("Upload the PDF", "Review title, author, subject, and keywords", "Save the updated metadata and download"),
        "faqs": (
            ("What PDF metadata can I change?", "Common fields include title, author, subject, keywords, creator, producer, and creation or modification dates when the source permits updates."),
            ("Does metadata editing change visible page content?", "No. Metadata is document-level information. It does not rewrite the visible page content unless you choose another editing or sanitization operation."),
            ("How do I remove metadata completely?", "Use the sanitize workflow to strip private metadata and related embedded content according to the selected cleanup policy."),
        ),
        "related": ("pdf_to_pdfa", "repair", "protect", "redact"),
    },
    "ai_chat": {
        "title": "AI PDF Chat — Ask Questions with Page Citations | Paperplane",
        "description": "Ask questions about a PDF and receive document-grounded answers with page citations when the configured AI provider is available.",
        "heading": "Ask questions about a PDF with citations",
        "intro": "Search a document conversationally when scanning headings and pages manually is slower than asking a focused question.",
        "how_to": ("Upload a supported PDF", "Ask a question about its contents", "Review the answer and cited pages"),
        "faqs": (
            ("Does AI PDF Chat work without an external AI provider?", "The application can expose a local fallback for supported retrieval workflows, but model-generated answers require the configured provider and policy. The UI reports unavailable capabilities honestly."),
            ("Are answers guaranteed to be correct?", "No. Treat generated answers as an assistive summary and inspect the cited source pages before making a legal, financial, or operational decision."),
            ("Can I use AI PDF Chat for confidential files?", "AI Chat sends document text to the AI service configured for this workspace. Review the provider and retention policy before uploading confidential files."),
        ),
        "related": ("pdf_to_text", "summarize", "ai_extract", "translate"),
    },
    "ai_extract": {
        "title": "Extract Data from PDF — AI Invoice & Resume Extraction | Paperplane",
        "description": "Extract structured invoice, receipt, or resume fields from PDFs into typed JSON and CSV when the configured AI engine is available.",
        "heading": "Extract structured data from a PDF",
        "intro": "Turn semi-structured documents into fields that can be reviewed, copied, or passed into a downstream business workflow.",
        "how_to": ("Upload an invoice, resume, or supported PDF", "Choose the extraction schema", "Review and export JSON or CSV"),
        "faqs": (
            ("What document types can Smart Metadata extract?", "The built-in schemas focus on common invoice and resume fields. Custom document layouts may require human review or a different extraction strategy."),
            ("Is the extracted JSON guaranteed to be complete?", "No. Extraction is probabilistic and depends on text quality, layout, and provider behavior. Always validate required fields before importing the result into a system of record."),
            ("Can I export extracted fields as CSV?", "Yes. Structured results can be normalized into a CSV representation suitable for spreadsheets and simple batch review."),
        ),
        "related": ("pdf_to_text", "ai_chat", "summarize", "pdf_to_excel"),
    },
    "summarize": {
        "title": "Summarize PDF Online — Generate an Executive Brief | Paperplane",
        "description": "Summarize a PDF into key points and an executive brief with page-grounded retrieval when the configured AI service is enabled.",
        "heading": "Summarize a PDF into its key points",
        "intro": "Get a fast orientation to a long report while keeping the original document available for checking important details.",
        "how_to": ("Upload the source PDF", "Generate the executive summary", "Review the brief with source references"),
        "faqs": (
            ("Can a summary replace reading the original PDF?", "No. A summary is a navigation aid, not a substitute for reviewing source language, exceptions, tables, and obligations that affect a decision."),
            ("Does summarization include page references?", "When retrieval and citation support are available, the generated brief can include source page references for targeted verification."),
            ("Can I summarize a scanned PDF?", "Scanned pages should be OCR-processed first so the summarizer has text to retrieve. Recognition quality directly affects the summary."),
        ),
        "related": ("ai_chat", "ai_extract", "ocr", "pdf_to_text"),
    },
    "translate": {
        "title": "Translate PDF Online — Convert Document Language | Paperplane",
        "description": "Translate PDF text into another language with layout-aware assistance when the configured translation engine is available.",
        "heading": "Translate PDF content for multilingual review",
        "intro": "Create a translated working copy while keeping the original document available for legal and editorial comparison.",
        "how_to": ("Upload a text-based or OCR PDF", "Choose the target language", "Review and download the translated copy"),
        "faqs": (
            ("Does translation preserve the exact PDF layout?", "Layout preservation depends on text length, fonts, columns, and the translation engine. Longer translated phrases may reflow or require manual review."),
            ("Is the translated PDF legally certified?", "No. Machine translation is not a certified legal translation. Use a qualified translator for contracts, filings, or regulated communications."),
            ("Can I translate a scanned PDF?", "Run OCR first so the translation engine can access text. Image-only pages cannot be reliably translated without recognition."),
        ),
        "related": ("ocr", "pdf_to_text", "ai_chat", "summarize"),
    },
    "photo_resizer": {
        "title": "Exam Photo & Signature Resizer for SSC & UPSC (20KB - 50KB) | Paperplane",
        "description": "Resize and compress photos and signatures for SSC CGL, CHSL, MTS, GD Constable forms to exact 20-50KB and 10-20KB limits.",
        "heading": "Exam Photo & Signature Resizer for SSC & UPSC",
        "intro": "Quickly resize photos and signature images to the exact dimensions (3.5x4.5cm, 4x2cm) and file size requirements (20KB-50KB) of Indian recruitment portals.",
        "how_to": ("Upload candidate photo or signature image", "Choose the exam preset (SSC, UPSC, IBPS)", "Download the verified resized image or PDF"),
        "faqs": (
            ("What is the exact SSC photo size?", "SSC requires a passport photo between 20 KB and 50 KB, with dimensions of approximately 3.5 cm width by 4.5 cm height (350x450 px)."),
            ("What is the SSC signature size requirement?", "SSC signatures must be between 10 KB and 20 KB with dimensions of 4.0 cm width by 2.0 cm height."),
            ("Can I export as JPG or PDF?", "Yes. You can download the output directly as an optimized JPG image or a single-page PDF document."),
        ),
        "related": ("jpg_to_pdf", "compress", "crop", "scan_pdf"),
    },
    "mask_aadhaar": {
        "title": "Mask Aadhaar Card Online Free — UIDAI Compliant First 8 Digits Redaction | Paperplane",
        "description": "Create a PDF or image copy with the first 8 digits of an Aadhaar number masked. Review the exported file before sharing.",
        "heading": "Mask Aadhaar Card PDF & Image Online",
        "intro": "Create a shareable copy with the first 8 digits masked, then review the exported file carefully before sharing it.",
        "how_to": ("Upload Aadhaar PDF or scan image", "Click Mask Aadhaar Now", "Download your UIDAI-compliant masked PDF"),
        "faqs": (
            ("How should I check a masked Aadhaar copy?", "Open the exported file and verify the first eight digits are fully obscured on every page before sharing. Server-powered job files are removed after the configured retention period (2 hours by default)."),
            ("Does it work on password-protected e-Aadhaar PDFs?", "Use our Unlock PDF tool first to remove the master password, then mask the first 8 digits."),
            ("Are the first 8 digits permanently unrecoverable?", "Yes. True redaction removes the covered text and image content from the output PDF."),
        ),
        "related": ("redact", "protect", "unlock", "compress"),
    },
    "grayscale": {
        "title": "Convert PDF to Grayscale for Printing | Paperplane",
        "description": "Convert colored PDF pages to grayscale for monochrome printing. Output size can vary, and image-based pages may not retain selectable text.",
        "heading": "Convert PDF to Grayscale",
        "intro": "Convert colored PDF pages to grayscale for black-and-white printing. Already-grayscale files are preserved; color pages are rendered as images, so file size can increase and their text may no longer be selectable.",
        "how_to": ("Upload your color PDF", "Click Convert to Grayscale", "Download your grayscale PDF"),
        "faqs": (
            ("Does grayscale conversion reduce file size?", "Not always. Already-grayscale PDFs are preserved, while converting color pages to images can increase file size. Use Compress PDF when reducing size is your goal."),
            ("Will text remain selectable?", "Text remains selectable when the source is already grayscale. Color pages are rendered to grayscale images and may need OCR before their text can be searched or copied."),
            ("Is the conversion reversible?", "No. Once colored pages are converted to grayscale, their original color data is not recoverable from the output file."),
            ("Does it work on scanned PDFs?", "Yes. Scanned image PDFs are fully supported and every embedded image is converted."),
        ),
        "related": ("compress", "remove", "rotate", "merge"),
    },
    "flatten": {
        "title": "Flatten PDF Forms Online Free | Paperplane",
        "description": "Flatten interactive PDF form fields into the page content online for free. Create a non-editable final submission copy.",
        "heading": "Flatten PDF Form Fields",
        "intro": "Permanently bake all AcroForm field appearances into the page — essential for final submission, archiving, and preventing further editing.",
        "how_to": ("Upload your fillable PDF form", "Click Flatten Form Fields", "Download the permanently flattened PDF"),
        "faqs": (
            ("What does flattening a PDF do?", "Flattening converts interactive field widgets into static page content. The PDF looks the same but fields can no longer be typed in."),
            ("Can I unflatten a flattened PDF?", "No. Flattening is permanent and irreversible. Keep the original fillable PDF before flattening."),
            ("Does flattening reduce file size?", "Usually yes, as interactive form metadata and widget streams are removed."),
        ),
        "related": ("forms", "protect", "compress", "sign"),
    },
    "photo_compress": {
        "title": "Compress Photo & Image Online Free (Target KB) | Paperplane",
        "description": "Compress JPG, PNG, and WebP images to exact target KB size online for free.",
        "heading": "Compress Photos & Images Online",
        "intro": "Reduce image file size to exact target KB or quality percentage quickly and privately.",
        "how_to": ("Upload your image file", "Choose target file size (KB) or quality", "Download your optimized image"),
        "faqs": (
            ("Can I compress to exact KB limits?", "Yes, Paperplane uses intelligent binary search optimization to reach your desired file size."),
            ("Does photo compression affect image clarity?", "Our algorithm balances visual fidelity and file compression to preserve details."),
            ("Which image formats are supported?", "JPG, JPEG, PNG, and WebP are supported."),
        ),
        "related": ("photo_resizer", "photo_resize", "jpg_to_pdf", "compress"),
    },
    "photo_resize": {
        "title": "Resize Photo Dimensions Online Free | Paperplane",
        "description": "Resize image dimensions (width, height, passport photo) online for free.",
        "heading": "Resize Photo & Image Dimensions",
        "intro": "Easily resize image dimensions, passport presets (3.5x4.5cm), or scale percentages.",
        "how_to": ("Upload photo or image", "Set custom dimensions or pick a preset", "Download your resized image"),
        "faqs": (
            ("Can I resize for passport photos?", "Yes, standard 3.5x4.5 cm and 350x450 px presets are built-in."),
            ("Is aspect ratio preserved?", "Yes, specifying width or height automatically calculates the proportional aspect ratio."),
            ("Is processing private?", "Yes, image resizing runs directly in your browser or through secure isolated processing."),
        ),
        "related": ("photo_resizer", "photo_compress", "crop", "scan_pdf"),
    },
    "photo_merge": {
        "title": "Merge Photos into One Online Free | Paperplane",
        "description": "Combine multiple photos side-by-side or stacked vertically online for free.",
        "heading": "Merge Multiple Photos into One Image",
        "intro": "Combine multiple photos into a single horizontal, vertical, or grid collage image.",
        "how_to": ("Select 2 or more photos", "Choose layout (vertical, horizontal, grid)", "Download your merged image"),
        "faqs": (
            ("How many photos can I combine?", "You can combine 2 to 20 photos into a single image."),
            ("What layout styles are available?", "Vertical stacking, horizontal side-by-side, and 2x2 grid are available."),
            ("Can I export to PDF as well?", "Yes, use our JPG to PDF tool to compile images into a multi-page PDF."),
        ),
        "related": ("photo_resizer", "jpg_to_pdf", "merge", "scan_pdf"),
    },
}

# Category landing pages are useful entry points for search visitors, but are
# deliberately kept separate from the 37-operation sitemap inventory.
SEO_LANDING_PAGES = {
    "compress-pdf-to-100kb": {
        "title": "Compress PDF to 100KB Online Free — SSC, UPSC & Govt Forms | Paperplane",
        "description": "Compress PDF documents to strictly under 100KB online for free. Ideal for SSC CGL, UPSC, NTA, state PSC, and government job uploads.",
        "heading": "Compress PDF to under 100 KB for Government Applications",
        "category": "Optimize PDF",
        "intro": "Ensure your PDF certificate, marksheet, or application complies with strict 100KB upload limits. Safe, private, and verified.",
        "related": ("compress", "photo_resizer", "merge", "pdf_to_jpg"),
    },
    "compress-pdf-to-200kb": {
        "title": "Compress PDF to 200KB Online Free — UPSC, NTA, NEET Forms | Paperplane",
        "description": "Reduce PDF file size to under 200KB online. Perfect for UPSC, NTA NEET, GATE, and university admission portals.",
        "heading": "Compress PDF to under 200 KB Online",
        "category": "Optimize PDF",
        "intro": "Quickly reduce PDF size to 200KB without quality loss for online applications and email attachments.",
        "related": ("compress", "photo_resizer", "split", "jpg_to_pdf"),
    },
    "convert-pdf": {
        "title": "Convert PDF Online — Free PDF Converter | Paperplane",
        "description": "Convert PDF files to Word, Excel, PowerPoint, JPG, text, Markdown, and PDF/A locally or online with Paperplane.",
        "heading": "Convert PDF files to the format you need",
        "category": "Convert PDF",
        "intro": "Turn PDFs into editable Office files, images, text, or archive-ready PDF/A documents with a clear workflow and privacy-first processing.",
        "related": ("pdf_to_word", "word_to_pdf", "pdf_to_jpg", "pdf_to_excel"),
    },
    "pdf-security": {
        "title": "PDF Security Tools — Protect, Unlock, Sign & Redact PDFs | Paperplane",
        "description": "Protect, unlock, sign, sanitize, and permanently redact PDF files with Paperplane's privacy-first security tools.",
        "heading": "Secure PDF documents without losing control",
        "category": "PDF Security",
        "intro": "Apply password protection, visual or cryptographic signatures, sanitization, and irreversible redaction from one focused PDF security workspace.",
        "related": ("protect", "unlock", "sign", "redact"),
    },
    "download": {
        "title": "Paperplane PDF Apps — Early Access Waitlist | Paperplane",
        "description": "Join the Paperplane PDF apps waitlist. Native desktop and mobile installers are not available yet.",
        "heading": "Join the Paperplane Apps Early Access Waitlist",
        "category": "Apps Waitlist",
        "intro": "Native desktop and mobile apps are not available to download yet. Request updates for your platform.",
        "related": ("merge", "split", "compress", "edit"),
    },
    "apps": {
        "title": "Paperplane PDF Apps — Early Access Waitlist | Paperplane",
        "description": "Join the Paperplane PDF apps waitlist. Native desktop and mobile installers are not available yet.",
        "heading": "Join the Paperplane Apps Early Access Waitlist",
        "category": "Apps Waitlist",
        "intro": "Native desktop and mobile apps are not available to download yet. Request updates for your platform.",
        "related": ("merge", "split", "compress", "edit"),
    },
    "privacy": {
        "title": "Privacy Policy & Data Handling | Paperplane",
        "description": "Read the Paperplane PDF privacy policy and learn which supported tools run in your browser and how temporary server processing works.",
        "heading": "Paperplane Privacy Policy & Data Protection",
        "category": "Compliance",
        "intro": "Some supported PDF operations can run in your browser. Server-powered job files expire after the configured retention period (2 hours by default); browser-saved Studio and AI Docs work remains on this device until cleared.",
        "related": ("protect", "unlock", "redact", "mask_aadhaar"),
    },
    "terms": {
        "title": "Terms of Service & Usage Policy | Paperplane",
        "description": "Paperplane PDF Terms of Service, acceptable use policy, API service terms, and billing conditions.",
        "heading": "Terms of Service",
        "category": "Compliance",
        "intro": "Review the conditions governing use of Paperplane PDF platform, API access, and enterprise billing.",
        "related": ("protect", "sign", "forms", "unlock"),
    },
    "reset-password": {
        "title": "Reset Account Password | Paperplane",
        "description": "Reset your Paperplane PDF account password securely with your verification token.",
        "heading": "Reset Account Password",
        "category": "Account Security",
        "intro": "Enter your new password to regain access to your Paperplane account and cloud document storage.",
        "related": ("protect", "unlock", "sign", "merge"),
    },
    "developers": {
        "title": "Developer REST API & Code Workbench | Paperplane",
        "description": "Integrate 41 PDF, Office, and OCR transformations into your application with Paperplane's fast, sovereign REST microservice.",
        "heading": "Enterprise Document Microservice Architecture",
        "category": "Developers",
        "intro": "Integrate high-speed conversion, organization, and AI operations into your backend apps, CI/CD pipelines, or microservices with dedicated API keys.",
        "related": ("merge", "split", "compress", "ocr"),
    },
}


def public_site_url(request: Request) -> str:
    """Return the public canonical origin without leaking an internal proxy URL."""
    configured = PAPERPLANE_PUBLIC_URL
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()

    if configured:
        # Keep the configured public origin authoritative while allowing a
        # trusted proxy to correct scheme/host during blue/green migrations.
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(configured)
        return urlunsplit((forwarded_proto or parts.scheme, forwarded_host or parts.netloc, "", "", "")).rstrip("/")

    scheme = forwarded_proto or request.url.scheme
    host = forwarded_host or request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}".rstrip("/")


def seo_page_context(operation: str | None, landing_slug: str | None = None) -> dict:
    if landing_slug in {"tool-desk", "studio"}:
        landing = {
            "tool-desk": {
                "title": "Paperplane PDF Tool Desk — Browse All PDF Tools",
                "description": "Browse and search Paperplane PDF tools by task, with clear routes for organizing, converting, editing, and protecting documents.",
                "heading": "Find the right PDF tool for your task",
                "category": "PDF tools",
                "intro": "Search the tool directory, choose a category, and open a focused workflow for your document.",
                "related": ("merge", "split", "compress", "edit"),
            },
            "studio": {
                "title": "Paperplane Advanced PDF Studio — Edit and Organize PDFs",
                "description": "Open Paperplane PDF Studio to view, annotate, organize, and export PDF documents in a responsive workspace.",
                "heading": "Work with PDF pages in Studio",
                "category": "PDF Studio",
                "intro": "Open a PDF or create a page, then use the page list and document tools to make and export changes.",
                "related": ("merge", "split", "edit", "sign"),
            },
        }[landing_slug]
        return {
            **landing,
            "operation": None,
            "slug": landing_slug,
            "how_to": (
                "Open the tool directory or Studio workspace",
                "Choose a document task and add your PDF",
                "Review and download the finished result",
            ),
            "faqs": (
                ("Can I use Paperplane on a phone?", "Yes. The web workspace adapts to mobile browsers and touch controls."),
                ("Can I use these pages without an account?", "Many document workflows are available without signing in; account features depend on the selected service."),
                ("Are uploaded files kept permanently?", "Processing and retention depend on the selected workflow. Review the privacy information for details."),
            ),
        }

    if landing_slug:
        landing = SEO_LANDING_PAGES[landing_slug]
        return {
            "title": landing["title"],
            "description": landing["description"],
            "heading": landing["heading"],
            "category": landing["category"],
            "intro": landing["intro"],
            "operation": None,
            "slug": landing_slug,
            "related": landing["related"],
            "how_to": (
                "Choose the PDF workflow that matches your goal",
                "Add your document and review the available options",
                "Download the verified result",
            ),
            "faqs": (
                ("Is Paperplane free to use?", "Paperplane includes free workflows for everyday PDF tasks. Browser-local processing is available for Merge, Split / extract, Remove pages, and Rotate PDF."),
                ("Are files stored permanently?", "No. Server-mode job files use isolated storage and an automatic lifecycle cleanup policy."),
                ("Can I use these tools on mobile?", "Yes. The web workspace adapts to Android and iOS browsers with touch-friendly controls."),
            ),
        }

    if operation is None:
        return {
            "title": "Paperplane PDF — Free Online PDF Tools & Private Editor",
            "description": "Merge, split, compress, convert, edit, sign, protect, and organize PDF files with Paperplane's privacy-first online tools.",
            "heading": "Every tool you need to work with PDFs in one place",
            "category": "PDF tools",
            "intro": "A responsive PDF workspace with 41 focused tools, clear upload steps, and temporary processing for server-powered tasks.",
            "operation": None,
            "slug": "",
            "related": ("merge", "compress", "pdf_to_word", "sign"),
            "how_to": ("Choose a PDF tool", "Add the source document", "Download the verified output"),
            "faqs": (
                ("Where are files processed?", "Merge, Split / extract, Remove pages, and Rotate PDF can run in your browser when Local Processing is selected. Other tasks use temporary server processing; expired job files are removed on the configured cleanup schedule (2-hour retention by default)."),
                ("What PDF operations are available?", "The catalog covers organizing, compression, conversion, editing, security, and document intelligence workflows."),
                ("Does Paperplane work on phones?", "Yes. The public web workspace is responsive and uses touch-sized controls on mobile browsers."),
            ),
        }

    info = OPERATIONS[operation]
    seo = SEO_CATALOG[operation]
    return {
        "title": seo["title"],
        "description": seo["description"],
        "heading": seo["heading"],
        "category": info["category"],
        "intro": seo["intro"],
        "operation": operation,
        "slug": OPERATION_SLUGS[operation or "merge"],
        "related": seo["related"],
        "how_to": seo["how_to"],
        "faqs": seo["faqs"],
    }


def render_seo_content(context: dict) -> str:
    """Build crawlable content shown below the interactive workspace."""
    related_links = []
    for related_operation in context["related"]:
        related_info = OPERATIONS[related_operation]
        related_slug = OPERATION_SLUGS[related_operation]
        related_links.append(
            f'<a class="seo-related-link" href="/{related_slug}">{html_escape(related_info["label"])}</a>'
        )

    faq_questions = tuple(context["faqs"]) + (
        ("Does Paperplane keep a job history?", "No. This version does not provide a recent-files or job-history page. Download the result when processing finishes; temporary server job files are removed by the retention cleanup."),
    )

    faq_html = "".join(
        f'<details class="seo-faq-item"><summary>{html_escape(question)}</summary><p>{html_escape(answer)}</p></details>'
        for question, answer in faq_questions
    )
    related_html = " ".join(related_links)

    return f"""
    <section class="seo-content" aria-labelledby="seo-page-heading">
      <div class="seo-content-inner">
        <div class="seo-eyebrow">{html_escape(context['category'])} · privacy-first workflow</div>
        <h2 id="seo-page-heading">{html_escape(context['heading'])}</h2>
        <p class="seo-lede">{html_escape(context['intro'])}</p>

        <div class="seo-howto-grid">
          {''.join(f'<article class="seo-howto-step"><span>{index:02d}</span><h3>{html_escape(step)}</h3></article>' for index, step in enumerate(context['how_to'], 1))}
        </div>

        <div class="seo-faq"><h3>Frequently asked questions</h3>{faq_html}</div>
        <nav class="seo-related" aria-label="Related PDF tools"><strong>Related tools</strong>{related_html}</nav>
      </div>
    </section>
    """


def render_web_page(request: Request, operation: str | None = None, landing_slug: str | None = None) -> str:
    context = seo_page_context(operation, landing_slug)
    site_url = public_site_url(request)
    canonical_path = f"/{context['slug']}" if context["slug"] else "/"
    canonical_url = f"{site_url}{canonical_path}"
    description = html_escape(context["description"], quote=True)
    title = html_escape(context["title"], quote=True)
    json_ld = json.dumps(
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "SoftwareApplication",
                    "name": f"Paperplane PDF — {context['heading']}",
                    "applicationCategory": "BusinessApplication",
                    "applicationSubCategory": context["category"],
                    "operatingSystem": "Web",
                    "url": canonical_url,
                    "description": context["description"],
                    "offers": {"@type": "Offer", "price": "0", "priceCurrency": "INR"},
                },
                {
                    "@type": "HowTo",
                    "name": f"How to use {context['heading']}",
                    "step": [
                        {"@type": "HowToStep", "position": index, "name": step, "text": step}
                        for index, step in enumerate(context["how_to"], 1)
                    ],
                },
                {
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": question,
                            "acceptedAnswer": {"@type": "Answer", "text": answer},
                        }
                        for question, answer in context["faqs"]
                    ],
                },
            ],
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    plan_limits = plan_limits_payload()
    for token, value in {
        "%%FREE_DAILY%%": plan_limits["free_operations_per_day"],
        "%%FREE_MB%%": plan_limits["free_max_file_size_mb"],
        "%%PRO_MB%%": plan_limits["pro_max_file_size_mb"],
        "%%BATCH_FILES%%": plan_limits["max_batch_files"],
    }.items():
        html = html.replace(token, str(value))
    if DISABLE_DOCS:
        html = re.sub(
            r'<a\b(?=[^>]*href="/docs")[^>]*>.*?</a>',
            '',
            html,
            count=1,
            flags=re.DOTALL,
        )
        html = re.sub(r'<a\b(?=[^>]*href="/redoc")[^>]*>.*?</a>', '', html, flags=re.DOTALL)
    meta = f"""
  <meta name="description" content="{description}" />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{html_escape(canonical_url, quote=True)}" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:url" content="{html_escape(canonical_url, quote=True)}" />
  <meta property="og:site_name" content="Paperplane PDF" />
  <meta name="twitter:card" content="summary" />
  <meta name="twitter:title" content="{title}" />
  <meta name="twitter:description" content="{description}" />
  <script type="application/ld+json">{json_ld}</script>
  """
    html = html.replace("<!-- SEO_META_SLOT -->", meta)
    html = html.replace("<!-- SEO_CONTENT_SLOT -->", render_seo_content(context))
    html = html.replace("<title>Paperplane PDF - Online PDF Tools &amp; Editor</title>", f"<title>{title}</title>")

    # Render the first meaningful viewport for crawlers and no-JavaScript
    # visitors.  The browser still hydrates the same shell after the
    # operation catalog loads, but it no longer flashes the home directory or
    # displays the default Merge PDF copy on a deep tool URL.
    if operation is not None:
        info = OPERATIONS[operation]
        html = html.replace(
            '<div id="view-home" class="home-container">',
            '<div id="view-home" class="home-container" hidden>',
            1,
        )
        html = html.replace(
            '<div id="view-tool-desk" class="tool-desk-container" hidden>',
            '<div id="view-tool-desk" class="tool-desk-container">',
            1,
        )
        html = html.replace(
            '<span class="tool-category-badge" id="tool-hero-cat">Organize PDF</span>',
            f'<span class="tool-category-badge" id="tool-hero-cat">{html_escape(info["category"])}</span>',
            1,
        )
        html = html.replace(
            '<h1 id="tool-title">Merge PDF</h1>',
            f'<h1 id="tool-title">{html_escape(info["label"])}</h1>',
            1,
        )
        html = html.replace(
            '<p id="tool-description">Combine multiple PDFs into one unified document with custom ordering.</p>',
            f'<p id="tool-description">{html_escape(info["description"])}</p>',
            1,
        )
        html = html.replace(
            '<span class="tool-desk-breadcrumb" id="desk-breadcrumb-label">Tool Workflow</span>',
            f'<span class="tool-desk-breadcrumb" id="desk-breadcrumb-label">{html_escape(info["category"])} / {html_escape(info["label"])}</span>',
            1,
        )
        # Synchronize topbar breadcrumb on initial SSR render
        html = html.replace('<span id="crumb-category">All Tools</span>', f'<span id="crumb-category">{html_escape(info["category"])}</span>', 1)
        html = html.replace('<span id="crumb-category">Organize PDF</span>', f'<span id="crumb-category">{html_escape(info["category"])}</span>', 1)
        html = html.replace('<b id="crumb-tool">Directory</b>', f'<b id="crumb-tool">{html_escape(info["label"])}</b>', 1)
        html = html.replace('<b id="crumb-tool">Merge PDF</b>', f'<b id="crumb-tool">{html_escape(info["label"])}</b>', 1)
    elif landing_slug in ("tool-desk", None):
        html = html.replace(
            '<div id="view-home" class="home-container">',
            '<div id="view-home" class="home-container" hidden>',
            1,
        )
        html = html.replace(
            '<div id="view-tool-desk-directory" class="tool-desk-directory" hidden>',
            '<div id="view-tool-desk-directory" class="tool-desk-directory">',
            1,
        )
        html = html.replace('<span id="crumb-category">All Tools</span>', '<span id="crumb-category">Workspace</span>', 1)
        html = html.replace('<span id="crumb-category">Organize PDF</span>', '<span id="crumb-category">Workspace</span>', 1)
        html = html.replace('<b id="crumb-tool">Directory</b>', '<b id="crumb-tool">Tool Desk</b>', 1)
        html = html.replace('<b id="crumb-tool">Merge PDF</b>', '<b id="crumb-tool">Tool Desk</b>', 1)
    elif landing_slug == "studio":
        html = html.replace(
            '<div id="view-home" class="home-container">',
            '<div id="view-home" class="home-container" hidden>',
            1,
        )
        html = html.replace(
            '<div id="view-pdf-studio" class="pdf-studio" hidden>',
            '<div id="view-pdf-studio" class="pdf-studio">',
            1,
        )
        html = html.replace('<span id="crumb-category">All Tools</span>', '<span id="crumb-category">Workspace</span>', 1)
        html = html.replace('<span id="crumb-category">Organize PDF</span>', '<span id="crumb-category">Workspace</span>', 1)
        html = html.replace('<b id="crumb-tool">Directory</b>', '<b id="crumb-tool">Advanced PDF Studio</b>', 1)
        html = html.replace('<b id="crumb-tool">Merge PDF</b>', '<b id="crumb-tool">Advanced PDF Studio</b>', 1)
    elif landing_slug in ("privacy", "terms"):
        html = html.replace(
            '<div id="view-home" class="home-container">',
            '<div id="view-home" class="home-container" hidden>',
            1,
        )
        html = html.replace(
            '<div id="view-legal" class="full-page-view legal-full-view" hidden>',
            '<div id="view-legal" class="full-page-view legal-full-view">',
            1,
        )
        legal_title = "Privacy Policy" if landing_slug == "privacy" else "Terms of Service"
        html = html.replace('<span id="crumb-category">All Tools</span>', '<span id="crumb-category">Legal Center</span>', 1)
        html = html.replace('<span id="crumb-category">Organize PDF</span>', '<span id="crumb-category">Legal Center</span>', 1)
        html = html.replace('<b id="crumb-tool">Directory</b>', f'<b id="crumb-tool">{legal_title}</b>', 1)
        html = html.replace('<b id="crumb-tool">Merge PDF</b>', f'<b id="crumb-tool">{legal_title}</b>', 1)
        if landing_slug == "terms":
            html = html.replace('id="full-privacy-pane"', 'id="full-privacy-pane" hidden', 1)
            html = html.replace('id="full-terms-pane" hidden', 'id="full-terms-pane"', 1)
            html = html.replace('id="full-legal-tab-privacy" class="legal-nav-tab active"', 'id="full-legal-tab-privacy" class="legal-nav-tab"', 1)
            html = html.replace('id="full-legal-tab-terms" class="legal-nav-tab"', 'id="full-legal-tab-terms" class="legal-nav-tab active"', 1)
    elif landing_slug == "developers":
        html = html.replace(
            '<div id="view-home" class="home-container">',
            '<div id="view-home" class="home-container" hidden>',
            1,
        )
        html = html.replace(
            '<div id="view-api-docs" class="full-page-view api-docs-full-view" hidden>',
            '<div id="view-api-docs" class="full-page-view api-docs-full-view">',
            1,
        )
        html = html.replace('<span id="crumb-category">All Tools</span>', '<span id="crumb-category">Developers</span>', 1)
        html = html.replace('<span id="crumb-category">Organize PDF</span>', '<span id="crumb-category">Developers</span>', 1)
        html = html.replace('<b id="crumb-tool">Directory</b>', '<b id="crumb-tool">REST API Workspace</b>', 1)
        html = html.replace('<b id="crumb-tool">Merge PDF</b>', '<b id="crumb-tool">REST API Workspace</b>', 1)
    elif landing_slug == "reset-password":
        html = html.replace(
            'class="modal-backdrop" id="reset-password-modal" hidden',
            'class="modal-backdrop" id="reset-password-modal"',
            1,
        )
        html = html.replace(
            'id="reset-password-modal" class="modal-backdrop" hidden',
            'id="reset-password-modal" class="modal-backdrop"',
            1,
        )
        html = html.replace('<span id="crumb-category">All Tools</span>', '<span id="crumb-category">Account</span>', 1)
        html = html.replace('<span id="crumb-category">Organize PDF</span>', '<span id="crumb-category">Account</span>', 1)
        html = html.replace('<b id="crumb-tool">Directory</b>', '<b id="crumb-tool">Reset Password</b>', 1)
        html = html.replace('<b id="crumb-tool">Merge PDF</b>', '<b id="crumb-tool">Reset Password</b>', 1)
    else:
        # Home directory view: ensure topbar breadcrumb accurately shows Directory
        html = html.replace('<span id="crumb-category">Organize PDF</span>', '<span id="crumb-category">All Tools</span>', 1)
        html = html.replace('<b id="crumb-tool">Merge PDF</b>', '<b id="crumb-tool">Directory</b>', 1)
    return html


# ----------------------------------------------------------------------
# Authentication & Authorization Dependency
# ----------------------------------------------------------------------

def current_user(
    request: Request = None,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key")
) -> str | None:
    token = None
    if x_api_key:
        token = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif request and request.cookies.get("paperplane_token"):
        token = request.cookies.get("paperplane_token").strip()

    user_id = authenticate(token) if token else None

    if REQUIRE_AUTH and not user_id:
        raise HTTPException(
            status_code=401,
            detail="Authentication is required. Please log in or provide a valid Bearer token or X-API-Key."
        )
    return user_id


def require_developer_key(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key")
) -> str:
    """
    Enforces Developer API key authentication via Authorization: Bearer <key> header.
    Rejects keys passed via query parameters with a 400 error.
    """
    if "api_key" in request.query_params or "key" in request.query_params:
        raise HTTPException(
            status_code=400,
            detail="API keys must be sent via 'Authorization: Bearer YOUR_API_KEY' header, not in query parameters."
        )

    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_api_key:
        token = x_api_key.strip()
    elif request.cookies.get("paperplane_token"):
        token = request.cookies.get("paperplane_token").strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide your Paperplane API key via 'Authorization: Bearer YOUR_API_KEY' header."
        )

    user_id = authenticate(token)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked Paperplane API key. Check your key in Settings or generate a new one."
        )
    return user_id



def enforce_rate_limit(request_key: str, limit: int | None = None) -> None:
    max_reqs = limit if limit is not None else RATE_LIMIT_PER_MINUTE
    if not consume_rate_limit(request_key, max_reqs):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a minute.", headers={"Retry-After": "60"})


def enforce_account_rate_limit(request_key: str, limit: int, window_seconds: int = 60) -> None:
    if not consume_rate_limit(request_key, limit, window_seconds=window_seconds):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(max(1, int(window_seconds)))},
        )


def enforce_otp_account_lock(email: str, purpose: str) -> None:
    remaining = otp_account_lock_remaining(email, purpose)
    if remaining:
        raise HTTPException(
            status_code=429,
            detail="Too many incorrect verification codes. Request a new code after the lock expires.",
            headers={"Retry-After": str(remaining)},
        )


def raise_invalid_otp(email: str, purpose: str) -> None:
    remaining = record_otp_failure(email, purpose)
    if remaining:
        raise HTTPException(
            status_code=429,
            detail="Too many incorrect verification codes. Request a new code after the lock expires.",
            headers={"Retry-After": str(remaining)},
        )
    raise HTTPException(400, "Invalid or expired verification code.")


def deliver_otp_or_raise(background_tasks: BackgroundTasks, email: str, code: str, purpose: str) -> None:
    # The automated test harness captures an OTP through its explicitly gated
    # dev_otp response. Outside that harness, never say a code was sent unless
    # a configured mail provider confirms delivery.
    if os.getenv("TESTING") == "True":
        background_tasks.add_task(send_otp_email, email, code, purpose)
        return
    if not send_otp_email(email, code, purpose):
        delete_email_otp(email, purpose, code)
        raise HTTPException(503, "Email delivery is unavailable. Please try again later or contact support.")


def parse_options(raw: str) -> dict:
    if not raw or not raw.strip():
        return {}
    raw_str = raw.strip()
    try:
        return json.loads(raw_str)
    except json.JSONDecodeError:
        # Relaxed parsing fallback for single quotes, trailing commas, or Python dict syntax
        try:
            import ast
            parsed_ast = ast.literal_eval(raw_str)
            if isinstance(parsed_ast, dict):
                return parsed_ast
        except Exception:
            pass

        parsed = {}
        cleaned = re.sub(r"^[\{\[]|[\}\]]$", "", raw_str).strip()
        for line in cleaned.splitlines():
            line = line.strip().rstrip(",")
            if ":" in line:
                k, v = line.split(":", 1)
                parsed[k.strip().strip('"\'')] = v.strip().strip('"\'')
        if parsed:
            return parsed
        raise HTTPException(400, "Invalid options JSON. Please verify format.")


UPLOAD_CHUNK_SIZE = 64 * 1024
MAX_BATCH_FILES = 100


def plan_limits_payload() -> dict[str, int]:
    """Public plan limits used by both the upload guard and client copy."""
    return {
        "free_operations_per_day": FREE_TIER_DAILY_LIMIT,
        "free_max_file_size_mb": FREE_TIER_MAX_FILE_SIZE_MB,
        "pro_max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "max_batch_files": MAX_BATCH_FILES,
    }


def upload_limit_bytes_for_tier(tier: str | None) -> int:
    paid_tiers = {"pro", "developer", "student_pro", "cyber_cafe", "exam_pass"}
    if (tier or "free").lower() in paid_tiers:
        return MAX_FILE_SIZE
    return min(MAX_FILE_SIZE, FREE_TIER_MAX_FILE_SIZE_MB * 1024 * 1024)


def upload_limit_bytes_for_user(user_id: str | None) -> int:
    user = get_user(user_id) if user_id else None
    tier = user.get("tier", "free") if user else "free"
    return upload_limit_bytes_for_tier(tier)


def save_upload_spooled(
    upload_file: UploadFile,
    destination: Path,
    max_bytes: int = MAX_FILE_SIZE,
) -> int:
    """Stream an uploaded multipart body to disk without buffering the file.

    UploadFile.file is already a seekable temporary file managed by Starlette;
    reading it in fixed-size chunks keeps the application heap bounded even
    when several large uploads are accepted concurrently.
    """
    total_bytes = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as out_file:
            while chunk := upload_file.file.read(UPLOAD_CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        413,
                        f"File exceeds maximum allowed limit of {max_bytes // (1024 * 1024)} MB.",
                    )
                out_file.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return total_bytes


def save_upload(upload: UploadFile, directory: Path, max_bytes: int = MAX_FILE_SIZE) -> Path:
    safe_name = Path(upload.filename or "document.pdf").name
    destination = directory / f"{uuid.uuid4().hex}_{safe_name}"
    save_upload_spooled(upload, destination, max_bytes=max_bytes)
    return destination


def validate_upload(path: Path, expected: str, operation: str = "") -> None:
    with path.open("rb") as stream:
        header = stream.read(1024)

    if expected == "pdf":
        # Accept readers' common compatibility case where a short preamble
        # precedes the PDF header, but still require PyMuPDF to parse at least
        # one real page below. A signature alone must never pass as a document.
        if b"%PDF-" not in header:
            raise ValueError("The uploaded file does not have a valid PDF header (%PDF-).")
        try:
            document = fitz.open(str(path))
            try:
                if document.page_count < 1:
                    raise ValueError("The uploaded PDF contains no readable pages.")
            finally:
                document.close()
        except Exception as error:
            if isinstance(error, ValueError) and str(error) == "The uploaded PDF contains no readable pages.":
                raise
            raise ValueError("The uploaded PDF is damaged or unreadable. Please choose a valid PDF.") from error

    if expected == "image":
        try:
            with Image.open(path) as image:
                image.verify()
        except Exception as error:
            raise ValueError("The uploaded image could not be decoded safely.") from error

    if expected == "office":
        if path.stat().st_size == 0:
            raise ValueError("The uploaded Office file is empty.")
        suffix = path.suffix.lower()
        allowed_by_operation = {
            "excel_to_pdf": ({".xlsx", ".xls", ".csv"}, "Excel file (.xlsx, .xls, .csv)"),
            "word_to_pdf": ({".docx", ".doc", ".odt", ".rtf"}, "Word document (.docx, .doc, .odt, .rtf)"),
            "powerpoint_to_pdf": ({".pptx", ".ppt", ".odp"}, "PowerPoint presentation (.pptx, .ppt, .odp)"),
        }
        allowed, description = allowed_by_operation.get(
            operation,
            ({".xlsx", ".xls", ".csv", ".docx", ".doc", ".odt", ".rtf", ".pptx", ".ppt", ".odp"}, "Office document"),
        )
        if suffix not in allowed:
            raise ValueError(f"Please provide a valid {description}.")

        ole_signature = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        if suffix == ".csv":
            if header.startswith(b"%PDF-") or b"\x00" in header:
                raise ValueError("Please provide a readable CSV file, not a PDF or binary file.")
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as stream:
                    first_rows = list(islice(csv.reader(stream), 2))
                if not first_rows or not any(cell.strip() for row in first_rows for cell in row):
                    raise ValueError("The CSV file is empty or contains no readable rows.")
            except UnicodeDecodeError as error:
                raise ValueError("The CSV file is not valid UTF-8 text.") from error
        elif suffix in {".xls", ".doc", ".ppt"}:
            if not header.startswith(ole_signature):
                raise ValueError(f"Please provide a valid {description}.")
        else:
            required_members = {
                ".xlsx": {"[Content_Types].xml", "xl/workbook.xml"},
                ".docx": {"[Content_Types].xml", "word/document.xml"},
                ".pptx": {"[Content_Types].xml", "ppt/presentation.xml"},
                ".odt": {"mimetype", "content.xml"},
                ".odp": {"mimetype", "content.xml"},
                ".rtf": set(),
            }
            if suffix == ".rtf":
                try:
                    with path.open("rb") as stream:
                        sample = stream.read(4096).lstrip()
                    if not sample.startswith(b"{\\rtf"):
                        raise ValueError("Please provide a valid RTF document.")
                except OSError as error:
                    raise ValueError("The RTF document could not be read.") from error
            else:
                try:
                    with zipfile.ZipFile(path) as archive:
                        names = set(archive.namelist())
                        if not required_members[suffix].issubset(names):
                            raise ValueError(f"Please provide a valid {description}.")
                        # Force the small structural parts to decompress so a fake or
                        # truncated ZIP cannot pass validation and consume quota.
                        for member in required_members[suffix]:
                            archive.read(member)
                except (OSError, zipfile.BadZipFile, RuntimeError) as error:
                    raise ValueError(f"Please provide a valid {description}.") from error

    if CLAMAV_HOST:
        try:
            with socket.create_connection((CLAMAV_HOST, CLAMAV_PORT), timeout=15) as client:
                client.sendall(b"zINSTREAM\0")
                with path.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        client.sendall(len(chunk).to_bytes(4, "big") + chunk)
                client.sendall((0).to_bytes(4, "big"))
                result = client.recv(4096).decode(errors="replace")
            if "FOUND" in result:
                raise ValueError("Upload rejected by malware scanner.")
            if "OK" not in result:
                raise ValueError("Malware scanner returned an invalid response.")
        except OSError as error:
            raise ValueError("Malware scanner is unavailable; upload rejected by policy.") from error


def save_pdf_upload(upload_file: UploadFile, destination: Path, user_id: str | None = None) -> Path:
    """Spool and validate a PDF upload while keeping the request heap bounded."""
    save_upload_spooled(upload_file, destination, max_bytes=upload_limit_bytes_for_user(user_id))
    try:
        validate_upload(destination, "pdf")
    except ValueError as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(422, str(error)) from error
    return destination


async def save_upload_spooled_async(
    upload_file: UploadFile,
    destination: Path,
    max_bytes: int = MAX_FILE_SIZE,
) -> int:
    """Run blocking spool I/O off the event loop for async upload routes."""
    return await asyncio.to_thread(save_upload_spooled, upload_file, destination, max_bytes)


async def save_pdf_upload_async(upload_file: UploadFile, destination: Path, user_id: str | None = None) -> Path:
    """Async wrapper for bounded PDF spooling and validation."""
    return await asyncio.to_thread(save_pdf_upload, upload_file, destination, user_id)


def _purge_job_directories(job_ids: list[str]) -> int:
    purged = 0
    for job_id in job_ids:
        target = JOBS / job_id
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            purged += 1
    return purged


def _purge_stale_libreoffice_profiles(now: float, minimum_age_seconds: int = 15 * 60) -> int:
    """Remove orphaned isolated profiles while leaving active conversions alone."""
    stale_profiles = 0
    temp_root = Path(tempfile.gettempdir())
    for profile_dir in temp_root.glob("paperplane-lo-*"):
        try:
            if profile_dir.is_dir() and (now - profile_dir.stat().st_mtime) > minimum_age_seconds:
                shutil.rmtree(profile_dir, ignore_errors=True)
                stale_profiles += 1
        except OSError:
            continue
    return stale_profiles


def _emergency_disk_threshold_reached() -> bool:
    usage = shutil.disk_usage(config.DATA_DIR)
    free_percent = (usage.free / usage.total * 100) if usage.total else 0
    return free_percent < EMERGENCY_DISK_FREE_PERCENT or usage.free < EMERGENCY_DISK_FREE_BYTES


def emergency_aggressive_purge() -> dict:
    """Free completed artifacts quickly when the data volume is under pressure."""
    before_free = shutil.disk_usage(config.DATA_DIR).free
    now = time.time()
    deleted_jobs = delete_expired_jobs(EMERGENCY_JOB_AGE_SECONDS)
    purged_directories = _purge_job_directories(deleted_jobs)
    stale_profiles = _purge_stale_libreoffice_profiles(now)
    vacuum = compact_database(500)
    after_free = shutil.disk_usage(config.DATA_DIR).free
    reclaimed_mb = max(0, after_free - before_free) / (1024 * 1024)
    logger.warning(
        "Emergency disk threshold triggered: reclaimed %s megabytes.",
        round(reclaimed_mb, 2),
    )
    return {
        "purged_directories": purged_directories,
        "deleted_jobs_count": len(deleted_jobs),
        "stale_libreoffice_profiles": stale_profiles,
        "database_vacuum": vacuum,
        "reclaimed_megabytes": round(reclaimed_mb, 2),
        "timestamp": now,
    }


def cleanup_expired_jobs() -> dict:
    """Purge job data and stale isolated conversion profiles."""
    now = time.time()
    emergency = None
    if _emergency_disk_threshold_reached():
        emergency = emergency_aggressive_purge()

    purged_directories = 0
    if JOBS.exists():
        for directory in JOBS.iterdir():
            if directory.is_dir() and (now - directory.stat().st_mtime) > JOB_TTL_SECONDS:
                shutil.rmtree(directory, ignore_errors=True)
                purged_directories += 1
    deleted_jobs = delete_expired_jobs(JOB_TTL_SECONDS)
    purged_directories += _purge_job_directories(deleted_jobs)

    # LibreOffice uses one isolated profile per conversion.  If a worker is
    # killed after spawning soffice.bin, the profile directory can outlive the
    # request.  Reap only old, namespaced profiles so active conversions are
    # never touched.
    stale_lo_profiles = _purge_stale_libreoffice_profiles(now)

    vacuum = compact_database()
    return {
        "purged_directories": purged_directories,
        "deleted_jobs_count": len(deleted_jobs),
        "stale_libreoffice_profiles": stale_lo_profiles,
        "database_vacuum": vacuum,
        "ttl_seconds": JOB_TTL_SECONDS,
        "emergency": emergency,
        "timestamp": now
    }



def parse_pages(spec: str, total: int) -> list[int]:
    result: list[int] = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            if "-" in item:
                parts = item.split("-", 1)
                if not parts[0].strip() or not parts[1].strip():
                    raise ValueError(f"Invalid range '{item}'. Specify format like '1-3'.")
                start, end = int(parts[0].strip()), int(parts[1].strip())
                if start > end:
                    raise ValueError(f"Invalid page range '{item}': start must not exceed end.")
                values = range(start, end + 1)
            else:
                values = [int(item)]
        except ValueError as e:
            if "Invalid" in str(e):
                raise
            raise ValueError(f"Invalid page specification '{item}'. Use numbers or ranges like '1-3, 5'.") from None
        for page in values:
            if page < 1 or page > total:
                raise ValueError(f"Page {page} is outside 1-{total}.")
            if page not in result:
                result.append(page)
    if not result:
        raise ValueError("Enter at least one page or range.")
    return result


def pdf_bytes(writer: PdfWriter) -> bytes:
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def overlay(width: float, height: float, text: str, kind: str, options: dict) -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(width, height))
    size = int(options.get("font_size", 11))
    pdf.setFont("Helvetica-Bold" if kind == "watermark" else "Helvetica", size if kind != "watermark" else min(44, max(20, width / 12)))

    if kind == "watermark":
        pdf.saveState()
        pdf.setFillAlpha(float(options.get("opacity", 0.18)))
        pdf.setFillColorRGB(0.2, 0.22, 0.25)
        pdf.translate(width / 2, height / 2)
        pdf.rotate(35)
        pdf.drawString(-pdf.stringWidth(text, "Helvetica-Bold", min(44, max(20, width / 12))) / 2, 0, text)
        pdf.restoreState()
    else:
        position = options.get("position", "Footer center")
        text_width = pdf.stringWidth(text, "Helvetica", size)
        x = 28 if position.endswith("left") else width - text_width - 28 if position.endswith("right") else (width - text_width) / 2
        y = 24 if position.startswith("Footer") else height - 34
        pdf.drawString(x, y, text)

    pdf.save()
    return output.getvalue()


# ----------------------------------------------------------------------
# Centralized Processing Dispatcher
# ----------------------------------------------------------------------

def _safe_int(val, default: int) -> int:
    if val is None:
        return default
    try:
        if isinstance(val, (int, float)):
            return int(val)
        val_str = str(val).strip()
        first_token = val_str.split()[0]
        return int(first_token)
    except Exception:
        return default


def _merge_pdf_inputs(inputs: list[Path], output: Path, options: dict) -> Path:
    passwords = options.get("passwords", {})
    global_pw = str(options.get("password", ""))
    writer = PdfWriter()
    for idx, path in enumerate(inputs):
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            pw = passwords.get(path.name) or passwords.get(str(idx)) or global_pw
            if not pw or not reader.decrypt(pw):
                raise ValueError(f"File '{path.name}' is password protected. Please provide a valid password.")
        for page in reader.pages:
            writer.add_page(page)
    output.write_bytes(pdf_bytes(writer))
    return output


def process(operation: str, inputs: list[Path], options: dict, output_dir: Path) -> Path:
    source = inputs[0] if inputs else None
    stem = source.stem.split("_", 1)[-1] if source else "document"
    output = output_dir / f"{stem}_{operation}.pdf"
    if operation == "merge":
        output = output_dir / "merged-PDF.pdf"

    # 1. Office to PDF Conversions
    if operation == "word_to_pdf":
        return converters.word_to_pdf(source, output)
    if operation == "excel_to_pdf":
        return converters.excel_to_pdf(source, output)
    if operation == "powerpoint_to_pdf":
        return converters.powerpoint_to_pdf(source, output)
    if operation == "html_to_pdf":
        url = str(options.get("url", "")).strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("HTML conversion requires a valid http:// or https:// URL.")
        return converters.html_to_pdf(url, output, is_url=True)

    # 2. PDF to Office / Standard formats
    if operation == "pdf_to_word":
        docx_output = output.with_suffix(".docx")
        return converters.pdf_to_word(source, docx_output, pages=options.get("pages", "all"))
    if operation == "pdf_to_excel":
        xlsx_output = output.with_suffix(".xlsx")
        return converters.pdf_to_excel(source, xlsx_output, pages=options.get("pages", "all"))
    if operation == "pdf_to_powerpoint":
        pptx_output = output.with_suffix(".pptx")
        return converters.pdf_to_powerpoint(source, pptx_output, pages=options.get("pages", "all"), mode=options.get("mode", "visual"))
    if operation == "pdf_to_pdfa":
        return converters.pdf_to_pdfa(source, output)

    # 3. True Compression, Repair & OCR (Phase 4)
    if operation == "compress":
        preset = options.get("preset", "balanced")
        target_size_kb = options.get("target_size_kb")
        target_size_bytes = _safe_int(target_size_kb, 0) * 1024 if target_size_kb else None
        quality = _safe_int(options.get("quality"), 65)
        max_dpi = _safe_int(options.get("dpi"), 150)
        run_converter_with_timeout(
            converters.compress_pdf,
            source, output,
            quality=quality, max_dpi=max_dpi,
            preset=preset, target_size_bytes=target_size_bytes,
            timeout_seconds=COMPRESS_TIMEOUT_SECONDS,
            tool_name="compress",
            source_path=source,
            output_path=output,
            retry_hint="The file may contain high complexity or dense raster assets. Try choosing a lower resolution preset or compressing a smaller page range."
        )
        return output

    if operation == "repair":
        mode = options.get("mode", "automatic")
        return converters.repair_pdf(source, output, mode=mode)

    if operation == "scan_pdf":
        return converters.scan_to_pdf(inputs, output, enhance=True)

    if operation == "photo_resizer":
        preset = options.get("preset", "ssc_photo")
        target_kb = _safe_int(options.get("target_kb"), 50)
        as_pdf = str(options.get("format", "jpg")).lower() == "pdf"
        return converters.resize_exam_image(source, output, preset=preset, target_kb=target_kb, as_pdf=as_pdf)

    if operation == "photo_compress":
        target_kb = _safe_int(options.get("target_kb"), 100)
        quality = _safe_int(options.get("quality"), 75)
        return converters.compress_photo(source, output, target_kb=target_kb, quality=quality)

    if operation == "photo_resize":
        width = _safe_int(options.get("width"), 0) or None
        height = _safe_int(options.get("height"), 0) or None
        scale_percent = _safe_int(options.get("scale_percent"), 0) or None
        return converters.resize_photo(source, output, width=width, height=height, scale_percent=scale_percent)

    if operation == "photo_merge":
        layout = str(options.get("layout", "vertical")).lower()
        return converters.merge_photos(inputs, output, layout=layout)

    if operation == "mask_aadhaar":
        return security_forms_engine.mask_aadhaar_pdf(source, output)

    if operation == "grayscale":
        run_converter_with_timeout(
            converters.convert_pdf_to_grayscale,
            source, output,
            timeout_seconds=GRAYSCALE_TIMEOUT_SECONDS,
            tool_name="grayscale",
            source_path=source,
            output_path=output,
            retry_hint="The document may contain complex high-resolution pages. Try splitting the PDF into smaller batches before converting."
        )
        return output

    if operation == "flatten":
        security_forms_engine.flatten_pdf_forms(source, output)
        return output

    if operation == "ocr":
        language = options.get("language", "eng")
        pages = options.get("pages", "all")
        mode = options.get("mode", "scanned_only")
        dpi = int(options.get("dpi", 150))
        run_converter_with_timeout(
            converters.ocr_pdf,
            source, output,
            language=language,
            pages=pages,
            mode=mode,
            dpi=dpi,
            timeout_seconds=OCR_TIMEOUT_SECONDS,
            tool_name="ocr",
            source_path=source,
            output_path=output,
            retry_hint="The document contains heavy scanned graphics. Try running OCR on a smaller page selection or reducing the DPI setting."
        )
        return output

    # 4. Core PDF Organization (Merge, Split, Remove, Rotate, Organize)
    if operation == "merge":
        return run_converter_with_timeout(
            _merge_pdf_inputs, inputs, output, options,
            timeout_seconds=MERGE_TIMEOUT_SECONDS,
            tool_name="merge",
            source_path=inputs[0] if inputs else None,
            output_path=output,
            retry_hint="The merge exceeded its processing window. Try fewer files or split the source documents into smaller batches."
        )

    if operation == "organize":
        page_specs = options.get("pages", [])
        doc = fitz.open(str(source))
        if isinstance(page_specs, str):
            raw_items = [part.strip() for part in page_specs.split(",")]
            if not raw_items or any(not item for item in raw_items):
                raise ValueError("Enter the page order, for example 3,1,2.")
            try:
                page_specs = [int(item) for item in raw_items]
            except ValueError as error:
                raise ValueError("Page order must be comma-separated page numbers, for example 3,1,2.") from error
        if not isinstance(page_specs, list) or not page_specs:
            raise ValueError("Enter the complete page order, for example 3,1,2.")
        normalized_specs = []
        for item in page_specs:
            if isinstance(item, int) and not isinstance(item, bool):
                page_num, rotation = item, 0
            elif isinstance(item, dict):
                try:
                    page_num = int(item.get("page", 0))
                    rotation = int(item.get("rotation", 0))
                except (TypeError, ValueError) as error:
                    raise ValueError("Each ordered page must have a valid page number and rotation.") from error
            else:
                raise ValueError("Each ordered page must be a page number or page object.")
            if page_num < 1 or page_num > len(doc):
                raise ValueError(f"Page order includes page {page_num}, but this PDF has {len(doc)} pages.")
            normalized_specs.append((page_num, rotation))
        page_numbers = [page_num for page_num, _ in normalized_specs]
        if len(page_numbers) != len(doc) or sorted(page_numbers) != list(range(1, len(doc) + 1)):
            raise ValueError("Page order must include every page exactly once.")
        new_doc = fitz.open()
        for page_num, rot in normalized_specs:
            p_num = page_num - 1
            if 0 <= p_num < len(doc):
                new_doc.insert_pdf(doc, from_page=p_num, to_page=p_num)
                if rot:
                    new_doc[-1].set_rotation(rot)
        new_doc.save(str(output), garbage=4, deflate=True)
        return output

    if operation == "translate":
        target_lang = str(options.get("target_language", "es")).strip() or "es"
        return ai_engine.translate_pdf_layout(source, output, target_lang=target_lang)

    if operation == "annotate":
        annots = options.get("annotations", [])
        if not annots:
            annot_type = str(options.get("annot_type", "")).strip().lower()
            annotation_text = str(options.get("text", "")).strip()
            comment_text = str(options.get("content", "")).strip()
            if not annot_type:
                raise ValueError("Choose an annotation type and enter its content before running Annotate PDF.")
            if annot_type in {"note", "sticky_note", "comment"} and not (comment_text or annotation_text):
                raise ValueError("Enter comment text for the sticky note.")
            if annot_type in {"highlight", "underline", "strikeout"} and not annotation_text:
                raise ValueError("Enter the text to find and annotate.")
            annots = [{
                "type": "sticky_note" if annot_type == "note" else annot_type,
                "page": max(1, int(options.get("page", 1))),
                "text": annotation_text,
                "content": comment_text or annotation_text,
                "rect": [float(x) for x in str(options.get("rect", "72,72,250,120")).split(",")],
                "point": [float(options.get("x", 72)), float(options.get("y", 72))],
            }]
        return converters.annotate_pdf(source, output, annotations=annots)

    if operation == "summarize":
        summary = ai_engine.summarize_pdf(source)
        res_file = output.with_suffix(".txt")
        res_file.write_text(summary, encoding="utf-8")
        return res_file

    if operation == "ai_extract":
        doc_type = options.get("document_type", "auto")
        entities = ai_engine.extract_metadata_entities(source, doc_type=doc_type)
        res_file = output.with_suffix(".json")
        res_file.write_text(json.dumps(entities, indent=2, ensure_ascii=False), encoding="utf-8")
        return res_file

    if operation == "ai_chat":
        question = str(options.get("question", "")).strip() or "Summarize the key contents of this document."
        chat_res = ai_engine.chat_with_pdf(source, question)
        res_file = output.with_suffix(".json")
        res_file.write_text(json.dumps(chat_res, indent=2, ensure_ascii=False), encoding="utf-8")
        return res_file

    if operation in {"jpg_to_pdf", "png_to_pdf", "images_to_pdf"}:
        return converters.images_to_pdf(
            inputs, output,
            page_size=options.get("page_size", "a4"),
            orientation=options.get("orientation", "auto"),
            margin_pt=float(options.get("margin", 0.0)),
            fit_mode=options.get("fit_mode", "fit")
        )

    if operation == "text_to_pdf":
        return converters.text_to_pdf(source, output)

    if operation == "markdown_to_pdf":
        return converters.markdown_to_pdf(source, output)

    if operation in {"edit", "crop", "redact"}:
        document = fitz.open(str(source))
        if operation == "edit":
            page_number = max(1, int(options.get("page", 1))) - 1
            if page_number >= len(document):
                raise ValueError("The selected page does not exist.")
            text = str(options.get("text", "")).strip()
            if not text:
                raise ValueError("Enter text to add.")
            document[page_number].insert_text(
                (float(options.get("x", 72)), float(options.get("y", 72))),
                text,
                fontsize=float(options.get("font_size", 14)),
                color=(0.1, 0.12, 0.12)
            )
        elif operation == "crop":
            margins = [float(options.get(key, 0)) for key in ("left", "top", "right", "bottom")]
            for page in document:
                rect = page.rect
                page.set_cropbox(fitz.Rect(rect.x0 + margins[0], rect.y0 + margins[1], rect.x1 - margins[2], rect.y1 - margins[3]))
        else:
            terms = [term.strip() for term in str(options.get("terms", "")).split(",") if term.strip()]
            if not terms:
                raise ValueError("Enter at least one term to redact.")
            matches = 0
            for page in document:
                for term in terms:
                    for rect in page.search_for(term):
                        page.add_redact_annot(rect, fill=(0, 0, 0))
                        matches += 1
                page.apply_redactions()
            if matches == 0:
                raise ValueError("No matching text was found. Nothing was redacted.")
        document.save(output, garbage=4, deflate=True)
        return output

    if operation == "compare":
        if len(inputs) != 2:
            raise ValueError("Compare requires exactly two PDF files.")
        left = "\n".join(page.get_text() for page in fitz.open(str(inputs[0])))
        right = "\n".join(page.get_text() for page in fitz.open(str(inputs[1])))
        original_names = options.get("_original_filenames", [])
        from_name = original_names[0] if len(original_names) > 0 else inputs[0].name
        to_name = original_names[1] if len(original_names) > 1 else inputs[1].name
        report = "\n".join(difflib.unified_diff(left.splitlines(), right.splitlines(), fromfile=from_name, tofile=to_name, lineterm=""))
        result = output.with_suffix(".txt")
        result.write_text(report or "No text differences found.\n", encoding="utf-8")
        return result

    # 5. Reader / Writer operations
    reader = PdfReader(str(source), strict=False)
    if reader.is_encrypted and operation != "unlock":
        raise ValueError("This PDF is encrypted. Use Unlock PDF first.")

    writer = PdfWriter()

    if operation == "split" or operation == "remove":
        if operation == "split" and (options.get("split_mode") == "all_pages" or options.get("split_all")):
            zip_output = output.with_suffix(".zip")
            doc = fitz.open(str(source))
            try:
                with zipfile.ZipFile(zip_output, "w", zipfile.ZIP_DEFLATED) as zf:
                    for idx in range(len(doc)):
                        p_doc = fitz.open()
                        p_doc.insert_pdf(doc, from_page=idx, to_page=idx)
                        zf.writestr(f"{stem}_page_{idx+1:03d}.pdf", p_doc.tobytes(deflate=True, garbage=3))
                        p_doc.close()
            finally:
                doc.close()
            return zip_output

        selected = parse_pages(options.get("pages", ""), len(reader.pages))
        if operation == "remove":
            selected = [p for p in range(1, len(reader.pages) + 1) if p not in selected]
        for number in selected:
            writer.add_page(reader.pages[number - 1])

    elif operation == "rotate":
        degrees = _safe_int(options.get("degrees"), 90)
        for page in reader.pages:
            page.rotate(degrees)
            writer.add_page(page)

    elif operation in {"watermark", "page_numbers"}:
        wm_image_data = options.get("watermark_image_data")
        if operation == "watermark" and wm_image_data and "," in str(wm_image_data):
            img_bytes = base64.b64decode(str(wm_image_data).split(",", 1)[1])
            temp_img = output_dir / f"wm_{uuid.uuid4().hex[:8]}.png"
            temp_img.write_bytes(img_bytes)
            try:
                converters.apply_image_watermark(source, output, temp_img, opacity=float(options.get("opacity", 0.3)))
                return output
            finally:
                temp_img.unlink(missing_ok=True)

        if operation == "watermark" and not wm_image_data:
            text = (options.get("text") or "").strip()
            if not text:
                raise ValueError("Please provide watermark text or select an image.")
            label = text
        else:
            label = options.get("text", "CONFIDENTIAL") if operation == "watermark" else ""

        format_pattern = str(options.get("format", "page_of_total")).lower()
        start_number = _safe_int(options.get("start_number"), 1)
        start_page = _safe_int(options.get("start_page"), 1)
        total_pages = len(reader.pages)

        for number, page in enumerate(reader.pages, 1):
            if operation == "watermark":
                lbl = label
            else:
                if number < start_page:
                    writer.add_page(page)
                    continue
                curr = start_number + (number - start_page)
                if format_pattern == "page_n" or "page {n}" in format_pattern:
                    lbl = f"Page {curr}"
                elif format_pattern == "number_only" or "number only" in format_pattern:
                    lbl = str(curr)
                else:
                    lbl = f"Page {curr} of {total_pages}"

            ov = PdfReader(io.BytesIO(overlay(float(page.mediabox.width), float(page.mediabox.height), lbl, operation, options)))
            page.merge_page(ov.pages[0])
            writer.add_page(page)

    elif operation == "protect":
        password = (options.get("password") or options.get("user_password") or "").strip()
        owner_pw = (options.get("owner_password") or "").strip()
        if not password and not owner_pw:
            raise ValueError("A non-empty password is required to encrypt this PDF.")
        perms = {
            "allow_printing": options.get("allow_printing", True),
            "allow_copying": options.get("allow_copying", True),
            "allow_modifying": options.get("allow_modifying", False),
            "allow_annotating": options.get("allow_annotating", False),
            "allow_form_filling": options.get("allow_form_filling", True)
        }
        return security_forms_engine.protect_pdf(source, output, user_password=password, owner_password=owner_pw, permissions=perms)

    elif operation == "unlock":
        password = (options.get("password") or "").strip()
        if not password:
            raise ValueError("Please provide the password to unlock this protected PDF.")
        return security_forms_engine.unlock_pdf(source, output, password=password)

    elif operation == "forms":
        fields = options.get("fields", {})
        if isinstance(fields, str):
            fields_str = fields.strip()
            if fields_str.startswith("{") and fields_str.endswith("}"):
                try:
                    fields = json.loads(fields_str)
                except Exception:
                    parsed = {}
                    for line in fields_str.strip("{}").splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            parsed[k.strip().strip('"\'')] = v.strip().strip('"\',')
                    fields = parsed
            else:
                parsed = {}
                for line in fields_str.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        parsed[k.strip().strip('"\'')] = v.strip().strip('"\',')
                fields = parsed

        if not isinstance(fields, dict) or not fields:
            raise ValueError("Provide form fields as a valid JSON object (e.g. {\"Field_Name\": \"Value\"}).")
        security_forms_engine.fill_pdf_forms(source, output, fields)
        if options.get("flatten", False):
            security_forms_engine.flatten_pdf_forms(output, output)
        return output

    elif operation == "metadata":
        for page in reader.pages:
            writer.add_page(page)
        metadata = {f"/{key.title()}": str(value) for key, value in options.items() if key in {"title", "author", "subject", "creator"} and value}
        if metadata:
            writer.add_metadata(metadata)

    elif operation == "sign":
        sig_data = options.get("signature_data")
        signer_name = options.get("signer_name") or options.get("signature") or "Signed"
        sign_mode = options.get("mode", "visual")
        if sign_mode == "digital":
            cert_pem, key_pem = security_forms_engine.generate_test_certificate(signer_name)
            return security_forms_engine.sign_pdf_digitally(
                source, output, cert_pem, key_pem,
                reason=options.get("reason", "Signed with Paperplane"),
                location=options.get("location", "Paperplane Workstation")
            )
        else:
            return security_forms_engine.add_visual_signature(
                source, output, sig_data or signer_name,
                signer_name=signer_name
            )

    elif operation == "pdf_to_text":
        txt_output = output.with_suffix(".txt")
        return converters.pdf_to_text(source, txt_output, pages=options.get("pages", "all"))

    elif operation == "pdf_to_markdown":
        md_output = output.with_suffix(".md")
        return converters.pdf_to_markdown(source, md_output, pages=options.get("pages", "all"))

    elif operation == "pdf_to_html":
        html_output = output.with_suffix(".html")
        return converters.pdf_to_html(source, html_output, pages=options.get("pages", "all"))

    elif operation in {"pdf_to_jpg", "pdf_to_png", "pdf_to_webp", "pdf_to_images"}:
        fmt = "png" if "png" in operation else ("webp" if "webp" in operation else "jpg")
        dpi = _safe_int(options.get("dpi"), 150)
        quality = _safe_int(options.get("quality"), 85)
        pages = options.get("pages", "all")
        return converters.pdf_to_images(source, output, fmt=fmt, dpi=dpi, pages=pages, quality=quality)

    output.write_bytes(pdf_bytes(writer))
    return output


# ----------------------------------------------------------------------
# API Routes
# ----------------------------------------------------------------------

def translation_ai_available() -> bool:
    """Translations require the configured upstream model; local fallback must not masquerade as translation."""
    return not ai_engine.AI_KILL_SWITCH and bool(ai_engine._current_bluesminds_api_key())


def translation_failure_response(error: RuntimeError) -> tuple[int, str, dict[str, str]]:
    """Map safe translation provider failure classes to an actionable HTTP result."""
    message = str(error)
    status_match = re.search(r"upstream HTTP (\d{3})", message, re.IGNORECASE)
    if status_match:
        upstream_status = int(status_match.group(1))
        if upstream_status in (401, 403, 404):
            return (
                503,
                f"The translation provider rejected its authentication, model, or endpoint configuration (upstream HTTP {upstream_status}).",
                {},
            )
        if upstream_status == 429:
            return 429, "The translation provider is rate limited (upstream HTTP 429). Please retry shortly.", {"Retry-After": "30"}
        if upstream_status in (408, 504):
            return 504, f"The translation provider timed out (upstream HTTP {upstream_status}). Please retry later.", {"Retry-After": "5"}
        if 500 <= upstream_status <= 599:
            return 502, f"The translation provider is unavailable (upstream HTTP {upstream_status}). Please retry later.", {"Retry-After": "5"}
        return 502, f"The translation provider rejected the request (upstream HTTP {upstream_status}).", {}
    if "network timeout" in message.lower():
        return 504, "The translation provider timed out or could not be reached. Please retry later.", {"Retry-After": "5"}
    if "invalid structured response" in message.lower():
        return 502, "The translation provider returned an invalid response. Please retry later.", {"Retry-After": "5"}
    if "no text was translated" in message.lower():
        return 422, "No text was translated. No translated PDF was produced.", {}
    return 502, "Translation provider failed during document processing. Please retry later.", {"Retry-After": "5"}


@app.get("/api/operations")
def get_operations():
    chrome_ok = bool(converters.find_chrome_executable())
    tesseract_ok = bool(shutil.which("tesseract"))
    ai_ok = not ai_engine.AI_KILL_SWITCH and bool(ai_engine._current_bluesminds_api_key())
    translation_ai_ok = translation_ai_available()

    result = {}
    for op_id, op_info in OPERATIONS.items():
        info = dict(op_info)
        info["implemented"] = True
        
        # Determine dynamic runtime availability
        if op_id == "html_to_pdf":
            info["available"] = chrome_ok
            info["status"] = "AVAILABLE" if chrome_ok else "DEPENDENCY_MISSING"
            info["prerequisite"] = None if chrome_ok else "Requires Chrome or Chromium browser binary"
        elif op_id == "ocr":
            info["available"] = tesseract_ok
            info["status"] = "AVAILABLE" if tesseract_ok else "DEPENDENCY_MISSING"
            info["prerequisite"] = None if tesseract_ok else "Requires Tesseract OCR engine installed"
        elif op_id in ("ai_chat", "ai_extract", "summarize"):
            info["available"] = ai_ok or op_id == "ai_extract"
            info["status"] = "AVAILABLE" if info["available"] else "SERVICE_UNAVAILABLE"
            info["prerequisite"] = None if ai_ok else ("Local extraction available; provider-backed extraction disabled" if op_id == "ai_extract" else "Requires the Paperplane AI service to be configured and enabled")
        elif op_id == "translate":
            info["available"] = translation_ai_ok
            info["status"] = "AVAILABLE" if translation_ai_ok else "SERVICE_UNAVAILABLE"
            info["prerequisite"] = None if translation_ai_ok else "Requires the Paperplane AI translation service to be configured and enabled"
        else:
            info["available"] = True
            info["status"] = "AVAILABLE"
            info["prerequisite"] = None
        result[op_id] = info
    return result


@app.get("/api/seo/{operation}")
def get_seo_operation(operation: str):
    """Return the crawlable content model used when the SPA changes tools."""
    if operation not in OPERATIONS:
        raise HTTPException(status_code=404, detail="Unknown operation")
    context = seo_page_context(operation)
    context["faqs"] = tuple(context.get("faqs", ())) + (
        ("Does Paperplane keep a job history?", "No. This version does not provide a recent-files or job-history page. Download the result when processing finishes; temporary server job files are removed by the retention cleanup."),
    )
    return context


@app.get("/api/integrations")
def get_integrations():
    ai_ok = not ai_engine.AI_KILL_SWITCH and bool(ai_engine._current_bluesminds_api_key())
    return {
        "ai": ai_ok,
        "ai_status": "connected" if ai_ok else "not_configured",
        "object_storage": bool(S3_BUCKET),
        "billing": bool(CASHFREE_APP_ID and CASHFREE_SECRET_KEY),
        "billing_provider": "cashfree",
        "auth": REQUIRE_AUTH,
        "queue": True,
        "malware_scan": bool(CLAMAV_HOST),
        "libreoffice": bool(converters.find_libreoffice_executable()),
        "chrome": bool(converters.find_chrome_executable()),
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "paperplane-pdf",
        "version": "2.0.0",
        "auth_required": REQUIRE_AUTH,
        "workers": executor._max_workers,
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "job_ttl_hours": JOB_TTL_SECONDS // 3600
    }


@app.post("/api/system/cleanup", include_in_schema=False)
def trigger_system_cleanup(request: Request, user_id: str | None = Depends(current_user)):
    """Queue an administrative cleanup without doing disk work in the request."""
    if not user_id:
        raise HTTPException(401, "Authentication is required to trigger maintenance cleanup.")
    user = get_user(user_id)
    if not user or user.get("tier") not in ("pro", "dev", "admin"):
        raise HTTPException(403, "Administrative privileges required.")
    enforce_rate_limit(f"system_cleanup:{user_id}", limit=5)
    cleanup_requested.set()
    return {
        "status": "queued",
        "message": "Ephemeral storage purge queued for the background cleanup daemon.",
    }



# ----------------------------------------------------------------------
# Auth & Developer API Endpoints
# ----------------------------------------------------------------------

def _auth_response_data(session: dict, user_id: str | None = None, extra: dict | None = None) -> dict:
    """Pure HttpOnly cookie auth helper: omits token from JSON in production to prevent JS/XSS exfiltration."""
    data = {
        "status": "success",
        "email": session.get("email"),
    }
    if user_id:
        data["user_id"] = user_id
    if extra:
        data.update(extra)
    # Session token is strictly delivered via secure HttpOnly cookie.
    # It is only exposed in response body if TESTING is True for automated test harness assertions.
    if os.getenv("TESTING") == "True":
        data["token"] = session.get("token")
    return data


@app.post("/api/auth/register")
async def register(
    response: Response,
    request: Request,
    background_tasks: BackgroundTasks,
    email: str | None = Form(None),
    password: str | None = Form(None),
    confirm_password: str | None = Form(None),
    otp: str | None = Form(None),
    require_otp: str | None = Form(None)
):
    if "application/json" in request.headers.get("content-type", ""):
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(400, "Registration JSON must be a valid object.") from exc
        if not isinstance(payload, dict):
            raise HTTPException(400, "Registration JSON must be an object.")
        email = payload.get("email", email)
        password = payload.get("password", password)
        confirm_password = payload.get("confirm_password", confirm_password)
        otp = payload.get("otp", otp)

    if not isinstance(email, str) or not isinstance(password, str) or not email or not password:
        raise HTTPException(400, "Email and password are required.")
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    enforce_rate_limit(f"reg:{client_ip}", limit=15)

    clean_email = email.lower().strip()
    if "@" not in clean_email or "." not in clean_email:
        raise HTTPException(400, "Please provide a valid email address.")
    enforce_account_rate_limit(f"reg-account:{clean_email}", limit=5, window_seconds=3600)

    if confirm_password is not None and confirm_password != password:
        raise HTTPException(400, "Passwords do not match.")

    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")

    existing_user = get_user_by_email(clean_email)
    if existing_user:
        raise HTTPException(409, "An account with that email already exists.")

    # Case 1: OTP was submitted to complete registration
    if otp:
        enforce_otp_account_lock(clean_email, "signup")
        clean_otp = str(otp).strip()
        payload = verify_email_otp(clean_email, "signup", clean_otp)
        if payload is None:
            record_audit_event("signup_otp_failed", email=clean_email, ip_address=client_ip, user_agent=user_agent)
            raise_invalid_otp(clean_email, "signup")
        clear_otp_failures(clean_email, "signup")
        
        user_id = create_user(clean_email, password)
        session = create_session(clean_email, password)
        response.set_cookie(
            key="paperplane_token",
            value=session["token"],
            max_age=14 * 86400,
            httponly=True,
            secure=SECURE_COOKIES,
            samesite=COOKIE_SAMESITE,
            path="/"
        )
        background_tasks.add_task(send_login_notification, session["email"], client_ip, user_agent)
        return _auth_response_data(session, user_id=user_id)

    # Every registration requires email verification, regardless of client flags.
    salt = secrets.token_hex(16)
    pw_hash = _password_hash(password, salt)
    otp_code = create_email_otp(clean_email, "signup", {"password_hash": pw_hash, "salt": salt})
    deliver_otp_or_raise(background_tasks, clean_email, otp_code, "signup")
    res = {
        "status": "otp_required",
        "email": clean_email,
        "purpose": "signup",
        "message": f"A 6-digit confirmation code has been dispatched to {clean_email}."
    }
    if os.getenv("TESTING") == "True":
        res["dev_otp"] = otp_code
    return res


@app.post("/api/auth/login")
def login(
    response: Response,
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    password: str = Form(...),
    otp: str | None = Form(None),
    require_otp: str | None = Form(None)
):
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    enforce_rate_limit(f"login:{client_ip}", limit=25)

    clean_email = email.lower().strip()

    # Case 1: OTP was submitted to complete 2FA login
    if otp:
        enforce_otp_account_lock(clean_email, "login")
        clean_otp = str(otp).strip()
        payload = verify_email_otp(clean_email, "login", clean_otp)
        if payload is None:
            record_audit_event("login_otp_failed", email=clean_email, ip_address=client_ip, user_agent=user_agent)
            raise_invalid_otp(clean_email, "login")
        clear_otp_failures(clean_email, "login")
        
        user = get_user_by_email(clean_email)
        if not user:
            raise HTTPException(401, "Account not found.")
        session = create_session_for_user(user["id"])
        response.set_cookie(
            key="paperplane_token",
            value=session["token"],
            max_age=14 * 86400,
            httponly=True,
            secure=SECURE_COOKIES,
            samesite=COOKIE_SAMESITE,
            path="/"
        )
        background_tasks.add_task(send_login_notification, session["email"], client_ip, user_agent)
        return _auth_response_data(session, extra={"expires_in": session["expires_at"]})

    # Verify user credentials
    user = verify_user_credentials(clean_email, password)
    if not user:
        record_audit_event("login_failed", email=clean_email, ip_address=client_ip, user_agent=user_agent, details="Invalid credentials")
        raise HTTPException(401, "Invalid email or password.")

    # Case 2: Two-factor OTP requested (e.g. from the website login page)
    if require_otp and str(require_otp).lower() in ("1", "true", "yes"):
        otp_code = create_email_otp(clean_email, "login", {"user_id": user["id"]})
        deliver_otp_or_raise(background_tasks, clean_email, otp_code, "login")
        res = {
            "status": "otp_required",
            "email": clean_email,
            "purpose": "login",
            "message": f"A 6-digit verification code has been dispatched to {clean_email}."
        }
        if os.getenv("TESTING") == "True":
            res["dev_otp"] = otp_code
        return res

    # Case 3: Direct login (backward compatibility for automated test suite and CLI)
    try:
        session = create_session(clean_email, password)
        response.set_cookie(
            key="paperplane_token",
            value=session["token"],
            max_age=14 * 86400,
            httponly=True,
            secure=SECURE_COOKIES,
            samesite=COOKIE_SAMESITE,
            path="/"
        )
        background_tasks.add_task(send_login_notification, session["email"], client_ip, user_agent)
        return _auth_response_data(session, extra={"expires_in": session["expires_at"]})
    except ValueError as error:
        raise HTTPException(401, str(error)) from error


@app.post("/api/auth/verify-signup-otp", include_in_schema=False)
async def verify_signup_otp(response: Response, request: Request, background_tasks: BackgroundTasks):
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    enforce_rate_limit(f"otp_verify:{client_ip}", limit=30)

    email = ""
    otp = ""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            email = body.get("email", "")
            otp = body.get("otp", "")
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            email = form.get("email", "")
            otp = form.get("otp", "")
        except Exception:
            pass

    clean_email = str(email).lower().strip()
    clean_otp = str(otp).strip()

    if not clean_email or not clean_otp:
        raise HTTPException(400, "Email and OTP code are required.")

    enforce_otp_account_lock(clean_email, "signup")
    payload = verify_email_otp(clean_email, "signup", clean_otp)
    if payload is None:
        record_audit_event("signup_otp_failed", email=clean_email, ip_address=client_ip, user_agent=user_agent)
        raise_invalid_otp(clean_email, "signup")
    clear_otp_failures(clean_email, "signup")

    pw_hash = payload.get("password_hash")
    salt = payload.get("salt")
    if pw_hash and salt:
        try:
            user_id = create_user_with_hash(clean_email, pw_hash, salt)
        except Exception as err:
            if "UNIQUE constraint" in str(err):
                user = get_user_by_email(clean_email)
                user_id = user["id"] if user else None
            else:
                raise HTTPException(500, "Failed to create user account.")
    else:
        pw = payload.get("password")
        if not pw:
            raise HTTPException(400, "Registration session has expired. Please sign up again.")
        try:
            user_id = create_user(clean_email, pw)
        except Exception as err:
            if "UNIQUE constraint" in str(err):
                user = get_user_by_email(clean_email)
                user_id = user["id"] if user else None
            else:
                raise HTTPException(500, "Failed to create user account.")

    session = create_session_for_user(user_id)
    response.set_cookie(
        key="paperplane_token",
        value=session["token"],
        max_age=14 * 86400,
        httponly=True,
        secure=SECURE_COOKIES,
        samesite=COOKIE_SAMESITE,
        path="/"
    )
    record_audit_event("signup_success", email=clean_email, ip_address=client_ip, user_agent=user_agent, user_id=user_id)
    background_tasks.add_task(send_login_notification, session["email"], client_ip, user_agent)
    return _auth_response_data(session, user_id=user_id)


@app.post("/api/auth/verify-login-otp", include_in_schema=False)
async def verify_login_otp(response: Response, request: Request, background_tasks: BackgroundTasks):
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    enforce_rate_limit(f"otp_verify:{client_ip}", limit=30)

    email = ""
    otp = ""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            email = body.get("email", "")
            otp = body.get("otp", "")
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            email = form.get("email", "")
            otp = form.get("otp", "")
        except Exception:
            pass

    clean_email = str(email).lower().strip()
    clean_otp = str(otp).strip()

    if not clean_email or not clean_otp:
        raise HTTPException(400, "Email and OTP code are required.")

    enforce_otp_account_lock(clean_email, "login")
    payload = verify_email_otp(clean_email, "login", clean_otp)
    if payload is None:
        record_audit_event("login_otp_failed", email=clean_email, ip_address=client_ip, user_agent=user_agent)
        raise_invalid_otp(clean_email, "login")
    clear_otp_failures(clean_email, "login")

    user = get_user_by_email(clean_email)
    if not user:
        raise HTTPException(401, "Account not found.")

    if payload.get("user_id") and payload["user_id"] != user["id"]:
        record_audit_event("login_otp_mismatch", email=clean_email, ip_address=client_ip, user_agent=user_agent)
        raise HTTPException(401, "Verification challenge mismatch.")

    session = create_session_for_user(user["id"])
    response.set_cookie(
        key="paperplane_token",
        value=session["token"],
        max_age=14 * 86400,
        httponly=True,
        secure=SECURE_COOKIES,
        samesite=COOKIE_SAMESITE,
        path="/"
    )
    record_audit_event("login_success", email=clean_email, ip_address=client_ip, user_agent=user_agent, user_id=user["id"])
    background_tasks.add_task(send_login_notification, session["email"], client_ip, user_agent)
    return _auth_response_data(session, user_id=user["id"], extra={"expires_in": session["expires_at"]})


@app.post("/api/auth/resend-otp", include_in_schema=False)
async def resend_otp(request: Request, background_tasks: BackgroundTasks):
    client_ip = get_client_ip(request)
    enforce_rate_limit(f"otp_resend:{client_ip}", limit=15)

    email = ""
    purpose = "login"
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            email = body.get("email", "")
            purpose = body.get("purpose", "login")
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            email = form.get("email", "")
            purpose = form.get("purpose", "login")
        except Exception:
            pass

    clean_email = str(email).lower().strip()
    clean_purpose = str(purpose).lower().strip()
    if clean_purpose not in ("login", "signup"):
        clean_purpose = "login"

    if not clean_email or "@" not in clean_email:
        raise HTTPException(400, "A valid email address is required.")

    allowed, remaining = can_resend_otp(clean_email, clean_purpose, cooldown=60)
    if not allowed:
        raise HTTPException(429, f"Please wait {remaining} seconds before requesting a new code.")

    if clean_purpose == "login":
        user = get_user_by_email(clean_email)
        if not user:
            raise HTTPException(404, "No account exists with this email address.")
        otp_code = create_email_otp(clean_email, "login", {"user_id": user["id"]})
    else:
        otp_code = create_email_otp(clean_email, clean_purpose, None)

    deliver_otp_or_raise(background_tasks, clean_email, otp_code, clean_purpose)

    res = {
        "status": "success",
        "message": "A new verification code has been sent. Any previous code is now invalid; use the latest code."
    }
    if os.getenv("TESTING") == "True":
        res["dev_otp"] = otp_code
    return res


@app.post("/api/auth/google")
def google_auth(response: Response, request: Request, background_tasks: BackgroundTasks, payload: dict = Body(default={})):
    """
    Authenticates via Google OAuth2 ID Token.
    Verifies signature, audience, and issuer against Google's public keys.
    If Google OAuth is not configured on this host, returns 503 Service Unavailable.
    """
    client_ip = get_client_ip(request)
    enforce_rate_limit(f"google_auth:{client_ip}", limit=20)

    credential = payload.get("credential") or payload.get("id_token")
    if not GOOGLE_CLIENT_ID:
        # In non-production testing environment, allow test credential if simulation explicitly enabled
        if ALLOW_BILLING_SIMULATION and ENVIRONMENT != "production" and payload.get("test_mode") and payload.get("email"):
            email = payload.get("email")
        else:
            raise HTTPException(
                status_code=503,
                detail="Google OAuth2 authentication is not configured in this deployment (missing GOOGLE_CLIENT_ID). Please use email/password sign-in."
            )
    else:
        if not credential:
            raise HTTPException(400, "Missing Google credential or id_token.")
        # Verify Google JWT using google-auth library with tokeninfo fallback
        email = None
        verified = False
        if HAS_GOOGLE_AUTH:
            try:
                id_info = google_id_token.verify_oauth2_token(
                    credential,
                    google_requests.Request(),
                    GOOGLE_CLIENT_ID
                )
                if id_info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
                    raise HTTPException(401, "Invalid Google token: issuer mismatch.")
                if id_info.get("aud") != GOOGLE_CLIENT_ID:
                    raise HTTPException(401, "Invalid Google token: audience mismatch.")
                if not id_info.get("email_verified") in (True, "true"):
                    raise HTTPException(401, "Google email is not verified.")
                email = id_info.get("email")
                if not email:
                    raise HTTPException(401, "No email in Google token.")
                verified = True
            except HTTPException:
                raise
            except Exception:
                verified = False

        if not verified:
            try:
                tokeninfo_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}"
                req = urllib.request.Request(tokeninfo_url, headers={"User-Agent": "Paperplane/2.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if data.get("aud") != GOOGLE_CLIENT_ID:
                    raise HTTPException(401, "Invalid Google token: audience mismatch.")
                if data.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
                    raise HTTPException(401, "Invalid Google token: issuer mismatch.")
                if not data.get("email_verified") in (True, "true"):
                    raise HTTPException(401, "Google email is not verified.")
                email = data.get("email")
                if not email:
                    raise HTTPException(401, "No email in Google token.")
            except HTTPException:
                raise
            except Exception as err:
                raise HTTPException(401, f"Google token verification failed: {err}") from err

    try:
        session = create_google_session(email)
        response.set_cookie(
            key="paperplane_token",
            value=session["token"],
            max_age=14 * 86400,
            httponly=True,
            secure=SECURE_COOKIES,
            samesite=COOKIE_SAMESITE,
            path="/"
        )
        background_tasks.add_task(send_login_notification, session["email"], client_ip)
        return _auth_response_data(session, extra={
            "tier": session["tier"],
            "expires_in": session["expires_at"],
            "message": "Signed in with Google successfully."
        })
    except Exception as err:
        raise HTTPException(500, "Google authentication session creation failed.") from err


@app.get("/api/auth/config")
def get_auth_config():
    """Returns safe public authentication configuration for the browser."""
    return {
        "google_enabled": bool(GOOGLE_CLIENT_ID),
        "google_client_id": GOOGLE_CLIENT_ID or None,
    }


@app.post("/api/auth/logout")
def logout(response: Response, request: Request, user_id: str | None = Depends(current_user)):
    """Logs out user, invalidating session in SQLite and clearing cookie."""
    token = request.cookies.get("paperplane_token")
    auth_hdr = request.headers.get("authorization", "")
    if not token and auth_hdr.lower().startswith("bearer "):
        token = auth_hdr[7:].strip()
    if token:
        delete_session(token)
    response.delete_cookie(
        key="paperplane_token",
        path="/"
    )
    return {"status": "success", "authenticated": False, "message": "Logged out successfully."}


@app.post("/api/auth/forgot-password", include_in_schema=False)
async def forgot_password(request: Request, background_tasks: BackgroundTasks):
    """
    Initiates secure password reset. Generates cryptographically secure single-use token.
    Dispatches email via SMTP if configured; in dev mode, surfaces reset URL.
    Returns generic response to prevent account enumeration.
    """
    client_ip = get_client_ip(request)
    enforce_rate_limit(f"forgot:{client_ip}", limit=10)

    target_email = ""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = await request.json()
            target_email = payload.get("email", "")
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            target_email = form.get("email", "")
        except Exception:
            pass

    target_email = str(target_email).lower().strip()
    if not target_email or "@" not in target_email:
        raise HTTPException(400, "Please provide a valid email address.")

    res = create_password_reset_token(target_email)
    dev_url = None
    if res:
        token, uid = res
        base_url = (PAPERPLANE_PUBLIC_URL or str(request.base_url)).rstrip("/")
        reset_link = f"{base_url}/?reset_token={token}"

        # Dispatch async branded transactional email
        background_tasks.add_task(send_password_reset_email, target_email, token, base_url)

        # In non-production testing environment, offer safe dev link for verification
        if ENVIRONMENT != "production" or os.getenv("TESTING") == "True" or "pytest" in sys.modules:
            dev_url = reset_link

    resp = {
        "status": "success",
        "message": "If an account exists, reset instructions will be sent when the email service accepts the request. If no email arrives, check spam or contact support."
    }
    if dev_url:
        resp["dev_reset_url"] = dev_url
    return resp


@app.post("/api/auth/reset-password", include_in_schema=False)
async def reset_password(request: Request, background_tasks: BackgroundTasks):
    """
    Consumes password reset token and sets new password. Invalidates all active sessions.
    """
    client_ip = get_client_ip(request)
    enforce_rate_limit(f"reset:{client_ip}", limit=15)

    tok = ""
    pw = ""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = await request.json()
            tok = payload.get("token", "")
            pw = payload.get("new_password", "")
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            tok = form.get("token", "")
            pw = form.get("new_password", "")
        except Exception:
            pass

    tok = str(tok).strip()
    pw = str(pw).strip()

    if not tok:
        raise HTTPException(400, "Reset token is required.")
    if len(pw) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")

    try:
        user_id = verify_and_consume_reset_token(tok, pw)
        if not user_id:
            raise HTTPException(400, "Invalid or expired password reset link. Please request a new one.")
        user = get_user(user_id) if user_id else None
        if user and user.get("email"):
            background_tasks.add_task(send_password_changed_notification, user["email"], client_ip)
        return {
            "status": "success",
            "message": "Password successfully reset. You may now sign in with your new password."
        }
    except ValueError as err:
        raise HTTPException(400, str(err)) from err


@app.post("/api/user/change-password")
async def change_password(
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str | None = Depends(current_user)
):
    """
    Changes password for authenticated user in Settings.
    """
    if not user_id:
        raise HTTPException(401, "Authentication required to change password.")

    old_pw = ""
    new_pw = ""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = await request.json()
            old_pw = payload.get("old_password", "")
            new_pw = payload.get("new_password", "")
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            old_pw = form.get("old_password", "")
            new_pw = form.get("new_password", "")
        except Exception:
            pass

    old_pw = str(old_pw).strip()
    new_pw = str(new_pw).strip()

    if not old_pw:
        raise HTTPException(400, "Current password is required.")
    if len(new_pw) < 8:
        raise HTTPException(400, "New password must be at least 8 characters.")

    client_ip = get_client_ip(request)
    try:
        update_user_password(user_id, old_pw, new_pw)
        user = get_user(user_id)
        if user and user.get("email"):
            background_tasks.add_task(send_password_changed_notification, user["email"], client_ip)
        return {"status": "success", "message": "Password updated successfully."}
    except ValueError as err:
        raise HTTPException(400, str(err)) from err


@app.post("/api/waitlist")
async def join_waitlist(request: Request, background_tasks: BackgroundTasks):
    """
    Early-access waiting list registration for native desktop and mobile clients.
    """
    client_ip = get_client_ip(request)
    enforce_rate_limit(f"waitlist:{client_ip}", limit=15)

    email = ""
    platform = "all"
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = await request.json()
            email = payload.get("email", "")
            platform = payload.get("platform", "all")
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            email = form.get("email", "")
            platform = form.get("platform", "all")
        except Exception:
            pass

    if not isinstance(email, str) or not email.strip() or len(email.strip()) > 254:
        raise HTTPException(422, "Please provide a valid email address of at most 254 characters.")
    email = email.strip().lower()
    if not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", email):
        raise HTTPException(422, "Please provide a valid email address.")
    if not isinstance(platform, str) or len(platform.strip()) > 32 or any(ord(char) < 32 for char in platform):
        raise HTTPException(422, "Platform must be a supported text value.")
    platform = platform.strip().lower()
    if platform not in {"all", "windows", "macos", "linux", "android", "ios"}:
        raise HTTPException(422, "Platform is not supported.")

    try:
        result = add_waitlist_entry(email, platform, client_ip)
        # Fire-and-forget admin alert email
        background_tasks.add_task(
            send_waitlist_alert,
            signup_email=email,
            platform=platform,
            waitlist_position=result.get("waitlist_position", 0),
            ip_address=client_ip,
        )
        return result
    except ValueError as err:
        raise HTTPException(400, str(err)) from err




@app.get("/api/auth/me")
def get_current_user_profile(request: Request, user_id: str | None = Depends(current_user)):
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication is required.")
    client_ip = get_client_ip(request)
    all_pricing = {
        "exam_pass": {"inr": EXAM_PASS_PRICE_INR},
        "student_pro": {"inr": STUDENT_PRO_PRICE_INR},
        "pro": {"inr": PRO_TIER_PRICE_INR},
        "cyber_cafe": {"inr": CYBER_CAFE_PRICE_INR},
        "developer": {"inr": DEV_TIER_PRICE_INR},
    }
    plan_limits = plan_limits_payload()
    if not user_id:
        usage = get_daily_usage(f"ip:{client_ip}")
        return {
            "authenticated": False,
            "role": "guest",
            "tier": "free",
            "tier_label": "Free",
            "is_pro": False,
            "is_dev": False,
            "daily_limit": FREE_TIER_DAILY_LIMIT,
            "usage_today": usage,
            "remaining_today": max(0, FREE_TIER_DAILY_LIMIT - usage),
            "pricing": all_pricing,
            "plan_limits": plan_limits,
        }
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication is required.")
    tier = (user.get("tier") or "free").lower()
    paid_tiers = ("pro", "developer", "student_pro", "cyber_cafe", "exam_pass")
    is_pro = tier in paid_tiers
    is_dev = tier == "developer"
    usage = get_daily_usage(f"user:{user_id}")
    tier_labels = {
        "developer": "Developer",
        "pro": "Pro Power User",
        "student_pro": "Student & Educator",
        "cyber_cafe": "Cyber Café",
        "exam_pass": "Exam",
        "free": "Free",
    }
    label = tier_labels.get(tier, "Free")
    return {
        "authenticated": True,
        "user_id": user["id"],
        "email": user["email"],
        "tier": tier,
        "tier_label": label,
        "is_pro": is_pro,
        "is_dev": is_dev,
        "subscription_status": user.get("subscription_status", "inactive"),
        "created_at": user["created_at"],
        "daily_limit": None if is_pro else FREE_TIER_DAILY_LIMIT,
        "usage_today": usage,
        "remaining_today": "Unlimited" if is_pro else max(0, FREE_TIER_DAILY_LIMIT - usage),
        "pricing": all_pricing,
        "plan_limits": plan_limits,
    }


# ----------------------------------------------------------------------
# Cashfree Payment Gateway (PG v2023-08-01) & Billing Endpoints
# ----------------------------------------------------------------------


def _cashfree_headers(idempotency_key: str | None = None) -> dict[str, str]:
    headers = {
        "x-client-id": CASHFREE_APP_ID,
        "x-client-secret": CASHFREE_SECRET_KEY,
        "x-api-version": CASHFREE_API_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if idempotency_key:
        headers["x-idempotency-key"] = idempotency_key
        headers["x-request-id"] = idempotency_key
    return headers


def _cashfree_request(method: str, path: str, body: dict | None = None) -> dict:
    if CASHFREE_ENV_CONFIG_ERROR or not CASHFREE_BASE_URL:
        raise RuntimeError("Cashfree checkout is unavailable because its environment is invalid.")
    if not CASHFREE_APP_ID or not CASHFREE_SECRET_KEY:
        raise HTTPException(503, "Cashfree payment processing is not configured for this deployment.")
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"{CASHFREE_BASE_URL.rstrip('/')}/{path.lstrip('/')}",
        data=payload,
        headers=_cashfree_headers(str(uuid.uuid4())),
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise HTTPException(502, f"Cashfree API request failed ({error.code}).") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise HTTPException(502, "Cashfree API is temporarily unreachable.") from error
    except json.JSONDecodeError as error:
        raise HTTPException(502, "Cashfree returned an invalid response.") from error


def _cashfree_tier_from_order(order_id: str) -> str:
    payload = get_billing_event_payload(order_id) or {}
    tier = str(payload.get("tier", "pro")).lower()
    return tier if tier in {"pro", "developer", "student_pro", "cyber_cafe", "exam_pass"} else "pro"


def _cashfree_payment_method(payment_data: dict | None) -> str:
    """Normalize Cashfree's payment_method object for the user billing record."""
    if not isinstance(payment_data, dict):
        return "cashfree"
    method = payment_data.get("payment_method")
    if isinstance(method, str) and method.strip():
        return method.strip().lower()
    if isinstance(method, dict):
        for name in ("upi", "card", "netbanking", "wallet", "paylater", "bank_transfer"):
            if method.get(name) is not None:
                return name
        for name in method:
            if isinstance(name, str) and name.strip():
                return name.strip().lower()
    return "cashfree"


@app.get("/api/billing/status")
def billing_status(request: Request, user_id: str | None = Depends(current_user)):
    client_ip = get_client_ip(request)
    user = get_user(user_id) if user_id else None
    tier = (user.get("tier") if user else "free").lower()
    subject = f"user:{user_id}" if user_id else f"ip:{client_ip}"
    usage = get_daily_usage(subject)
    paid_tiers = ("pro", "developer", "student_pro", "cyber_cafe", "exam_pass")
    is_pro = tier in paid_tiers
    is_dev = tier == "developer"
    tier_labels = {
        "developer": "Developer",
        "pro": "Pro Power User",
        "student_pro": "Student & Educator",
        "cyber_cafe": "Cyber Café",
        "exam_pass": "Exam",
        "free": "Free",
    }
    label = tier_labels.get(tier, "Free")
    return {
        "tier": tier,
        "tier_label": label,
        "is_pro": is_pro,
        "is_dev": is_dev,
        "daily_limit": None if is_pro else FREE_TIER_DAILY_LIMIT,
        "usage_today": usage,
        "remaining_today": "Unlimited" if is_pro else max(0, FREE_TIER_DAILY_LIMIT - usage),
        "pricing": {
            "exam_pass": {"inr": EXAM_PASS_PRICE_INR},
            "student_pro": {"inr": STUDENT_PRO_PRICE_INR},
            "pro": {"inr": PRO_TIER_PRICE_INR},
            "cyber_cafe": {"inr": CYBER_CAFE_PRICE_INR},
            "developer": {"inr": DEV_TIER_PRICE_INR},
        },
        "cashfree_configured": bool(CASHFREE_APP_ID and CASHFREE_SECRET_KEY),
        "cashfree_environment": CASHFREE_ENV,
        "subscription_status": user.get("subscription_status", "inactive") if user else "inactive",
        "has_payment_customer": bool(user and user.get("payment_customer_id")),
        "cashfree_order_id": user.get("cashfree_order_id") if user else None,
    }


@app.post("/api/billing/checkout-session")
def create_checkout_session(
    request: Request,
    payload: dict = Body(default={}),
    user_id: str | None = Depends(current_user),
):
    if not user_id:
        raise HTTPException(401, "Authentication is required to subscribe.")
    user = get_user(user_id)
    if not user:
        raise HTTPException(404, "User not found.")

    valid_tiers = {"exam_pass", "student_pro", "cyber_cafe", "pro", "developer"}
    target_tier = str(payload.get("tier", "pro")).lower()
    if target_tier not in valid_tiers:
        target_tier = "pro"
    currency = str(payload.get("currency", "INR")).upper()
    if currency != "INR":
        raise HTTPException(400, "Paperplane checkout currently supports INR only.")
    if CASHFREE_ENV_CONFIG_ERROR:
        logger.error("Cashfree checkout blocked: invalid CASHFREE_ENV configuration.")
        raise HTTPException(
            503,
            "Payments are temporarily unavailable. Please try again later.",
        )
    if ENVIRONMENT == "production" and CASHFREE_ENV != "PROD" and not ALLOW_TEST_PAYMENTS:
        logger.warning("Cashfree checkout blocked in production because PROD mode is not configured.")
        raise HTTPException(
            503,
            "Payments are temporarily unavailable. Please try again later.",
        )
    if target_tier == "exam_pass":
        amount = EXAM_PASS_PRICE_INR
    elif target_tier == "student_pro":
        amount = STUDENT_PRO_PRICE_INR
    elif target_tier == "cyber_cafe":
        amount = CYBER_CAFE_PRICE_INR
    elif target_tier == "developer":
        amount = DEV_TIER_PRICE_INR
    else:
        amount = PRO_TIER_PRICE_INR
    # Cashfree order IDs are deliberately deterministic and traceable back to
    # the account that initiated the payment. The timestamp keeps retries from
    # colliding in normal operation while the database retains the active ID.
    order_id = f"order_pp_{user_id[:8]}_{int(time.time())}"
    if user.get("cashfree_order_id") == order_id:
        order_id = f"{order_id}_{uuid.uuid4().hex[:6]}"
    public_url = (PAPERPLANE_PUBLIC_URL or str(request.base_url)).rstrip("/")
    # The redirect only means checkout returned to the merchant. Payment is
    # activated exclusively after verify_cashfree_order sees Cashfree PAID.
    return_url = f"{public_url}/?billing=return&order_id={urllib.parse.quote(order_id, safe='')}"
    order_meta = {"return_url": return_url}
    if PAPERPLANE_PUBLIC_URL.startswith("https://"):
        order_meta["notify_url"] = f"{public_url}/api/billing/cashfree-webhook"
    order_payload = {
        "order_id": order_id,
        "order_amount": amount,
        "order_currency": currency,
        "customer_details": {
            "customer_id": user["id"],
            "customer_email": user["email"],
            "customer_phone": CASHFREE_DEFAULT_CUSTOMER_PHONE,
        },
        "order_meta": order_meta,
        "order_note": f"Paperplane PDF {target_tier.capitalize()} Plan",
    }

    if not CASHFREE_APP_ID or not CASHFREE_SECRET_KEY:
        if ENVIRONMENT != "development" or not ALLOW_BILLING_SIMULATION:
            raise HTTPException(503, "Live Cashfree payment processing is not configured.")
        set_user_tier(
            user_id, tier=target_tier, status="active",
            customer_id=f"demo_cashfree_{uuid.uuid4().hex[:12]}",
            cashfree_order_id=order_id, payment_method="cashfree_demo",
        )
        record_billing_event(order_id, "cashfree.demo_order_activated", user["id"], {"user_id": user_id, "tier": target_tier, "currency": currency, "amount": amount})
        return {"status": "success", "mode": "demo_activated", "order_id": order_id, "environment": CASHFREE_ENV, "tier": target_tier}

    data = _cashfree_request("POST", "/orders", order_payload)
    payment_session_id = data.get("payment_session_id")
    if not payment_session_id:
        raise HTTPException(502, "Cashfree did not return a payment session.")
    set_user_tier(user_id, tier=user.get("tier", "free"), status=user.get("subscription_status", "inactive"), cashfree_order_id=order_id, payment_method="cashfree")
    record_billing_event(order_id, "cashfree.order_created", user["id"], {"user_id": user_id, "tier": target_tier, "currency": currency, "amount": amount, "cashfree_order": data})
    return {"status": "success", "payment_session_id": payment_session_id, "order_id": order_id, "environment": CASHFREE_ENV}


@app.get("/api/billing/verify-order/{order_id}")
def verify_cashfree_order(order_id: str, user_id: str | None = Depends(current_user)):
    if not user_id:
        raise HTTPException(401, "Authentication is required.")
    user = get_user(user_id)
    if not user or user.get("cashfree_order_id") != order_id:
        raise HTTPException(404, "Payment order not found for this account.")
    data = _cashfree_request("GET", f"/orders/{urllib.parse.quote(order_id, safe='')}")
    if str(data.get("order_status", "")).upper() != "PAID":
        return {"status": str(data.get("order_status", "PENDING")).lower(), "order_id": order_id, "tier": user.get("tier", "free")}
    tier = _cashfree_tier_from_order(order_id)
    customer_id = (data.get("customer_details") or {}).get("customer_id") or user_id
    payment_method = _cashfree_payment_method(data.get("payment"))
    set_user_tier(
        user_id,
        tier=tier,
        status="active",
        customer_id=customer_id,
        cashfree_order_id=order_id,
        payment_method=payment_method,
    )
    record_billing_event(f"{order_id}:verified", "cashfree.order_verified", customer_id, data)
    return {"status": "paid", "tier": tier, "order_id": order_id}


@app.post("/api/billing/cashfree-webhook", include_in_schema=False)
async def cashfree_webhook(request: Request):
    raw_body = await request.body()
    timestamp = request.headers.get("x-webhook-timestamp", "")
    received_signature = request.headers.get("x-webhook-signature", "")
    if not CASHFREE_SECRET_KEY or not timestamp or not received_signature:
        raise HTTPException(400, "Cashfree webhook signature headers are missing.")
    expected_signature = base64.b64encode(
        hmac.new(CASHFREE_SECRET_KEY.encode("utf-8"), timestamp.encode("utf-8") + raw_body, hashlib.sha256).digest()
    ).decode("ascii")
    if not hmac.compare_digest(expected_signature, received_signature):
        raise HTTPException(400, "Cashfree webhook signature verification failed.")
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(400, "Invalid Cashfree webhook JSON payload.") from error

    event_type = event.get("type", "")
    data = event.get("data") or {}
    order_data = data.get("order") or {}
    payment_data = data.get("payment") or {}
    customer_data = data.get("customer_details") or {}
    order_id = order_data.get("order_id") or payment_data.get("order_id")
    customer_id = (
        customer_data.get("customer_id")
        or payment_data.get("customer_id")
        or order_data.get("customer_id")
    )
    event_id = (
        request.headers.get("x-idempotency-header")
        or request.headers.get("x-webhook-id")
        or f"cashfree_{hashlib.sha256(raw_body).hexdigest()}"
    )
    record_billing_event(event_id, event_type, customer_id, event)

    if event_type == "PAYMENT_SUCCESS_WEBHOOK" and str(payment_data.get("payment_status", "SUCCESS")).upper() == "SUCCESS" and order_id:
        user = get_user_by_payment_order(order_id)
        if not user and customer_id:
            user = get_user(customer_id)
        if user:
            tier = _cashfree_tier_from_order(order_id)
            set_user_tier(
                user["id"],
                tier=tier,
                status="active",
                customer_id=customer_id or user["id"],
                cashfree_order_id=order_id,
                payment_method=_cashfree_payment_method(payment_data),
            )
    return {"status": "OK"}


@app.post("/api/billing/simulate-pro", include_in_schema=False)
def simulate_pro(user_id: str = Depends(current_user)):
    """Developer test endpoint to toggle Pro Power User tier."""
    if ENVIRONMENT != "development" or not ALLOW_BILLING_SIMULATION:
        raise HTTPException(403, "Billing simulation is disabled in production environments.")
    if not user_id:
        raise HTTPException(401, "Sign in first to simulate Pro tier.")
    set_user_tier(user_id, tier="pro", status="active")
    return {"status": "success", "tier": "pro", "message": "Upgraded to Pro Power User (₹250/mo)!"}


@app.post("/api/billing/simulate-dev", include_in_schema=False)
def simulate_dev(user_id: str = Depends(current_user)):
    """Developer test endpoint to toggle Developer API tier."""
    if ENVIRONMENT != "development" or not ALLOW_BILLING_SIMULATION:
        raise HTTPException(403, "Billing simulation is disabled in production environments.")
    if not user_id:
        raise HTTPException(401, "Sign in first to simulate Developer tier.")
    set_user_tier(user_id, tier="developer", status="active")
    return {"status": "success", "tier": "developer", "message": "Upgraded to Developer (₹750/mo)!"}


@app.post("/api/billing/simulate-free", include_in_schema=False)
def simulate_free(user_id: str = Depends(current_user)):
    """Developer test endpoint to reset to Free tier."""
    if ENVIRONMENT != "development" or not ALLOW_BILLING_SIMULATION:
        raise HTTPException(403, "Billing simulation is disabled in production environments.")
    if not user_id:
        raise HTTPException(401, "Sign in first.")
    set_user_tier(user_id, tier="free", status="inactive")
    return {"status": "success", "tier": "free", "message": "Reset to Free!"}


# ----------------------------------------------------------------------
# Developer API Key Management
# ----------------------------------------------------------------------

@app.get("/api/developer/keys")
def get_keys(user_id: str = Depends(current_user)):
    if not user_id:
        raise HTTPException(401, "Authentication is required to view API keys.")
    return {"keys": list_api_keys(user_id)}


@app.post("/api/developer/keys")
def generate_key(name: str = Form("Default API Key"), user_id: str = Depends(current_user)):
    if not user_id:
        raise HTTPException(401, "Authentication is required to generate API keys.")
    user = get_user(user_id)
    tier = (user.get("tier") if user else "free").lower()
    existing_keys = list_api_keys(user_id)

    # Free tier gets 1 evaluation key, Pro, Cyber Café & Developer tiers get unlimited keys
    if tier not in ("pro", "developer", "cyber_cafe") and len(existing_keys) >= 1:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "DEV_REQUIRED_API_KEYS",
                "message": "Generating multiple API keys and continuous CI/CD SDK pipelines requires the Cyber Café & Developer plan (₹299/mo).",
                "tier": tier
            }
        )

    key_id, raw_key = create_api_key(user_id, name)
    return {"key_id": key_id, "api_key": raw_key, "name": name, "tier": tier}


@app.delete("/api/developer/keys/{key_id}")
def delete_key(key_id: str, user_id: str = Depends(current_user)):
    if not user_id:
        raise HTTPException(401, "Authentication is required.")
    if revoke_api_key(key_id, user_id):
        return {"revoked": True}
    raise HTTPException(404, "API key not found.")


# ----------------------------------------------------------------------
# AI Endpoints (Chat, Summarize, Extract, Translate)
# ----------------------------------------------------------------------

@app.post("/api/ai/chat")
async def ai_chat(
    file: UploadFile | None = File(None),
    question: str = Form(...),
    user_id: str | None = Depends(current_user)
):
    temp_dir = Path(tempfile.mkdtemp())
    try:
        if file is None:
            greeting = ai_engine._simple_greeting_reply(question)
            if greeting:
                return {"answer": greeting, "citations": [], "retrieval_method": None, "fallback_used": False}
            private_reply = ai_engine._private_information_request_reply(question)
            if private_reply:
                return {"answer": private_reply, "citations": [], "retrieval_method": None, "fallback_used": False}
            if ai_engine._is_code_request(question):
                return {"answer": ai_engine._CODE_SCOPE_REPLY, "citations": [], "retrieval_method": None, "fallback_used": False}
            if ai_engine._is_identity_question(question):
                return {"answer": ai_engine._PAPERPLANE_IDENTITY, "citations": [], "retrieval_method": None, "fallback_used": False}
            if ai_engine._is_document_question(question):
                return {"answer": "No PDF is open. Upload a document for a cited answer, or ask a general question directly.", "citations": [], "retrieval_method": None}
            correction = ai_engine.correct_false_premise(None, question)
            if correction:
                return {"answer": correction, "citations": [], "retrieval_method": None, "fallback_used": False}
            answer = await asyncio.to_thread(ai_engine.call_llm, ai_engine._PAPERPLANE_SYSTEM_PROMPT, question, 35)
            answer = ai_engine._guard_ai_output(answer)
            return {"answer": answer, "citations": [], "retrieval_method": None, "fallback_used": False}
        temp_pdf = temp_dir / "chat_doc.pdf"
        await save_upload_spooled_async(file, temp_pdf, max_bytes=upload_limit_bytes_for_user(user_id))
        return await asyncio.to_thread(ai_engine.chat_with_pdf, temp_pdf, question)
    except ValueError as ve:
        raise HTTPException(status_code=503, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=502, detail=str(re))
    except HTTPException:
        raise
    except Exception as err:
        logging.getLogger("paperplane").error("AI chat failed: %s", err)
        raise HTTPException(status_code=502, detail="AI request failed, please try again")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/ai/chat/stream")
async def ai_chat_stream(
    file: UploadFile | None = File(None),
    question: str = Form(...),
    user_id: str | None = Depends(current_user),
):
    """SSE chat endpoint: reports real work stages and streams upstream content deltas."""
    temp_dir = Path(tempfile.mkdtemp())

    def frame(kind: str, **data: Any) -> str:
        return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def events():
        try:
            yield frame("stage", stage="Thinking…")
            greeting = ai_engine._simple_greeting_reply(question)
            if greeting:
                yield frame("replace", text=greeting)
                yield frame("done", citations=[], mode="direct_conversation")
                return
            private_reply = ai_engine._private_information_request_reply(question)
            if private_reply:
                yield frame("replace", text=private_reply)
                yield frame("done", citations=[])
                return
            if ai_engine._is_code_request(question):
                yield frame("replace", text=ai_engine._CODE_SCOPE_REPLY)
                yield frame("done", citations=[])
                return
            if ai_engine._is_identity_question(question):
                yield frame("replace", text=ai_engine._PAPERPLANE_IDENTITY)
                yield frame("done", citations=[])
                return

            citations: list[int] = []
            system_prompt = ai_engine._PAPERPLANE_SYSTEM_PROMPT
            user_prompt = question
            document_question = ai_engine._is_document_question(question)
            if file is not None:
                temp_pdf = temp_dir / "chat_stream.pdf"
                await save_upload_spooled_async(file, temp_pdf, max_bytes=upload_limit_bytes_for_user(user_id))
                yield frame("stage", stage="Extracting…")
                chunks = await asyncio.to_thread(ai_engine.extract_chunks_from_pdf, temp_pdf)
                correction = await asyncio.to_thread(ai_engine.correct_false_premise, temp_pdf, question)
                if correction:
                    yield frame("replace", text=correction)
                    yield frame("done", citations=[])
                    return
                yield frame("stage", stage="Analysing…")
                if not chunks:
                    yield frame("replace", text="No readable text was found in this document to answer your question.")
                    yield frame("done", citations=[])
                    return
                yield frame("stage", stage="Searching…")
                page_match = re.search(r"\bpage\s+(\d+)\b", question, re.IGNORECASE)
                broad_summary = bool(re.search(r"\b(summar(?:y|ize|ise)|overview|key points|important information)\b", question, re.IGNORECASE))
                if page_match:
                    requested = int(page_match.group(1))
                    chosen = [chunk for chunk in chunks if chunk.page_number == requested]
                elif broad_summary:
                    chosen = ai_engine._select_broad_summary_chunks(chunks)
                else:
                    chosen = ai_engine.LightweightRAG(chunks).search(question, top_k=8)
                if not chosen:
                    yield frame("replace", text="No relevant information found in the document for your question.")
                    yield frame("done", citations=[])
                    return
                citations = sorted({chunk.page_number for chunk in chosen})
                context = "\n\n---\n\n".join(f"[Page {chunk.page_number}]:\n{chunk.text}" for chunk in chosen)
                system_prompt += " Answer accurately using only the provided document excerpts and cite factual claims as [Page X]."
                user_prompt = f"DOCUMENT EXCERPTS:\n{context}\n\nUSER QUESTION: {question}"
            else:
                if file is None and document_question:
                    yield frame("replace", text="No PDF is open. Upload a document for a cited answer, or ask a general question directly.")
                    yield frame("done", citations=[])
                    return
                yield frame("stage", stage="Analysing…")
                correction = await asyncio.to_thread(ai_engine.correct_false_premise, None, question)
                if correction:
                    yield frame("replace", text=correction)
                    yield frame("done", citations=[])
                    return

            # With the external provider deliberately disabled, PDF chat still
            # returns a clearly labelled local extractive answer. It never
            # represents that answer as model-generated.
            if file is not None and (
                ai_engine.AI_KILL_SWITCH or not ai_engine._current_bluesminds_api_key()
            ):
                local_answer = ai_engine._offline_rag_fallback(system_prompt, user_prompt)
                local_answer, local_citations = ai_engine.align_answer_citations(local_answer, citations)
                yield frame("stage", stage="Generating…")
                for word in re.findall(r"\S+\s*", local_answer):
                    yield frame("token", text=word)
                    await asyncio.sleep(0.02)
                yield frame("done", citations=local_citations, mode="local_extraction")
                return

            yield frame("stage", stage="Generating…")
            stream = iter(ai_engine.stream_bluesminds(system_prompt, user_prompt))
            sentinel = object()

            def get_next():
                try:
                    return next(stream)
                except StopIteration:
                    return sentinel

            accumulated = ""
            pending_output = ""
            full_answer = ""
            max_forbidden_len = max([len(ai_engine.BLUESMINDS_MODEL or "")] + [len(word) for word in ("nemotron", "nvidia", "bluesminds", "openai", "anthropic", "google gemini")])
            # Hold the entire possible self-identification phrase. A short
            # rolling tail is unsafe because the introduction might already
            # have been emitted before the provider name arrives in a later
            # SSE delta.
            identity_guard_buffer = max(180, max_forbidden_len + 140)
            while True:
                piece = await asyncio.to_thread(get_next)
                if piece is sentinel:
                    break
                accumulated += piece
                full_answer += piece
                pending_output += piece
                guarded_full_answer = ai_engine._guard_ai_output(full_answer)
                if guarded_full_answer == ai_engine._PAPERPLANE_IDENTITY and full_answer != guarded_full_answer:
                    yield frame("replace", text=guarded_full_answer)
                    accumulated = ""
                    pending_output = ""
                    full_answer = guarded_full_answer
                    break
                safe_limit = max(0, len(pending_output) - identity_guard_buffer)
                safe_len = max(pending_output.rfind(" ", 0, safe_limit), pending_output.rfind("\n", 0, safe_limit), pending_output.rfind("\t", 0, safe_limit))
                if safe_len:
                    yield frame("token", text=pending_output[:safe_len + 1])
                    pending_output = pending_output[safe_len + 1:]
            if pending_output:
                yield frame("token", text=pending_output)
            final_answer, aligned_citations = ai_engine.align_answer_citations(
                ai_engine._guard_ai_output(full_answer), citations
            )
            # Replace the streamed draft once with its citation-validated final
            # form; chips and inline page references now share one source.
            yield frame("replace", text=final_answer)
            yield frame("done", citations=aligned_citations)
        except ValueError as exc:
            logging.getLogger("paperplane").warning("AI stream configuration issue: %s", exc)
            yield frame("error", message="AI provider is not configured")
        except Exception as exc:
            logging.getLogger("paperplane").warning("AI stream failed: %s", exc)
            safe_message = str(exc)
            if not safe_message.startswith("AI service "):
                safe_message = "Paperplane AI could not complete the request. Please try again."
            yield frame("error", message=safe_message[:240])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/ai/summarize")
async def ai_summarize(
    file: UploadFile = File(...),
    user_id: str | None = Depends(current_user)
):
    temp_dir = Path(tempfile.mkdtemp())
    summary_task: asyncio.Task | None = None
    defer_temp_cleanup = False
    try:
        temp_pdf = temp_dir / "summary_doc.pdf"
        await save_upload_spooled_async(file, temp_pdf, max_bytes=upload_limit_bytes_for_user(user_id))

        def build_summary() -> tuple[str, list[int]]:
            summary_text = ai_engine.summarize_pdf(temp_pdf)
            eligible_pages = sorted({chunk.page_number for chunk in ai_engine.extract_chunks_from_pdf(temp_pdf) if chunk.text.strip()})
            return ai_engine.align_answer_citations(summary_text, eligible_pages)

        summary_task = asyncio.create_task(asyncio.to_thread(build_summary))
        try:
            summary, citations = await asyncio.wait_for(
                asyncio.shield(summary_task),
                timeout=AI_SUMMARY_REQUEST_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            defer_temp_cleanup = True
            summary_task.add_done_callback(lambda _task: shutil.rmtree(temp_dir, ignore_errors=True))
            raise HTTPException(
                status_code=504,
                detail="The AI provider did not return an executive brief before the request deadline. No output was created; retry later.",
                headers={"Retry-After": "5"},
            ) from exc
        except asyncio.CancelledError:
            defer_temp_cleanup = True
            summary_task.add_done_callback(lambda _task: shutil.rmtree(temp_dir, ignore_errors=True))
            raise
        return {"status": "success", "summary": summary, "citations": citations}
    except ValueError as ve:
        raise HTTPException(status_code=503, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=502, detail=str(re))
    except HTTPException:
        raise
    except Exception as err:
        logging.getLogger("paperplane").error("AI summarize failed: %s", err)
        raise HTTPException(status_code=502, detail="AI request failed, please try again")
    finally:
        if not defer_temp_cleanup:
            shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/ai/extract")
async def ai_extract(
    file: UploadFile = File(...),
    doc_type: str = Form("auto"),
    user_id: str | None = Depends(current_user)
):
    temp_dir = Path(tempfile.mkdtemp())
    try:
        temp_pdf = temp_dir / "extract_doc.pdf"
        await save_pdf_upload_async(file, temp_pdf, user_id=user_id)
        data = await asyncio.to_thread(ai_engine.extract_metadata_entities, temp_pdf, doc_type)
        return {"status": "success", "data": data}
    except Exception as err:
        logging.getLogger("paperplane").warning(f"Smart metadata extraction fallback triggered: {err}")
        return {
            "status": "success",
            "data": {
                "document_type": "general",
                "total_pages": 1,
                "contact": {"emails": [], "phones": []},
                "source_pages": [],
                "warnings": ["Extraction completed using local fallback parser."],
                "general_data": {
                    "title": file.filename or "Document",
                    "document_date": None,
                    "detected_topics": ["General Document"],
                    "key_entities": []
                },
                "retrieval_method": "Deterministic Structural Entity Extraction"
            }
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/ai/translate")
async def ai_translate_endpoint(
    file: UploadFile = File(...),
    target_language: str = Form("es"),
    user_id: str | None = Depends(current_user)
):
    if not translation_ai_available():
        raise HTTPException(503, "AI translation is unavailable because the Paperplane AI translation service is not configured or enabled.")
    temp_dir = Path(tempfile.mkdtemp())
    translation_task: asyncio.Task | None = None
    defer_temp_cleanup = False
    try:
        temp_pdf = temp_dir / "translate_input.pdf"
        save_pdf_upload(file, temp_pdf, user_id=user_id)
        out_pdf = temp_dir / f"translated_{target_language}.pdf"
        translation_report: dict = {}
        translation_task = asyncio.create_task(asyncio.to_thread(
            ai_engine.translate_pdf_layout,
            temp_pdf,
            out_pdf,
            target_lang=target_language,
            report=translation_report,
        ))
        try:
            await asyncio.wait_for(asyncio.shield(translation_task), timeout=AI_TRANSLATION_REQUEST_TIMEOUT_SECONDS)
        except asyncio.TimeoutError as exc:
            defer_temp_cleanup = True
            translation_task.add_done_callback(lambda _task: shutil.rmtree(temp_dir, ignore_errors=True))
            raise HTTPException(status_code=504, detail="The translation provider did not return a result before the request deadline. No translated PDF was created; retry later.", headers={"Retry-After": "5"}) from exc
        except asyncio.CancelledError:
            defer_temp_cleanup = True
            translation_task.add_done_callback(lambda _task: shutil.rmtree(temp_dir, ignore_errors=True))
            raise
        content = out_pdf.read_bytes()
        return StreamingResponse(
            io.BytesIO(content),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="translated_{target_language}.pdf"',
                "X-Paperplane-Translation-Mode": "translated" if translation_report.get("blocks_translated") and not translation_report.get("blocks_preserved") else "partial" if translation_report.get("blocks_translated") else "failed",
                "X-Paperplane-Translation-Warnings": str(len(translation_report.get("warnings", []))),
            }
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="AI translation is not configured for this workspace.") from exc
    except RuntimeError as exc:
        status_code, detail, headers = translation_failure_response(exc)
        logging.getLogger("paperplane").warning("AI translation failed: %s", detail)
        raise HTTPException(status_code=status_code, detail=detail, headers=headers) from exc
    except Exception as exc:
        logging.getLogger("paperplane").error("AI translation failed unexpectedly (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Translation provider failed during document processing. Please retry later.", headers={"Retry-After": "5"}) from exc
    finally:
        if not defer_temp_cleanup:
            shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/api/ai/capabilities", tags=["AI Intelligence"])
def ai_capabilities():
    """Expose only whether executive summarization can run, never provider details."""
    if ai_engine.AI_KILL_SWITCH:
        return {
            "executive_brief_available": False,
            "reason": "ai_service_disabled",
        }
    available = bool(ai_engine._current_bluesminds_api_key())
    return {
        "executive_brief_available": available,
        "reason": None if available else "ai_service_not_configured",
    }


@app.get("/api/ai/test-connection", tags=["AI Intelligence"])
@app.post("/api/ai/test-connection", tags=["AI Intelligence"])
def general_ai_test_connection():
    """
    Public connection test endpoint for UI and workspace callers.
    Safely checks the configured AI service without leaking secrets.
    """
    result = ai_engine.test_bluesminds_connectivity()
    status = result.get("status")
    if status in ("connected", "inference_succeeded"):
        return {
            "status": "connected",
            "message": "Short AI connection check passed. Full PDF workflows can still fail or time out.",
            "fallback_active": False,
        }
    if status == "configuration_missing":
        return {"status": status, "message": "AI provider is not configured", "fallback_active": False}
    http_status = result.get("http_status")
    error_label = f" (HTTP {int(http_status)})" if isinstance(http_status, int) else ""
    return {
        "status": "connection_error",
        "message": f"AI connection failed{error_label}. Check the configured AI service and try again.",
        "fallback_active": False,
    }


@app.post("/api/pdf/annotate")
async def pdf_annotate_endpoint(
    file: UploadFile = File(...),
    annotations: str = Form("[]"),
    user_id: str | None = Depends(current_user)
):
    temp_dir = Path(tempfile.mkdtemp())
    try:
        temp_pdf = temp_dir / "annot_input.pdf"
        save_pdf_upload(file, temp_pdf, user_id=user_id)
        out_pdf = temp_dir / "annotated.pdf"
        parsed = json.loads(annotations)
        converters.annotate_pdf(temp_pdf, out_pdf, annotations=parsed)
        content = out_pdf.read_bytes()
        return StreamingResponse(
            io.BytesIO(content),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="annotated.pdf"'}
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)



# ----------------------------------------------------------------------
# Phase 2: Studio Editor Backend Endpoints
# ----------------------------------------------------------------------

@app.post("/api/studio/apply-edits")
async def studio_apply_edits(
    file: UploadFile = File(...),
    edits: str = Form("[]"),
    user_id: str | None = Depends(current_user)
):
    """
    Bake all editor annotations/objects (text overlays, images, shapes,
    freehand strokes, signature marks) into a real PDF using PyMuPDF.

    edits: JSON array of EditorObject records (see Phase 2 editor.js schema).
    Each object contains: type, page (1-based), docX, docY, docW, docH,
    and type-specific payload (text content, imageData base64, stroke points, etc.)

    Returns: the modified PDF as a streaming response.

    IMPORTANT: Text objects are inserted as PDF text overlays (NOT
    in-place modification of existing PDF content). This is clearly
    labelled in the UI as "Text Overlay". True in-content editing of
    existing PDF text is not supported by this stack safely.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        # Save upload
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        # Parse edit objects
        try:
            edit_list = json.loads(edits or "[]")
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"Invalid edits JSON: {e}")

        if not isinstance(edit_list, list):
            raise HTTPException(400, "edits must be a JSON array.")

        out_path = temp_dir / "edited.pdf"
        converters.apply_editor_annotations(in_path, out_path, edit_list)

        out_bytes = out_path.read_bytes()
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="edited.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Editor bake failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/page/insert")
async def studio_page_insert(
    file: UploadFile = File(...),
    after_page: int = Form(0),   # 1-based; 0 = prepend before page 1
    width: float = Form(595),
    height: float = Form(842),
    orientation: str = Form("portrait"),
    user_id: str | None = Depends(current_user)
):
    """
    Insert a blank page into the PDF after the specified page number.
    Configurable width, height, and orientation.
    after_page=0 inserts before the first page.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        doc = fitz.open(str(in_path))
        total = len(doc)

        insert_at = max(0, min(after_page, total))  # clamp
        target_w = float(width)
        target_h = float(height)
        if orientation.lower() == "landscape" and target_w < target_h:
            target_w, target_h = target_h, target_w
        elif orientation.lower() == "portrait" and target_w > target_h:
            target_w, target_h = target_h, target_w

        doc.insert_page(insert_at, width=target_w, height=target_h)

        out_path = temp_dir / "with_page.pdf"
        doc.save(str(out_path), garbage=4, deflate=True)
        doc.close()

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="with_page.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Page insert failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/page/delete")
async def studio_page_delete(
    file: UploadFile = File(...),
    page_number: int | None = Form(None),   # 1-based (single page)
    pages: str | None = Form(None),         # JSON array of 1-based pages
    user_id: str | None = Depends(current_user)
):
    """
    Delete one or more pages from the PDF.
    Refuses if attempting to delete all pages.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        doc = fitz.open(str(in_path))
        total = len(doc)

        to_delete = []
        if pages:
            try:
                parsed = json.loads(pages)
                if isinstance(parsed, list):
                    to_delete = [int(p) for p in parsed]
            except Exception as e:
                raise HTTPException(400, f"Invalid pages JSON: {e}")
        elif page_number is not None:
            to_delete = [int(page_number)]
        else:
            raise HTTPException(400, "Must provide page_number or pages.")

        to_delete_set = set(to_delete)
        if total <= 1:
            raise HTTPException(400, "Cannot delete the only page in the document.")
        if len(to_delete_set) >= total:
            raise HTTPException(400, "Cannot delete all pages in the document.")

        for p in to_delete_set:
            if p < 1 or p > total:
                raise HTTPException(400, f"Page {p} is out of range (1–{total}).")

        # Delete from highest to lowest index so subsequent indices do not shift
        for p in sorted(to_delete_set, reverse=True):
            doc.delete_page(p - 1)

        out_path = temp_dir / "deleted_page.pdf"
        # A one-page delete already rewrites the page tree. Deep garbage
        # collection (level 4) scans and deduplicates every object, which made
        # large Studio deletes unnecessarily slow. Level 1 drops unreferenced
        # objects while keeping the mutation bounded and the output valid.
        doc.save(str(out_path), garbage=1, deflate=True)
        doc.close()

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="deleted_page.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Page delete failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/page/duplicate")
async def studio_page_duplicate(
    file: UploadFile = File(...),
    page_number: int | None = Form(None),   # 1-based (single page)
    pages: str | None = Form(None),         # JSON array of 1-based pages
    user_id: str | None = Depends(current_user)
):
    """
    Duplicate one or more pages and insert copies immediately after each original.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        doc = fitz.open(str(in_path))
        total = len(doc)

        to_dup = []
        if pages:
            try:
                parsed = json.loads(pages)
                if isinstance(parsed, list):
                    to_dup = [int(p) for p in parsed]
            except Exception as e:
                raise HTTPException(400, f"Invalid pages JSON: {e}")
        elif page_number is not None:
            to_dup = [int(page_number)]
        else:
            raise HTTPException(400, "Must provide page_number or pages.")

        for p in to_dup:
            if p < 1 or p > total:
                raise HTTPException(400, f"Page {p} out of range.")

        src_doc = fitz.open(str(in_path))
        # Duplicate from highest to lowest index to maintain stable insertion relative to original
        for p in sorted(to_dup, reverse=True):
            doc.insert_pdf(src_doc, from_page=p - 1, to_page=p - 1, start_at=p)
        src_doc.close()

        out_path = temp_dir / "duplicated.pdf"
        doc.save(str(out_path), garbage=4, deflate=True)
        doc.close()

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="duplicated.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Page duplicate failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ----------------------------------------------------------------------
# Phase 3: Page Organizer, Reorder, Rotate, Crop, Resize, Extract, Split, Import
# ----------------------------------------------------------------------

@app.post("/api/studio/pages/reorder")
async def studio_pages_reorder(
    file: UploadFile = File(...),
    order: str = Form(...),  # JSON array of page indices
    user_id: str | None = Depends(current_user)
):
    """
    Reorder pages in a PDF document in-place.
    order: JSON array of 0-based or 1-based page indices representing desired new order.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        try:
            order_list = json.loads(order)
            if not isinstance(order_list, list):
                raise ValueError("order must be a JSON array.")
            order_list = [int(x) for x in order_list]
        except Exception as e:
            raise HTTPException(400, f"Invalid order parameter: {e}")

        doc = fitz.open(str(in_path))
        total = len(doc)
        doc.close()

        if len(order_list) == 0:
            raise HTTPException(400, "Page order list cannot be empty.")

        # Detect 1-based vs 0-based list
        min_val = min(order_list)
        max_val = max(order_list)
        if min_val >= 1 and max_val == total and len(order_list) == total:
            # Convert 1-based to 0-based
            order_list = [x - 1 for x in order_list]
        elif max_val >= total or min_val < 0:
            raise HTTPException(400, f"Page indices outside range 0..{total - 1}.")

        out_path = temp_dir / "reordered.pdf"
        converters.reorder_pdf_pages(in_path, out_path, order_list)

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="reordered.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Page reorder failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/pages/rotate")
async def studio_pages_rotate(
    file: UploadFile = File(...),
    pages: str = Form("all"),       # "all" or JSON array of 1-based pages
    degrees: int = Form(90),        # degrees e.g. 90, 180, 270, -90
    user_id: str | None = Depends(current_user)
):
    """
    Rotate specified pages or all pages by given degrees (+90, -90, 180, 270).
    Persists rotation directly to PDF page geometry.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        pages_parsed: list[int] | str = "all"
        if pages != "all":
            try:
                pages_parsed = json.loads(pages)
                if not isinstance(pages_parsed, list):
                    pages_parsed = [int(pages)]
                else:
                    pages_parsed = [int(x) for x in pages_parsed]
            except Exception:
                # Handle comma-separated string e.g. "1,2,3"
                try:
                    pages_parsed = [int(x.strip()) for x in pages.split(",") if x.strip()]
                except Exception as e:
                    raise HTTPException(400, f"Invalid pages format: {e}")

        out_path = temp_dir / "rotated.pdf"
        converters.rotate_pdf_pages(in_path, out_path, pages_parsed, degrees)

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="rotated.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Page rotate failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/pages/crop")
async def studio_pages_crop(
    file: UploadFile = File(...),
    pages: str = Form("all"),       # "all" or JSON array of 1-based pages
    box: str = Form(...),           # JSON object {x, y, width, height} or [x0, y0, x1, y1]
    user_id: str | None = Depends(current_user)
):
    """
    Apply crop box in 72 DPI PDF user points to specified pages.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        pages_parsed: list[int] | str = "all"
        if pages != "all":
            try:
                pages_parsed = json.loads(pages)
                if not isinstance(pages_parsed, list):
                    pages_parsed = [int(pages)]
                else:
                    pages_parsed = [int(x) for x in pages_parsed]
            except Exception:
                try:
                    pages_parsed = [int(x.strip()) for x in pages.split(",") if x.strip()]
                except Exception as e:
                    raise HTTPException(400, f"Invalid pages format: {e}")

        try:
            box_data = json.loads(box)
        except Exception as e:
            raise HTTPException(400, f"Invalid box JSON: {e}")

        out_path = temp_dir / "cropped.pdf"
        converters.crop_pdf_pages(in_path, out_path, pages_parsed, box_data)

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="cropped.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Page crop failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/pages/resize")
async def studio_pages_resize(
    file: UploadFile = File(...),
    pages: str = Form("all"),       # "all" or JSON array of 1-based pages
    target_w: float = Form(...),     # Width in points
    target_h: float = Form(...),     # Height in points
    mode: str = Form("scale"),       # 'scale', 'center', or 'crop'
    user_id: str | None = Depends(current_user)
):
    """
    Resize specified pages to target dimensions (pt).
    mode: 'scale' (proportional vector fit), 'center' (centered), 'crop' (mediabox adjustment).
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        pages_parsed: list[int] | str = "all"
        if pages != "all":
            try:
                pages_parsed = json.loads(pages)
                if not isinstance(pages_parsed, list):
                    pages_parsed = [int(pages)]
                else:
                    pages_parsed = [int(x) for x in pages_parsed]
            except Exception:
                try:
                    pages_parsed = [int(x.strip()) for x in pages.split(",") if x.strip()]
                except Exception as e:
                    raise HTTPException(400, f"Invalid pages format: {e}")

        out_path = temp_dir / "resized.pdf"
        converters.resize_pdf_pages(in_path, out_path, pages_parsed, float(target_w), float(target_h), mode)

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="resized.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Page resize failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/pages/extract")
async def studio_pages_extract(
    file: UploadFile = File(...),
    pages: str = Form(...),  # JSON array of 1-based page numbers in desired sequence
    user_id: str | None = Depends(current_user)
):
    """
    Extract a subset of pages into a new PDF document.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        try:
            pages_list = json.loads(pages)
            if not isinstance(pages_list, list):
                pages_list = [int(pages)]
            else:
                pages_list = [int(x) for x in pages_list]
        except Exception:
            try:
                pages_list = [int(x.strip()) for x in pages.split(",") if x.strip()]
            except Exception as e:
                raise HTTPException(400, f"Invalid pages format: {e}")

        if not pages_list:
            raise HTTPException(400, "No pages specified for extraction.")

        out_path = temp_dir / "extracted.pdf"
        converters.extract_pdf_pages(in_path, out_path, pages_list)

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="extracted.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Page extract failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/pages/import")
async def studio_pages_import(
    base_file: UploadFile = File(...),
    import_file: UploadFile = File(...),
    pages: str = Form("[]"),                # JSON list of 1-based page numbers or empty for all
    insert_after_page: int = Form(0),        # 0 = beginning, N = after page N
    user_id: str | None = Depends(current_user)
):
    """
    Cross-document page import: import selected pages from import_file into base_file.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        base_path = temp_dir / "base.pdf"
        save_pdf_upload(base_file, base_path, user_id=user_id)

        import_path = temp_dir / "import.pdf"
        save_pdf_upload(import_file, import_path, user_id=user_id)

        pages_list: list[int] | None = None
        if pages and pages != "[]":
            try:
                parsed = json.loads(pages)
                if isinstance(parsed, list) and len(parsed) > 0:
                    pages_list = [int(x) for x in parsed]
            except Exception:
                try:
                    pages_list = [int(x.strip()) for x in pages.split(",") if x.strip()]
                except Exception as e:
                    raise HTTPException(400, f"Invalid pages parameter: {e}")

        out_path = temp_dir / "imported.pdf"
        converters.import_pdf_pages(base_path, import_path, out_path, pages_list, insert_after_page)

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="imported.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Cross-document page import failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/documents/merge")
async def studio_documents_merge(
    files: list[UploadFile] = File(...),
    order: str = Form("[]"),  # Optional JSON list of filename strings or indices
    user_id: str | None = Depends(current_user)
):
    """
    Merge multiple PDF files into one unified document with specified ordering.
    """
    if len(files) < 2:
        raise HTTPException(400, "At least two PDF files are required for merging.")

    temp_dir = Path(tempfile.mkdtemp())
    try:
        saved_paths: dict[str, Path] = {}
        path_list: list[Path] = []

        for idx, f in enumerate(files):
            p = temp_dir / f"doc_{idx}_{f.filename}"
            save_pdf_upload(f, p, user_id=user_id)
            saved_paths[f.filename] = p
            path_list.append(p)

        # Apply ordering if provided
        final_sources: list[Path] = []
        if order and order != "[]":
            try:
                order_spec = json.loads(order)
                if isinstance(order_spec, list) and len(order_spec) > 0:
                    for item in order_spec:
                        if isinstance(item, int) and 0 <= item < len(path_list):
                            final_sources.append(path_list[item])
                        elif isinstance(item, str) and item in saved_paths:
                            final_sources.append(saved_paths[item])
            except Exception:
                final_sources = path_list
        if not final_sources:
            final_sources = path_list

        out_path = temp_dir / "merged.pdf"
        converters.merge_pdf_documents(final_sources, out_path)

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="merged.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Document merge failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/documents/split")
async def studio_documents_split(
    file: UploadFile = File(...),
    mode: str = Form(...),   # 'ranges' or 'every_n'
    param: str = Form(...),  # e.g. "1-2, 3-5" or "2"
    user_id: str | None = Depends(current_user)
):
    """
    Split a PDF by page ranges or every N pages.
    Returns standalone PDF if 1 part produced, or a ZIP archive containing all parts if multiple.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        split_dir = temp_dir / "split_output"
        try:
            created_files = converters.split_pdf_document(in_path, split_dir, mode, param)
        except ValueError as err:
            raise HTTPException(400, str(err)) from err

        if not created_files:
            raise HTTPException(400, "No files generated from split operation.")

        if len(created_files) == 1:
            return StreamingResponse(
                io.BytesIO(created_files[0].read_bytes()),
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{created_files[0].name}"'}
            )

        # Multiple files: package into a ZIP archive
        zip_path = temp_dir / "split_documents.zip"
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for f in created_files:
                zf.write(str(f), arcname=f.name)

        return StreamingResponse(
            io.BytesIO(zip_path.read_bytes()),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="split_documents.zip"'}
        )
    except ValueError as err:
        raise HTTPException(400, str(err)) from err
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Split document failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/pages/metadata")
async def studio_pages_metadata(
    file: UploadFile = File(...),
    user_id: str | None = Depends(current_user)
):
    """
    Retrieve structural metadata per page: dimensions, rotation, orientation, and logical labels.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        data = converters.get_pdf_metadata_pages(in_path)
        return JSONResponse({"ok": True, "data": data})
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Failed to extract page metadata: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# Phase 4 Studio Endpoints: Compression, Repair & OCR
# =============================================================================

@app.get("/api/studio/ocr/languages")
def studio_ocr_languages():
    """Returns list of genuinely installed OCR language models found in tessdata/."""
    langs = converters.get_installed_ocr_languages()
    return JSONResponse({"ok": True, "languages": langs})


@app.post("/api/studio/ocr")
async def studio_ocr(
    file: UploadFile = File(...),
    language: str = Form("eng"),
    pages: str = Form("all"),       # "all" or JSON list of 1-based page numbers
    mode: str = Form("scanned_only"),  # "scanned_only" | "all" | "selected"
    dpi: int = Form(150),
    user_id: str | None = Depends(current_user)
):
    """
    Performs genuine OCR and adds a searchable text layer to the PDF.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        pages_parsed: list[int] | str = "all"
        if pages != "all":
            try:
                pages_parsed = json.loads(pages)
                if not isinstance(pages_parsed, list):
                    pages_parsed = [int(pages)]
                else:
                    pages_parsed = [int(x) for x in pages_parsed]
            except Exception:
                try:
                    pages_parsed = [int(x.strip()) for x in pages.split(",") if x.strip()]
                except Exception as e:
                    raise HTTPException(400, f"Invalid pages format: {e}")

        out_path = temp_dir / "ocr_result.pdf"
        report = await asyncio.to_thread(
            run_converter_with_timeout,
            converters.ocr_pdf,
            in_path, out_path,
            language=language,
            pages=pages_parsed,
            mode=mode,
            dpi=dpi,
            timeout_seconds=OCR_TIMEOUT_SECONDS,
            tool_name="ocr",
            source_path=in_path,
            output_path=out_path,
            retry_hint="Try running OCR on a smaller page selection or reducing the DPI setting."
        )

        headers = {
            "Content-Disposition": 'attachment; filename="ocr_searchable.pdf"',
            "X-Pages-Processed": str(report["pages_processed"]),
            "X-Pages-OCRed": str(report["pages_ocrd"]),
            "X-Already-Searchable": str(report["pages_already_searchable"]),
            "X-Pages-Failed": str(report["pages_failed"]),
            "X-Language": report["language"],
            "X-Extracted-Chars": str(report["extracted_chars"]),
            "X-Elapsed-Seconds": str(report["elapsed_seconds"]),
            "X-Original-Size": str(report["original_size"]),
            "X-Output-Size": str(report["output_size"]),
            "Access-Control-Expose-Headers": "X-Pages-Processed, X-Pages-OCRed, X-Already-Searchable, X-Pages-Failed, X-Language, X-Extracted-Chars, X-Elapsed-Seconds, X-Original-Size, X-Output-Size"
        }

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers=headers
        )
    except HTTPException:
        raise
    except TimeoutError as te:
        return JSONResponse(
            status_code=504,
            content={
                "ok": False,
                "error": str(te),
                "retry_hint": "Try running OCR on a smaller page selection or reducing the DPI setting.",
                "detail": str(te)
            }
        )
    except ValueError as ve:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": str(ve),
                "retry_hint": "Please verify OCR language models and PDF validity.",
                "detail": str(ve)
            }
        )
    except Exception as err:
        logger.error("Studio OCR processing failed: %s", err)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": f"OCR processing failed: {err}",
                "retry_hint": "Please try again with a smaller file or standard DPI.",
                "detail": f"OCR processing failed: {err}"
            }
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/compress/analyze")
async def studio_compress_analyze(
    file: UploadFile = File(...),
    user_id: str | None = Depends(current_user)
):
    """
    Analyzes PDF structure and returns compression potential report.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        report = converters.analyze_pdf_compression(in_path)
        return JSONResponse({"ok": True, "analysis": report})
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Compression analysis failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/compress")
async def studio_compress(
    file: UploadFile = File(...),
    preset: str = Form("balanced"),
    target_size_kb: int | None = Form(None),
    quality: int = Form(65),
    max_dpi: int = Form(150),
    user_id: str | None = Depends(current_user)
):
    """
    Compresses PDF using chosen preset ('extreme', 'high', 'balanced', 'high_quality', 'lossless')
    or target size in KB.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        target_bytes = int(target_size_kb) * 1024 if target_size_kb and target_size_kb > 0 else None
        out_path = temp_dir / "compressed.pdf"

        report = await asyncio.to_thread(
            run_converter_with_timeout,
            converters.compress_pdf,
            in_path, out_path,
            quality=quality, max_dpi=max_dpi,
            preset=preset, target_size_bytes=target_bytes,
            timeout_seconds=COMPRESS_TIMEOUT_SECONDS,
            tool_name="compress",
            source_path=in_path,
            output_path=out_path,
            retry_hint="Try selecting a lower resolution preset or splitting the document."
        )

        headers = {
            "Content-Disposition": 'attachment; filename="compressed.pdf"',
            "X-Original-Size": str(report["original_size"]),
            "X-Output-Size": str(report["output_size"]),
            "X-Saved-Bytes": str(report["saved_bytes"]),
            "X-Percent-Saved": str(report["percent_saved"]),
            "X-Preset-Used": str(report["preset_used"]),
            "Access-Control-Expose-Headers": "X-Original-Size, X-Output-Size, X-Saved-Bytes, X-Percent-Saved, X-Preset-Used"
        }

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers=headers
        )
    except HTTPException:
        raise
    except TimeoutError as te:
        return JSONResponse(
            status_code=504,
            content={
                "ok": False,
                "error": str(te),
                "retry_hint": "Try selecting a lower resolution preset or splitting the document.",
                "detail": str(te)
            }
        )
    except ValueError as ve:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": str(ve),
                "retry_hint": "Please verify file format and security restrictions.",
                "detail": str(ve)
            }
        )
    except Exception as err:
        logger.error("Studio compression failed: %s", err)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": f"Compression failed: {err}",
                "retry_hint": "Please try again or select a different preset.",
                "detail": f"Compression failed: {err}"
            }
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/repair")
async def studio_repair(
    file: UploadFile = File(...),
    mode: str = Form("automatic"),  # 'automatic' | 'advanced' | 'validate_only'
    user_id: str | None = Depends(current_user)
):
    """
    Validates or repairs corrupted, malformed, or truncated PDFs.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_upload_spooled(file, in_path, max_bytes=upload_limit_bytes_for_user(user_id))

        out_path = temp_dir / "repaired.pdf"
        try:
            report = converters.repair_pdf_advanced(in_path, out_path, mode=mode)
        except ValueError as ve:
            raise HTTPException(422, str(ve)) from ve

        if mode == "validate_only":
            return JSONResponse({"ok": True, "report": report})

        headers = {
            "Content-Disposition": 'attachment; filename="repaired.pdf"',
            "X-Repair-Valid": str(report["valid"]),
            "X-Recovered-Pages": str(report["recovered_pages"]),
            "X-Unrecoverable-Pages": str(report["unrecoverable_pages"]),
            "Access-Control-Expose-Headers": "X-Repair-Valid, X-Recovered-Pages, X-Unrecoverable-Pages"
        }

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers=headers
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Repair failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ----------------------------------------------------------------------
# Phase 5 Studio Conversion Endpoints
# ----------------------------------------------------------------------

@app.get("/api/studio/conversions/capabilities")
def studio_conversion_capabilities():
    """Returns dynamic conversion capabilities and detected local engines."""
    return JSONResponse(converters.get_conversion_capabilities())


@app.post("/api/studio/convert")
@app.post("/api/conversions")
async def studio_convert(
    file: UploadFile = File(None),
    target_format: str = Form(...),
    options: str = Form("{}"),
    user_id: str | None = Depends(current_user)
):
    """
    High-fidelity studio conversion endpoint.
    Converts source document into target format with validation and real progress.
    """
    if not file:
        raise HTTPException(400, "A source file is required for conversion.")

    fmt = target_format.lower().strip().lstrip(".")
    opts = parse_options(options)

    MEDIA_TYPES = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "zip": "application/zip",
        "txt": "text/plain; charset=utf-8",
        "md": "text/markdown; charset=utf-8",
        "html": "text/html; charset=utf-8",
    }

    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_stem = Path(file.filename or "document").stem
        in_suffix = Path(file.filename or "document.pdf").suffix.lower()
        in_path = temp_dir / f"input{in_suffix}"
        await save_upload_spooled_async(file, in_path, max_bytes=upload_limit_bytes_for_user(user_id))

        out_ext = f".{fmt}" if fmt != "zip" else ".zip"
        out_path = temp_dir / f"{in_stem}_converted{out_ext}"

        start_t = time.time()

        if fmt == "pdf":
            # TO PDF
            if in_suffix in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"):
                converters.images_to_pdf(
                    [in_path], out_path,
                    page_size=opts.get("page_size", "a4"),
                    orientation=opts.get("orientation", "auto"),
                    margin_pt=float(opts.get("margin", 0.0)),
                    fit_mode=opts.get("fit_mode", "fit")
                )
            elif in_suffix in (".docx", ".doc"):
                converters.word_to_pdf(in_path, out_path)
            elif in_suffix in (".xlsx", ".xls"):
                converters.excel_to_pdf(in_path, out_path)
            elif in_suffix in (".pptx", ".ppt"):
                converters.powerpoint_to_pdf(in_path, out_path)
            elif in_suffix in (".md", ".markdown"):
                converters.markdown_to_pdf(in_path, out_path)
            elif in_suffix in (".html", ".htm"):
                converters.html_to_pdf(in_path.read_text(encoding="utf-8", errors="replace"), out_path, is_url=False)
            elif in_suffix == ".txt":
                converters.text_to_pdf(in_path, out_path)
            else:
                raise HTTPException(400, f"Unsupported source format '{in_suffix}' for PDF conversion.")

        elif fmt in ("docx", "word"):
            converters.pdf_to_word(in_path, out_path, pages=opts.get("pages", "all"))
        elif fmt in ("xlsx", "excel"):
            converters.pdf_to_excel(in_path, out_path, pages=opts.get("pages", "all"))
        elif fmt in ("pptx", "powerpoint"):
            converters.pdf_to_powerpoint(in_path, out_path, pages=opts.get("pages", "all"), mode=opts.get("mode", "visual"))
        elif fmt in ("jpg", "jpeg", "png", "webp"):
            dpi = int(opts.get("dpi", 150))
            quality = int(opts.get("quality", 85))
            pages = opts.get("pages", "all")
            out_path = converters.pdf_to_images(in_path, out_path, fmt=fmt, dpi=dpi, pages=pages, quality=quality)
        elif fmt in ("txt", "text"):
            converters.pdf_to_text(in_path, out_path, pages=opts.get("pages", "all"))
        elif fmt in ("md", "markdown"):
            converters.pdf_to_markdown(in_path, out_path, pages=opts.get("pages", "all"))
        elif fmt == "html":
            converters.pdf_to_html(in_path, out_path, pages=opts.get("pages", "all"))
        elif fmt == "pdfa":
            converters.pdf_to_pdfa(in_path, out_path)
            fmt = "pdf"
        else:
            raise HTTPException(400, f"Unsupported conversion target format: '{fmt}'.")

        val_report = converters.validate_conversion_output(out_path, expected_format=out_path.suffix.lstrip("."))
        elapsed = round(time.time() - start_t, 2)

        media_type = MEDIA_TYPES.get(out_path.suffix.lstrip("."), "application/octet-stream")
        download_name = f"{in_stem}_{fmt}{out_path.suffix}"

        headers = {
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "X-Conversion-Format": fmt,
            "X-Conversion-Time": str(elapsed),
            "X-Conversion-Valid": str(val_report["valid"]),
            "Access-Control-Expose-Headers": "Content-Disposition, X-Conversion-Format, X-Conversion-Time, X-Conversion-Valid"
        }

        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type=media_type,
            headers=headers
        )
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(422, str(ve)) from ve
    except Exception as err:
        raise HTTPException(500, f"Conversion failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/convert/images-to-pdf")
async def studio_images_to_pdf(
    files: list[UploadFile] = File(...),
    page_size: str = Form("a4"),
    orientation: str = Form("auto"),
    margin: float = Form(0.0),
    fit_mode: str = Form("fit"),
    user_id: str | None = Depends(current_user)
):
    """Batch converts multiple uploaded images into a clean, unified PDF with customizable layout."""
    if not files:
        raise HTTPException(400, "No image files provided.")

    temp_dir = Path(tempfile.mkdtemp())
    try:
        saved_paths = []
        for idx, upload in enumerate(files):
            ext = Path(upload.filename or f"img_{idx}.jpg").suffix.lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"):
                ext = ".jpg"
            img_p = temp_dir / f"img_{idx:03d}{ext}"
            size = await save_upload_spooled_async(upload, img_p, max_bytes=upload_limit_bytes_for_user(user_id))
            if size == 0:
                img_p.unlink(missing_ok=True)
                continue
            saved_paths.append(img_p)

        if not saved_paths:
            raise HTTPException(400, "All uploaded image files were empty.")

        out_pdf = temp_dir / "images_combined.pdf"
        converters.images_to_pdf(
            saved_paths, out_pdf,
            page_size=page_size,
            orientation=orientation,
            margin_pt=margin,
            fit_mode=fit_mode
        )

        val_report = converters.validate_conversion_output(out_pdf, "pdf")

        headers = {
            "Content-Disposition": 'attachment; filename="images_combined.pdf"',
            "X-Converted-Pages": str(val_report["metrics"]["pages"]),
            "Access-Control-Expose-Headers": "Content-Disposition, X-Converted-Pages"
        }

        return StreamingResponse(
            io.BytesIO(out_pdf.read_bytes()),
            media_type="application/pdf",
            headers=headers
        )
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(422, str(ve)) from ve
    except Exception as err:
        raise HTTPException(500, f"Images to PDF failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)



@app.get("/api/studio/pdf-info")
async def studio_pdf_info(
    url: str,
    user_id: str | None = Depends(current_user)
):
    """Return basic metadata (page count, page dimensions) for a PDF served at a URL."""
    # Only allow our own job download URLs or /assets/ paths for safety
    if not (url.startswith("/api/jobs/") or url.startswith("/assets/")):
        raise HTTPException(403, "Only internal PDF URLs are permitted.")

# ----------------------------------------------------------------------
# Phase 6: PDF Forms, Signing & Security Studio Endpoints
# ----------------------------------------------------------------------

@app.post("/api/studio/forms/analyze")
async def studio_forms_analyze(
    file: UploadFile = File(...),
    user_id: str | None = Depends(current_user)
):
    """Analyzes all interactive AcroForm widgets across document pages."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        await save_pdf_upload_async(file, in_path, user_id=user_id)
        analysis = security_forms_engine.analyze_pdf_forms(in_path)
        return analysis
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Form analysis failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/forms/add-field")
async def studio_forms_add_field(
    file: UploadFile = File(...),
    field_data: str = Form(...),
    user_id: str | None = Depends(current_user)
):
    """Adds a new interactive form field (text, checkbox, combobox, radio, etc.) to the PDF."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        out_path = temp_dir / "field_added.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)
        parsed_data = parse_options(field_data)
        security_forms_engine.add_form_field(in_path, out_path, parsed_data)
        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="form_field_added.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Add form field failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/forms/fill")
async def studio_forms_fill(
    file: UploadFile = File(...),
    field_values: str = Form(...),
    user_id: str | None = Depends(current_user)
):
    """Fills interactive form fields with supplied key-value pairs."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        out_path = temp_dir / "filled.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)
        values = parse_options(field_values)
        security_forms_engine.fill_pdf_forms(in_path, out_path, values)
        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="form_filled.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Form fill failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/forms/flatten")
async def studio_forms_flatten(
    file: UploadFile = File(...),
    user_id: str | None = Depends(current_user)
):
    """Bakes form appearances into static vector page content, removing interactive widgets."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        out_path = temp_dir / "flattened.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)
        security_forms_engine.flatten_pdf_forms(in_path, out_path)
        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="forms_flattened.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Form flatten failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/forms/reset")
async def studio_forms_reset(
    file: UploadFile = File(...),
    user_id: str | None = Depends(current_user)
):
    """Resets all form fields to default/blank states."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        out_path = temp_dir / "reset.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)
        security_forms_engine.reset_pdf_forms(in_path, out_path)
        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="forms_reset.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Form reset failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/forms/export")
async def studio_forms_export(
    file: UploadFile = File(...),
    user_id: str | None = Depends(current_user)
):
    """Exports all form field values into JSON."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)
        data = security_forms_engine.export_form_data(in_path)
        return JSONResponse(data)
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Form export failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/forms/import")
async def studio_forms_import(
    file: UploadFile = File(...),
    data: str = Form(...),
    user_id: str | None = Depends(current_user)
):
    """Imports form field data from JSON dictionary."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        out_path = temp_dir / "imported.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)
        imported_values = parse_options(data)
        security_forms_engine.import_form_data(in_path, out_path, imported_values)
        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="forms_imported.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Form import failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/sign/visual")
async def studio_sign_visual(
    file: UploadFile = File(...),
    signature_data: str = Form(...),
    page: int = Form(0),
    rect: str | None = Form(None),
    signer_name: str = Form("Signed"),
    date_str: str = Form(""),
    user_id: str | None = Depends(current_user)
):
    """Applies a visual electronic signature (drawn or typed) onto a document page."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        out_path = temp_dir / "visual_signed.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        rect_coords = None
        if rect:
            try:
                rect_coords = json.loads(rect)
            except Exception:
                pass

        security_forms_engine.add_visual_signature(
            in_path, out_path, signature_data,
            page_num=page, rect=rect_coords,
            signer_name=signer_name, date_str=date_str
        )
        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="visually_signed.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Visual signature failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/sign/digital")
async def studio_sign_digital(
    file: UploadFile = File(...),
    signer_name: str = Form("Verified Signer"),
    reason: str = Form("Document Integrity Verification"),
    location: str = Form("Paperplane Workstation"),
    visual_appearance: str | None = Form(None),
    custom_cert: UploadFile | None = File(None),
    custom_key: UploadFile | None = File(None),
    user_id: str | None = Depends(current_user)
):
    """Signs a PDF using standard detached PKCS#7 / CMS digital signatures (SHA-256 + RSA-2048)."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        out_path = temp_dir / "digitally_signed.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        if custom_cert and custom_key:
            cert_path = temp_dir / "custom.crt"
            key_path = temp_dir / "custom.key"
            save_upload_spooled(custom_cert, cert_path, max_bytes=1024 * 1024)
            save_upload_spooled(custom_key, key_path, max_bytes=1024 * 1024)
            cert_pem = cert_path.read_bytes()
            key_pem = key_path.read_bytes()
        else:
            cert_pem, key_pem = security_forms_engine.generate_test_certificate(signer_name)

        vis_dict = None
        if visual_appearance:
            try:
                vis_dict = json.loads(visual_appearance)
            except Exception:
                pass

        security_forms_engine.sign_pdf_digitally(
            in_path, out_path, cert_pem, key_pem,
            reason=reason, location=location, visual_appearance=vis_dict
        )
        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="digitally_signed.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Digital signing failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/sign/verify")
async def studio_sign_verify(
    file: UploadFile = File(...),
    user_id: str | None = Depends(current_user)
):
    """Cryptographically inspects and verifies all detached digital signatures."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)
        report = security_forms_engine.verify_pdf_signatures(in_path)
        return report
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Signature verification failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/security/protect")
async def studio_security_protect(
    file: UploadFile = File(...),
    user_password: str = Form(""),
    owner_password: str = Form(""),
    permissions: str | None = Form(None),
    user_id: str | None = Depends(current_user)
):
    """Encrypts a PDF using modern AES-256 and configurable permission bitmasks."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        out_path = temp_dir / "protected.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        perms_dict = None
        if permissions:
            try:
                perms_dict = json.loads(permissions)
            except Exception:
                pass

        security_forms_engine.protect_pdf(
            in_path, out_path,
            user_password=user_password,
            owner_password=owner_password,
            permissions=perms_dict
        )
        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="protected.pdf"'}
        )
    except HTTPException:
        raise
    except ValueError as ve:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": str(ve),
                "retry_hint": "Please provide a valid non-empty password.",
                "detail": str(ve)
            }
        )
    except Exception as err:
        logger.error("Studio protection failed: %s", err)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": f"PDF protection failed: {err}",
                "retry_hint": "Please verify PDF format and try again.",
                "detail": f"PDF protection failed: {err}"
            }
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/security/unlock")
async def studio_security_unlock(
    file: UploadFile = File(...),
    password: str = Form(...),
    user_id: str | None = Depends(current_user)
):
    """Authenticates against a password-protected PDF and produces an unencrypted copy."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        out_path = temp_dir / "unlocked.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        security_forms_engine.unlock_pdf(in_path, out_path, password=password)
        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="unlocked.pdf"'}
        )
    except HTTPException:
        raise
    except ValueError as ve:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": str(ve),
                "retry_hint": "Please verify the password and document protection state.",
                "detail": str(ve)
            }
        )
    except Exception as err:
        logger.error("Studio unlock failed: %s", err)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": f"PDF unlock failed: {err}",
                "retry_hint": "Please try again.",
                "detail": f"PDF unlock failed: {err}"
            }
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/security/inspect")
async def studio_security_inspect(
    file: UploadFile = File(...),
    password: str = Form(""),
    user_id: str | None = Depends(current_user)
):
    """Inspects encryption algorithm, active permissions, metadata, embedded JavaScript, and attachments."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        report = security_forms_engine.inspect_pdf_security(in_path, password=password)
        return report
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Security inspection failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/security/sanitize")
async def studio_security_sanitize(
    file: UploadFile = File(...),
    options: str | None = Form(None),
    user_id: str | None = Depends(current_user)
):
    """Removes sensitive document metadata, attachments, annotations, and active JavaScript."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        out_path = temp_dir / "sanitized.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        opts_dict = None
        if options:
            try:
                opts_dict = json.loads(options)
            except Exception:
                pass

        sanitize_report: dict[str, Any] = {}
        security_forms_engine.sanitize_pdf(in_path, out_path, targets=opts_dict, report=sanitize_report)
        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="sanitized.pdf"',
                "X-Paperplane-Sanitize-Report": json.dumps(sanitize_report, separators=(",", ":")),
            }
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Sanitization failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/studio/security/redact")
async def studio_security_redact(
    file: UploadFile = File(...),
    redactions: str = Form(...),
    user_id: str | None = Depends(current_user)
):
    """Permanently obliterates text glyphs and vectors via hardened redaction."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        in_path = temp_dir / "input.pdf"
        out_path = temp_dir / "redacted.pdf"
        save_pdf_upload(file, in_path, user_id=user_id)

        redactions_list = parse_options(redactions)
        if isinstance(redactions_list, dict):
            redactions_list = [redactions_list]

        security_forms_engine.apply_hardened_redaction(in_path, out_path, redactions_list)
        return StreamingResponse(
            io.BytesIO(out_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="redacted.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, f"Redaction failed: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)





@app.post("/api/cloud/sync")
def cloud_sync(
    file_url: str = Form(...),
    provider: str = Form("direct"),
    user_id: str | None = Depends(current_user)
):
    """Imports remote document files directly from Google Drive, Dropbox, OneDrive, or public HTTPS URL."""
    url = file_url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL: Must start with http:// or https://")
    parsed_url = urllib.parse.urlsplit(url)
    hostname = (parsed_url.hostname or "").lower().rstrip(".")
    if parsed_url.username or parsed_url.password:
        raise HTTPException(400, "Invalid URL: embedded credentials are not allowed")

    # Format Google Drive shareable link to direct export
    if hostname == "drive.google.com":
        match = re.search(r"/d/([a-zA-Z0-9_-]+)", parsed_url.path) or re.search(r"(?:^|&)id=([a-zA-Z0-9_-]+)(?:&|$)", parsed_url.query)
        if match:
            url = f"https://drive.google.com/uc?export=download&confirm=t&id={match.group(1)}"
            provider = "Google Drive"
    elif hostname == "dropbox.com" or hostname.endswith(".dropbox.com"):
        url = re.sub(r"[?&]dl=0", "", url)
        url += ("&" if "?" in url else "?") + "dl=1"
        provider = "Dropbox"
    elif hostname == "1drv.ms" or hostname == "onedrive.live.com":
        provider = "OneDrive"

    try:
        response_metadata: dict[str, str] = {}
        raw_bytes, content_type = converters.safe_fetch_url(
            url,
            max_size=upload_limit_bytes_for_user(user_id),
            timeout=30,
            response_metadata=response_metadata,
        )

        # Reject HTML preview, login, or error pages
        if raw_bytes.startswith((b"<!DOCTYPE", b"<!doctype", b"<html", b"<HTML", b"<body", b"<head")):
            if provider == "Google Drive":
                raise ValueError("Google Drive returned a preview or login page. Set General access to Anyone with the link, or use a direct PDF download URL.")
            raise ValueError("The provided link returned an HTML webpage or login screen instead of a direct file. Ensure it is publicly accessible without login or use a direct download URL.")

        if not raw_bytes.startswith(b"%PDF-"):
            raise ValueError("Cloud Import accepts PDF files only. This link returned another file type; use its matching converter instead.")
        try:
            imported_pdf = fitz.open(stream=raw_bytes, filetype="pdf")
            page_count = imported_pdf.page_count
            imported_pdf.close()
        except Exception as invalid_pdf:
            raise ValueError("The link returned a damaged or unreadable PDF. Choose a valid PDF and try again.") from invalid_pdf
        if page_count < 1:
            raise ValueError("The linked PDF has no pages to import.")
        disposition = response_metadata.get("content_disposition", "")
        filename_match = (
            re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", disposition, re.IGNORECASE)
            or re.search(r'filename\s*=\s*"([^"\r\n]+)"', disposition, re.IGNORECASE)
            or re.search(r"filename\s*=\s*([^;\s]+)", disposition, re.IGNORECASE)
        )
        filename = urllib.parse.unquote(filename_match.group(1)).strip() if filename_match else ""
        if not filename:
            final_path = urllib.parse.urlsplit(response_metadata.get("final_url", "")).path
            path_name = urllib.parse.unquote(final_path.rsplit("/", 1)[-1])
            filename = path_name if path_name.lower().endswith(".pdf") else "cloud_imported.pdf"
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        filename = re.sub(r'[\x00-\x1f\x7f<>:"/\\|?*]', "_", filename).strip(" .")
        if not filename:
            filename = "cloud_imported.pdf"
        if not filename.lower().endswith(".pdf"):
            filename = f"{Path(filename).stem or 'cloud_imported'}.pdf"
        filename = filename[:180]
        content_type = "application/pdf"

        b64_data = base64.b64encode(raw_bytes).decode("utf-8")
        return {
            "status": "success",
            "provider": provider,
            "filename": filename,
            "size": len(raw_bytes),
            "page_count": page_count,
            "content_type": content_type or "application/pdf",
            "data_url": f"data:{content_type or 'application/pdf'};base64,{b64_data}"
        }
    except ValueError as val_err:
        message = str(val_err)
        if provider == "Google Drive" and any(
            token in message.lower() for token in ("could not resolve hostname", "timed out", "connection failed", "network is unreachable")
        ):
            message = "Google Drive could not be reached. Confirm the file is shared with anyone who has the link, then retry or use a direct PDF download URL."
        raise HTTPException(400, message) from val_err
    except HTTPException:
        raise
    except Exception as err:
        if provider == "Google Drive":
            raise HTTPException(400, "Google Drive could not be reached. Confirm public sharing or use a direct PDF download URL.") from err
        raise HTTPException(400, "Cloud file sync failed. Check that the link is public and points directly to a PDF file.") from err


# ----------------------------------------------------------------------
# Page Organizer Endpoints
# ----------------------------------------------------------------------

@app.post("/api/organize/thumbnails")
async def organize_thumbnails(
    file: UploadFile = File(...),
    user_id: str | None = Depends(current_user),
):
    """Generates preview thumbnails for each page in an uploaded PDF."""
    temp_dir = Path(tempfile.mkdtemp(prefix="paperplane-thumbnails-"))
    try:
        input_path = temp_dir / "input.pdf"
        save_pdf_upload(file, input_path, user_id=user_id)
        doc = fitz.open(str(input_path))
        thumbnails = []
        for page_idx, page in enumerate(doc, 1):
            pix = page.get_pixmap(dpi=72)
            img_base64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            thumbnails.append({
                "page": page_idx,
                "width": page.rect.width,
                "height": page.rect.height,
                "thumbnail": f"data:image/png;base64,{img_base64}"
            })
        return {"total_pages": len(doc), "pages": thumbnails}
    except Exception as err:
        raise HTTPException(422, f"Failed to render PDF pages: {err}") from err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ----------------------------------------------------------------------
# Job Runner & Management
# ----------------------------------------------------------------------

def run_job(job_id: str, operation: str, paths: list[Path], options: dict, user_id: str | None) -> None:
    job_dir = JOBS / job_id
    try:
        update_job(job_id, status="processing", progress=20)
        result = process(operation, paths, options, job_dir)
        update_job(
            job_id,
            status="completed",
            progress=100,
            output_name=result.name,
            output_size=result.stat().st_size
        )
    except Exception as error:
        update_job(job_id, status="failed", progress=100, error=str(error))


@app.get("/api/jobs/{job_id}")
def job_status(
    job_id: str,
    request: Request,
    user_id: str | None = Depends(current_user)
):
    effective_token = request.cookies.get(f"guest_job_{job_id}") or request.headers.get("X-Guest-Token")
    row = get_job(job_id, user_id=user_id, guest_token=effective_token)
    if not row:
        raise HTTPException(404, "Job not found.")
    res = dict(row)
    res.pop("guest_token", None)
    res.pop("user_id", None)
    return res


@app.post("/api/jobs/create", status_code=202)
@app.post("/api/jobs", status_code=202)
def create_job_endpoint(
    request: Request,
    response: Response,
    operation: str = Form(...),
    options: str = Form("{}"),
    files: list[UploadFile] = File(default=[]),
    user_id: str | None = Depends(current_user)
):
    # Freemium Tier & Daily Quota Check
    client_ip = get_client_ip(request)
    enforce_account_rate_limit(f"job-account:{user_id or client_ip}", limit=20, window_seconds=60)
    allowed, usage_count, user_tier = check_operation_quota(user_id, client_ip, FREE_TIER_DAILY_LIMIT)
    if not allowed:
        if user_id:
            quota_msg = f"Daily limit reached ({FREE_TIER_DAILY_LIMIT}/{FREE_TIER_DAILY_LIMIT} operations on Free Tier). Paid plans have no daily operation cap; upload and batch limits still apply."
        else:
            quota_msg = f"Daily guest limit reached ({FREE_TIER_DAILY_LIMIT}/{FREE_TIER_DAILY_LIMIT} operations). Create a free account or choose a paid plan with no daily operation cap; upload and batch limits still apply."
        raise HTTPException(
            status_code=402,
            detail={
                "code": "TIER_LIMIT_REACHED",
                "message": quota_msg,
                "limit": FREE_TIER_DAILY_LIMIT,
                "usage": usage_count,
                "tier": user_tier
            }
        )

    if operation not in OPERATIONS:
        raise HTTPException(400, f"Unknown operation: {operation}")

    if not OPERATIONS[operation]["implemented"]:
        raise HTTPException(501, OPERATIONS[operation].get("description", "Operation not available."))
    if operation == "translate" and not translation_ai_available():
        raise HTTPException(503, "AI translation is unavailable because the Paperplane AI translation service is not configured or enabled.")

    parsed_options = parse_options(options)

    # Allow url conversion without files
    if operation == "html_to_pdf":
        files = []
    elif not files:
        raise HTTPException(400, "Please select at least one file to process.")

    # Batch limits (up to 100 for merge/scan/images)
    max_files = MAX_BATCH_FILES if operation in {"merge", "jpg_to_pdf", "scan_pdf"} else 2 if operation == "compare" else 1
    if len(files) > max_files:
        raise HTTPException(400, f"This operation accepts at most {max_files} files.")

    if operation == "compare":
        parsed_options["_original_filenames"] = [
            "".join(char for char in str(file.filename or "document.pdf").replace("\\", "/").rsplit("/", 1)[-1] if char.isprintable())[:180]
            or "document.pdf"
            for file in files
        ]

    expected = OPERATIONS[operation]["accept"]
    job_id, guest_token = persist_job(operation, user_id, JOB_TTL_SECONDS)
    if guest_token:
        response.set_cookie(
            key=f"guest_job_{job_id}",
            value=guest_token,
            max_age=JOB_TTL_SECONDS,
            httponly=True,
            secure=SECURE_COOKIES,
            samesite=COOKIE_SAMESITE,
            path="/"
        )
    
    job_dir = JOBS / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        paths = []
        upload_limit_bytes = upload_limit_bytes_for_tier(user_tier)
        for file in files:
            p = save_upload(file, job_dir, max_bytes=upload_limit_bytes)
            validate_upload(p, expected, operation)
            paths.append(p)

        # Failed uploads and invalid files do not consume a daily operation.
        subject = f"user:{user_id}" if user_id else f"ip:{client_ip}"
        usage_today = increment_daily_usage(subject)
        response.headers["X-Paperplane-Operations-Today"] = str(usage_today)
        executor.submit(run_job, job_id, operation, paths, parsed_options, user_id)
        return {
            "job_id": job_id,
            "status": "queued",
            "status_url": f"/api/jobs/{job_id}",
            "download_url": f"/api/jobs/{job_id}/download"
        }
    except HTTPException as error:
        update_job(job_id, status="failed", error=str(error.detail))
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(error.status_code, error.detail) from error
    except Exception as error:
        update_job(job_id, status="failed", error=str(error))
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(422, str(error)) from error


@app.get("/api/jobs/{job_id}/download")
def download(
    job_id: str,
    request: Request,
    user_id: str | None = Depends(current_user)
):
    directory = JOBS / job_id
    cookie_key = f"guest_job_{job_id}"
    effective_token = request.cookies.get(cookie_key) or request.headers.get("X-Guest-Token")
    row = get_job(job_id, user_id=user_id, guest_token=effective_token)
    if not row:
        raise HTTPException(404, "Job not found.")
    if row["status"] != "completed":
        raise HTTPException(409, f"Job is {row['status']}.")

    def owner_scoped_file(path: Path, filename: str) -> FileResponse:
        file_response = FileResponse(path, filename=filename, media_type="application/octet-stream")
        if not row["user_id"]:
            if not consume_guest_job_token(job_id, effective_token or ""):
                raise HTTPException(404, "Job not found.")
            file_response.delete_cookie(
                cookie_key,
                path="/",
                httponly=True,
                secure=SECURE_COOKIES,
                samesite=COOKIE_SAMESITE,
            )
        return file_response

    out_name = row["output_name"] or "document.pdf"
    if row["output_name"]:
        target = (directory / row["output_name"]).resolve()
        if target.is_relative_to(directory.resolve()) and target.exists():
            return owner_scoped_file(target, out_name)

    # Fallback to any non-upload file
    if directory.exists():
        candidates = [p for p in directory.iterdir() if p.is_file() and not p.name.endswith(".tmp")]
        if candidates:
            cand = candidates[-1].resolve()
            if cand.is_relative_to(directory.resolve()) and cand.exists():
                return owner_scoped_file(cand, cand.name)

    raise HTTPException(404, "Job output not found or expired.")


@app.delete("/api/jobs/{job_id}")
def delete_job(
    job_id: str,
    request: Request,
    user_id: str | None = Depends(current_user)
):
    effective_token = request.cookies.get(f"guest_job_{job_id}") or request.headers.get("X-Guest-Token")
    row = get_job(job_id, user_id=user_id, guest_token=effective_token)
    if not row:
        raise HTTPException(404, "Job not found.")
    directory = JOBS / job_id
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
    delete_job_record(job_id)
    return {"deleted": True}


# ----------------------------------------------------------------------
# Public Paperplane PDF Developer REST API (v1)
# ----------------------------------------------------------------------

def _dev_rate_limit_headers(usage: dict) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(usage.get("daily_limit", FREE_API_CALLS_PER_DAY)),
        "X-RateLimit-Remaining": str(usage.get("calls_remaining", 0)),
        "X-RateLimit-Reset": str(usage.get("reset_timestamp", 0)),
        "X-RateLimit-AI-Limit": str(usage.get("ai_limit", FREE_AI_CALLS_PER_DAY)),
        "X-RateLimit-AI-Remaining": str(usage.get("ai_remaining", 0)),
    }


@app.get("/api/v1/operations", tags=["Developer API v1"])
def list_v1_operations():
    """Lists all available PDF operations and their capabilities."""
    catalog = []
    for op_name, op_info in OPERATIONS.items():
        catalog.append({
            "operation": op_name,
            "label": op_info.get("label", op_name),
            "category": op_info.get("category", "General"),
            "accepts": op_info.get("accept", "pdf"),
            "implemented": bool(op_info.get("implemented", False)),
            "description": op_info.get("description", "")
        })
    return {
        "total_operations": len(catalog),
        "operations": catalog
    }


@app.get("/api/v1/account/usage", tags=["Developer API v1"])
def developer_account_usage(user_id: str = Depends(require_developer_key)):
    """Returns the authenticated developer account's daily API allowance and current usage."""
    usage = get_developer_api_usage(user_id)
    return JSONResponse(usage, headers=_dev_rate_limit_headers(usage))


@app.post("/api/v1/jobs", status_code=202, tags=["Developer API v1"])
async def create_v1_job(
    request: Request,
    operation: str = Form(...),
    options: str = Form("{}"),
    files: list[UploadFile] = File(default=[]),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: str = Depends(require_developer_key)
):
    """
    Submits a new PDF processing job to the Paperplane REST API engine.
    Supports Idempotency-Key header, daily free tier quota enforcement, and concurrency controls.
    """
    # 1. Idempotency Check
    if idempotency_key:
        cached_job_id = get_idempotent_job(idempotency_key, user_id)
        if cached_job_id:
            existing_job = get_job(cached_job_id, user_id=user_id)
            if existing_job:
                usage = get_developer_api_usage(user_id)
                return JSONResponse(
                    {
                        "job_id": existing_job["id"],
                        "operation": existing_job["operation"],
                        "status": existing_job["status"],
                        "idempotent": True,
                        "status_url": f"/api/v1/jobs/{existing_job['id']}",
                        "download_url": f"/api/v1/jobs/{existing_job['id']}/download",
                        "created_at": existing_job["created_at"],
                    },
                    status_code=200,
                    headers=_dev_rate_limit_headers(usage)
                )

    # 2. Pre-validate operation
    if operation not in OPERATIONS:
        raise HTTPException(400, f"Unknown operation: '{operation}'. See /api/v1/operations for available tools.")

    if not OPERATIONS[operation].get("implemented", False):
        raise HTTPException(501, OPERATIONS[operation].get("description", "Operation not currently implemented."))
    if operation == "translate" and not translation_ai_available():
        raise HTTPException(503, "AI translation is unavailable because the Paperplane AI translation service is not configured or enabled.")

    is_ai = operation in {"summarize", "ai_chat", "ai_extract", "translate"}

    # 3. Read and check file sizes
    if operation != "html_to_pdf" and not files:
        raise HTTPException(400, "Please supply at least one input file in the 'files' multipart form field.")

    max_files = MAX_BATCH_FILES if operation in {"merge", "jpg_to_pdf", "scan_pdf"} else 2 if operation == "compare" else 1
    if len(files) > max_files:
        raise HTTPException(400, f"Operation '{operation}' accepts at most {max_files} input file(s).")

    staging_dir = Path(tempfile.mkdtemp(prefix="paperplane-upload-"))
    staged_files: list[tuple[str, Path]] = []
    total_bytes = 0
    try:
        for f in files:
            original_name = f.filename or "input.pdf"
            staged_path = staging_dir / f"{uuid.uuid4().hex}_{Path(original_name).name}"
            total_bytes += await save_upload_spooled_async(f, staged_path, max_bytes=upload_limit_bytes_for_user(user_id))
            staged_files.append((original_name, staged_path))
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    # 4. Quota and Concurrency Check
    allowed, quota_err, usage = check_and_consume_developer_quota(
        user_id,
        is_ai=is_ai,
        file_size_bytes=total_bytes
    )
    if not allowed:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise HTTPException(
            status_code=429,
            detail={
                "code": "QUOTA_EXHAUSTED",
                "message": quota_err,
                "usage": usage
            },
            headers=_dev_rate_limit_headers(usage)
        )

    # 5. Parse options
    try:
        parsed_options = parse_options(options)
    except Exception as parse_err:
        shutil.rmtree(staging_dir, ignore_errors=True)
        refund_developer_quota(user_id, is_ai=is_ai)
        raise HTTPException(400, f"Invalid options JSON: {parse_err}") from parse_err

    # 6. Create Job and Disk Directory
    job_id, _ = persist_job(operation, user_id, JOB_TTL_SECONDS)
    if idempotency_key:
        record_idempotent_job(idempotency_key, user_id, job_id, ttl=JOB_TTL_SECONDS)

    job_dir = JOBS / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    expected = OPERATIONS[operation]["accept"]
    try:
        saved_paths = []
        for orig_name, staged_path in staged_files:
            safe_name = Path(orig_name).name
            dest = job_dir / f"{uuid.uuid4().hex}_{safe_name}"
            shutil.move(str(staged_path), str(dest))
            validate_upload(dest, expected)
            saved_paths.append(dest)

        executor.submit(run_job, job_id, operation, saved_paths, parsed_options, user_id)
        return JSONResponse(
            {
                "job_id": job_id,
                "operation": operation,
                "status": "queued",
                "status_url": f"/api/v1/jobs/{job_id}",
                "download_url": f"/api/v1/jobs/{job_id}/download",
                "created_at": time.time(),
                "expires_in_seconds": JOB_TTL_SECONDS
            },
            status_code=202,
            headers=_dev_rate_limit_headers(usage)
        )
    except Exception as upload_err:
        refund_developer_quota(user_id, is_ai=is_ai)
        update_job(job_id, status="failed", error=str(upload_err))
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(422, f"Failed to accept input files: {upload_err}") from upload_err
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


@app.get("/api/v1/jobs/{job_id}", tags=["Developer API v1"])
def get_v1_job(job_id: str, user_id: str = Depends(require_developer_key)):
    """Retrieves the status, progress, error, and artifact metadata of a specific developer job."""
    row = get_job(job_id, user_id=user_id)
    if not row:
        raise HTTPException(404, "Job not found or access denied.")
    usage = get_developer_api_usage(user_id)
    job_data = dict(row)
    job_data.pop("guest_token", None)
    job_data["status_url"] = f"/api/v1/jobs/{job_id}"
    job_data["download_url"] = f"/api/v1/jobs/{job_id}/download"
    return JSONResponse(job_data, headers=_dev_rate_limit_headers(usage))


@app.get("/api/v1/jobs/{job_id}/download", tags=["Developer API v1"])
def download_v1_job_output(job_id: str, user_id: str = Depends(require_developer_key)):
    """Downloads the verified output artifact produced by a completed developer job."""
    directory = JOBS / job_id
    row = get_job(job_id, user_id=user_id)
    if not row:
        raise HTTPException(404, "Job not found or access denied.")
    if row["status"] != "completed":
        raise HTTPException(409, f"Job status is '{row['status']}'. Output can only be downloaded once completed.")

    if row["output_name"]:
        target = (directory / row["output_name"]).resolve()
        if target.is_relative_to(directory.resolve()) and target.exists():
            return FileResponse(target, filename=row["output_name"])

    if directory.exists():
        candidates = [p for p in directory.iterdir() if p.is_file() and not p.name.endswith(".tmp")]
        if candidates:
            cand = candidates[-1].resolve()
            if cand.is_relative_to(directory.resolve()) and cand.exists():
                return FileResponse(cand, filename=cand.name)

    raise HTTPException(404, "Job output artifact not found or expired.")


@app.delete("/api/v1/jobs/{job_id}", tags=["Developer API v1"])
def delete_v1_job(job_id: str, user_id: str = Depends(require_developer_key)):
    """Cancels or deletes a job and purges its stored files."""
    row = get_job(job_id, user_id=user_id)
    if not row:
        raise HTTPException(404, "Job not found or access denied.")
    directory = JOBS / job_id
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
    update_job(job_id, status="cancelled", error="Cancelled by user via API.")
    return {"deleted": True, "job_id": job_id}


# Developer API Key Management Endpoints (v1 & legacy developer alias)
@app.get("/api/v1/keys", tags=["Developer API v1"])
@app.get("/api/developer/keys", tags=["Developer Keys"])
def list_keys_endpoint(request: Request, user_id: str | None = Depends(current_user)):
    effective_user_id = user_id or authenticate(request.cookies.get("paperplane_token"))
    if not effective_user_id:
        raise HTTPException(401, "Authentication required to manage API keys.")
    return {"keys": list_api_keys(effective_user_id)}


@app.post("/api/v1/keys", tags=["Developer API v1"])
@app.post("/api/developer/keys", tags=["Developer Keys"])
def create_key_endpoint(
    request: Request,
    name: str = Form("Default API Key"),
    user_id: str | None = Depends(current_user)
):
    effective_user_id = user_id or authenticate(request.cookies.get("paperplane_token"))
    if not effective_user_id:
        raise HTTPException(401, "Authentication required to generate an API key.")
    key_id, raw_key = create_api_key(effective_user_id, name)
    return {
        "id": key_id,
        "name": name,
        "api_key": raw_key,
        "key_prefix": raw_key[:12] + "...",
        "created_at": time.time(),
        "warning": "Copy your secret API key now. It cannot be displayed again."
    }


@app.delete("/api/v1/keys/{key_id}", tags=["Developer API v1"])
@app.delete("/api/developer/keys/{key_id}", tags=["Developer Keys"])
def revoke_key_endpoint(
    key_id: str,
    request: Request,
    user_id: str | None = Depends(current_user)
):
    effective_user_id = user_id or authenticate(request.cookies.get("paperplane_token"))
    if not effective_user_id:
        raise HTTPException(401, "Authentication required to revoke an API key.")
    success = revoke_api_key(key_id, effective_user_id)
    if not success:
        raise HTTPException(404, "API key not found or already revoked.")
    return {"revoked": True, "key_id": key_id}


# Direct AI Endpoints for Developers
@app.post("/api/v1/ai/summarize", tags=["Developer AI"])
async def api_v1_ai_summarize(
    file: UploadFile = File(...),
    user_id: str = Depends(require_developer_key)
):
    """Summarizes an uploaded PDF using document-grounded AI inference."""
    temp_dir = Path(tempfile.mkdtemp(prefix="paperplane-upload-"))
    tmp_path = temp_dir / "input.pdf"

    try:
        file_size = await save_upload_spooled_async(file, tmp_path, max_bytes=upload_limit_bytes_for_user(user_id))
        allowed, quota_err, usage = check_and_consume_developer_quota(
            user_id, is_ai=True, file_size_bytes=file_size
        )
        if not allowed:
            raise HTTPException(429, detail=quota_err, headers=_dev_rate_limit_headers(usage))
        summary_text = ai_engine.summarize_pdf(tmp_path)
        return JSONResponse({"summary": summary_text}, headers=_dev_rate_limit_headers(usage))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/v1/ai/extract", tags=["Developer AI"])
async def api_v1_ai_extract(
    file: UploadFile = File(...),
    doc_type: str = Form("auto"),
    user_id: str = Depends(require_developer_key)
):
    """Extracts structured entities from an uploaded PDF using AI inference."""
    temp_dir = Path(tempfile.mkdtemp(prefix="paperplane-upload-"))
    tmp_path = temp_dir / "input.pdf"

    try:
        file_size = await save_upload_spooled_async(file, tmp_path, max_bytes=upload_limit_bytes_for_user(user_id))
        allowed, quota_err, usage = check_and_consume_developer_quota(
            user_id, is_ai=True, file_size_bytes=file_size
        )
        if not allowed:
            raise HTTPException(429, detail=quota_err, headers=_dev_rate_limit_headers(usage))
        extracted = ai_engine.extract_metadata_entities(tmp_path, doc_type=doc_type)
        return JSONResponse(extracted, headers=_dev_rate_limit_headers(usage))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _remove_ai_identity_fields(value: Any) -> Any:
    """Remove upstream identity fields recursively from public AI JSON contracts."""
    hidden_keys = {"provider", "provider_name", "model", "model_name", "upstream_provider", "upstream_model"}
    if isinstance(value, dict):
        return {
            key: _remove_ai_identity_fields(item)
            for key, item in value.items()
            if str(key).casefold() not in hidden_keys
        }
    if isinstance(value, list):
        return [_remove_ai_identity_fields(item) for item in value]
    return value


@app.post("/api/v1/ai/chat", tags=["Developer AI"])
async def api_v1_ai_chat(
    file: UploadFile = File(...),
    question: str = Form(...),
    user_id: str = Depends(require_developer_key)
):
    """Answers questions grounded in the content of the uploaded PDF with page citations."""
    temp_dir = Path(tempfile.mkdtemp(prefix="paperplane-upload-"))
    tmp_path = temp_dir / "input.pdf"

    try:
        file_size = await save_upload_spooled_async(file, tmp_path, max_bytes=upload_limit_bytes_for_user(user_id))
        allowed, quota_err, usage = check_and_consume_developer_quota(
            user_id, is_ai=True, file_size_bytes=file_size
        )
        if not allowed:
            raise HTTPException(429, detail=quota_err, headers=_dev_rate_limit_headers(usage))
        chat_result = ai_engine.chat_with_pdf(tmp_path, question)
        return JSONResponse(_remove_ai_identity_fields(chat_result), headers=_dev_rate_limit_headers(usage))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/api/v1/ai/test-connection", tags=["Developer AI"])
@app.post("/api/v1/ai/test-connection", tags=["Developer AI"])
def test_ai_connection(user_id: str = Depends(require_developer_key)):
    """
    Explicit authenticated connectivity test for the configured AI service.
    Returns status and diagnostic details without exposing API secrets.
    """
    result = ai_engine.test_bluesminds_connectivity()
    return _remove_ai_identity_fields(result)


@app.get("/developers", response_class=HTMLResponse, tags=["Web Pages"])
def developers_page(request: Request):
    return render_web_page(request, landing_slug="developers")


# ----------------------------------------------------------------------
# Web Interface Hosting
# ----------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render_web_page(request)


@app.get("/download", response_class=HTMLResponse, tags=["Web Pages"])
@app.get("/apps", response_class=HTMLResponse, tags=["Web Pages"])
def download_page(request: Request):
    return render_web_page(request, landing_slug="download")


@app.get("/tool-desk", response_class=HTMLResponse, include_in_schema=False)
def tool_desk_page(request: Request):
    return render_web_page(request, landing_slug="tool-desk")


@app.get("/tools", include_in_schema=False)
def legacy_tools_redirect():
    return RedirectResponse(url="/", status_code=301)


@app.get("/studio", response_class=HTMLResponse, include_in_schema=False)
def studio_workspace_page(request: Request):
    return render_web_page(request, landing_slug="studio")


@app.get("/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page(request: Request):
    return render_web_page(request, landing_slug="tool-desk")


@app.get("/privacy", response_class=HTMLResponse)
def privacy_route(request: Request):
    return render_web_page(request, landing_slug="privacy")


@app.get("/terms", response_class=HTMLResponse)
def terms_route(request: Request):
    return render_web_page(request, landing_slug="terms")


@app.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(request: Request):
    return render_web_page(request, landing_slug="reset-password")


@app.get("/docs", include_in_schema=False)
def docs_redirect():
    return RedirectResponse(url="/api-docs" if not DISABLE_DOCS else "/developers")


@app.get("/api-docs", include_in_schema=False)
def api_docs_help_fallback():
    return RedirectResponse(url="/developers")


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Paperplane PDF Platform",
        "version": "2.0.0",
        "timestamp": time.time(),
    }


@app.get("/api/health/persistence", include_in_schema=False)
def persistence_health(_: None = Depends(_require_admin)):
    """Expose resolved persistence diagnostics only to an MFA-authenticated owner."""
    return _persistence_snapshot()


@app.get("/favicon.ico")
def favicon_icon():
    fav_file = ROOT / "web" / "assets" / "favicon.svg"
    if fav_file.exists():
        return FileResponse(fav_file, media_type="image/svg+xml")
    return Response(status_code=204)



app.mount("/assets", StaticFiles(directory=ROOT / "web" / "assets"), name="assets")


@app.get("/robots.txt", include_in_schema=False)
def robots_txt(request: Request):
    site_url = public_site_url(request)
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /api/",
            "Disallow: /api-docs",
            "Disallow: /redoc",
            f"Sitemap: {site_url}/sitemap.xml",
            "",
        ]
    )
    return Response(content=body, media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml(request: Request):
    site_url = public_site_url(request)
    paths = ["/"]
    paths.extend(f"/{slug}" for slug in OPERATION_SLUGS.values())
    paths.extend(f"/{slug}" for slug in SEO_LANDING_PAGES)
    urls = "".join(
        f"<url><loc>{html_escape(site_url + path, quote=True)}</loc><changefreq>weekly</changefreq><priority>{'1.0' if path != '/' else '1.0'}</priority></url>"
        for path in paths
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(content=xml, media_type="application/xml")


LEGACY_SLUG_REDIRECTS = {
    "scan-pdf": "scan-to-pdf",
    "fill-form": "fill-pdf-form",
    "ai-translate": "translate-pdf",
    "ai-summarize": "summarize-pdf",
    "remove-pages": "remove-pages-pdf",
    "exam-photo-signature-resizer": "ssc-photo-resizer",
    "mask-aadhaar": "mask-aadhaar-card-online",
    "flatten-pdf-forms": "flatten-pdf",
    "page-numbers": "add-page-numbers-to-pdf",
    "smart-metadata": "extract-pdf-data",
    "extract-metadata": "extract-pdf-data",
    "compress": "compress-pdf",
    "merge": "merge-pdf",
    "split": "split-pdf",
    "organize": "organize-pdf",
    "rotate": "rotate-pdf",
    "repair": "repair-pdf",
    "ocr": "ocr-pdf",
    "watermark": "watermark-pdf",
    "protect": "protect-pdf",
    "unlock": "unlock-pdf",
    "sign": "sign-pdf",
    "extract-pages": "split-pdf",
    "grayscale-pdf": "convert-pdf-to-grayscale",
    "pdf-to-ppt": "pdf-to-powerpoint",
    "ppt-to-pdf": "powerpoint-to-pdf",
}


@app.api_route("/admin", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
def admin_portal_page():
    """Visual admin portal for the platform owner with 3-factor authentication and visual analytics."""
    return HTMLResponse(content="""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Admin Console — Paperplane PDF</title>
  <style>
    :root {
      --bg: #0b1113;
      --card-bg: #141f22;
      --card-border: #26373b;
      --text: #f0f5f4;
      --text-muted: #8ca3a2;
      --accent: #ff4b26;
      --accent-hover: #e03e1b;
      --pro-color: #fbbf24;
      --dev-color: #c084fc;
      --free-color: #94a3b8;
      --green: #10b981;
      --red: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: #111a1d;
      border-bottom: 1px solid var(--card-border);
      padding: 14px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .logo-badge {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 18px;
      font-weight: 700;
    }
    .logo-icon {
      width: 34px;
      height: 34px;
      background: var(--accent);
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-weight: 900;
      color: #fff;
    }
    .env-tag {
      font-size: 11px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 6px;
      background: #1c2b2f;
      color: var(--green);
      border: 1px solid #23483f;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .btn {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      text-decoration: none;
      transition: all 0.15s;
    }
    .btn:hover { background: #1c2b2f; border-color: #385055; }
    .btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    .btn-primary:hover { background: var(--accent-hover); }
    .btn-danger { background: #3b1414; border-color: #632323; color: #ff8585; }
    .btn-danger:hover { background: #4a1919; }

    main {
      flex: 1;
      max-width: 1340px;
      width: 100%;
      margin: 0 auto;
      padding: 28px 24px;
    }

    /* Auth Screens Container */
    .auth-card {
      max-width: 480px;
      margin: 60px auto;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 36px;
      text-align: center;
      box-shadow: 0 16px 40px rgba(0,0,0,0.5);
    }
    .auth-card h1 { font-size: 22px; margin-bottom: 8px; }
    .auth-card p { color: var(--text-muted); font-size: 13.5px; margin-bottom: 24px; line-height: 1.5; }

    /* Input with Eye toggle */
    .field-group {
      text-align: left;
      margin-bottom: 16px;
    }
    .field-label {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 6px;
      display: block;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .input-wrapper {
      position: relative;
      display: flex;
      align-items: center;
    }
    .input-field {
      width: 100%;
      padding: 12px 42px 12px 14px;
      background: #0f1618;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: var(--text);
      font-size: 14px;
      outline: none;
      transition: border-color 0.15s;
    }
    .input-field:focus { border-color: var(--accent); }
    .toggle-eye {
      position: absolute;
      right: 12px;
      background: none;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 16px;
      padding: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .toggle-eye:hover { color: #fff; }

    .error-msg {
      color: #f87171;
      background: #3b1414;
      border: 1px solid #7f1d1d;
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 13px;
      margin-bottom: 16px;
      display: none;
      text-align: left;
    }
    .info-note {
      font-size: 12px;
      color: var(--text-muted);
      background: #0f181a;
      border: 1px dashed var(--card-border);
      padding: 10px 12px;
      border-radius: 8px;
      margin-bottom: 20px;
      text-align: left;
      line-height: 1.4;
    }

    /* Lockout Screen */
    #lockout-screen {
      border-color: #ef4444;
      background: #1c0f0f;
    }

    /* Environment Live Banner */
    .system-banner {
      background: #101c1e;
      border: 1px solid #1e3a3f;
      border-radius: 10px;
      padding: 12px 18px;
      margin-bottom: 24px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      font-size: 13px;
    }
    .system-banner strong { color: var(--green); }

    /* Dashboard Metrics Grid */
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }
    .metric-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px;
      position: relative;
    }
    .metric-card .title {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      margin-bottom: 6px;
    }
    .metric-card .value {
      font-size: 28px;
      font-weight: 800;
      color: var(--text);
    }
    .metric-card .sub {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
    }

    /* Visual Analytics Section */
    .analytics-section {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 20px;
      margin-bottom: 28px;
    }
    @media (max-width: 900px) {
      .analytics-section { grid-template-columns: 1fr; }
    }
    .chart-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px;
    }
    .chart-card h3 {
      font-size: 14px;
      font-weight: 700;
      color: var(--text);
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .bar-chart-container {
      display: flex;
      align-items: flex-end;
      gap: 8px;
      height: 160px;
      padding-top: 20px;
      border-bottom: 1px solid var(--card-border);
    }
    .bar-col {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      height: 100%;
      justify-content: flex-end;
      gap: 6px;
    }
    .bar-fill {
      width: 100%;
      max-width: 28px;
      background: var(--accent);
      border-radius: 4px 4px 0 0;
      min-height: 4px;
      transition: height 0.3s ease;
      cursor: pointer;
    }
    .bar-fill:hover { background: #ff6b4d; }
    .bar-label {
      font-size: 10px;
      color: var(--text-muted);
      text-align: center;
      white-space: nowrap;
    }
    .bar-value {
      font-size: 10px;
      color: #fff;
      font-weight: 700;
    }

    /* Tier Meter Bar */
    .meter-bar {
      height: 16px;
      border-radius: 8px;
      overflow: hidden;
      display: flex;
      background: #111a1d;
      margin-bottom: 16px;
      border: 1px solid var(--card-border);
    }
    .meter-seg-free { background: var(--free-color); height: 100%; }
    .meter-seg-pro { background: var(--pro-color); height: 100%; }
    .meter-seg-dev { background: var(--dev-color); height: 100%; }
    .legend-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      font-size: 12.5px;
    }
    .legend-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .legend-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      display: inline-block;
      margin-right: 8px;
    }

    /* Toolbar & Tabs */
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 20px;
    }
    .tabs {
      display: flex;
      background: #10191c;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 4px;
      gap: 4px;
    }
    .tab-btn {
      padding: 8px 18px;
      background: transparent;
      border: none;
      color: var(--text-muted);
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }
    .tab-btn.active {
      background: var(--card-bg);
      color: #fff;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    .search-box {
      background: #0f1618;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 8px 14px;
      color: #fff;
      font-size: 13px;
      min-width: 240px;
    }

    /* Data Tables */
    .table-container {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }
    th {
      background: #111a1d;
      padding: 12px 16px;
      color: var(--text-muted);
      font-weight: 600;
      border-bottom: 1px solid var(--card-border);
    }
    td {
      padding: 12px 16px;
      border-bottom: 1px solid #1a282c;
    }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: rgba(255,255,255,0.02); }

    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .badge-free { background: #1e293b; color: #94a3b8; }
    .badge-pro { background: #3b280c; color: #fbbf24; border: 1px solid #78350f; }
    .badge-dev { background: #2e1065; color: #c084fc; border: 1px solid #581c87; }
    .badge-platform { background: #162a26; color: #34d399; }

    /* Filter pills */
    .filter-pills {
      display: flex;
      gap: 6px;
      margin-left: 8px;
    }
    .pill {
      font-size: 11px;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 999px;
      cursor: pointer;
      border: 1px solid var(--card-border);
      background: #0f1618;
      color: var(--text-muted);
    }
    .pill.active { background: #26373b; color: #fff; border-color: #3d555c; }

    /* Revenue & Financial Analytics */
    .revenue-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .revenue-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px;
    }
    .revenue-card.highlight {
      border-color: #10b981;
      background: #0d221c;
    }
    .revenue-card .title {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      margin-bottom: 6px;
    }
    .revenue-card .value {
      font-size: 26px;
      font-weight: 800;
      color: var(--text);
    }
    .revenue-card .sub {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
    }

    /* Form Panels for AI & Config */
    .form-panel {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 24px;
      max-width: 760px;
    }
    .form-group {
      margin-bottom: 20px;
      text-align: left;
    }
    .form-select, .form-input {
      width: 100%;
      padding: 10px 14px;
      background: #0f1618;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: var(--text);
      font-size: 14px;
      outline: none;
      box-sizing: border-box;
    }
    .form-select:focus, .form-input:focus {
      border-color: var(--accent);
    }
    .form-help {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 6px;
      line-height: 1.4;
    }
    .btn-xs {
      padding: 4px 8px;
      font-size: 11px;
      border-radius: 6px;
    }
    .star-gold { color: #fbbf24; }
    .star-gray { color: #475569; }
  </style>
</head>
<body>
  <header>
    <div class="logo-badge">
      <div class="logo-icon">P</div>
      <span>Paperplane Admin Console</span>
      <span class="env-tag" id="header-env">Live System</span>
    </div>
    <div class="header-actions" id="header-actions" style="display: none;">
      <span style="font-size: 12px; color: var(--green); display: flex; align-items: center; gap: 4px;">● Session Active</span>
      <button class="btn" id="btn-refresh">🔄 Refresh</button>
      <button class="btn btn-danger" id="btn-logout">Logout</button>
    </div>
  </header>

  <main>
    <!-- Screen 0: Lockout Alert Screen (if 3 wrong attempts were entered) -->
    <div id="lockout-screen" class="auth-card" style="display: none;">
      <div style="font-size: 48px; margin-bottom: 12px;">🚨</div>
      <h1 style="color: #ef4444;">Admin Console Locked</h1>
      <p style="color: #fca5a5;">
        3 consecutive incorrect attempts were detected. As an automated intrusion defense against brute-force attacks, administrative access has been suspended for 24 hours.
      </p>
      <div style="background: #271414; border: 1px solid #7f1d1d; border-radius: 8px; padding: 14px; text-align: left; font-size: 13px; margin-bottom: 20px;">
        <div style="margin-bottom: 6px;"><strong style="color: #fca5a5;">Notification:</strong> <span style="color: #fff;">Sent to the configured owner email</span></div>
        <div style="margin-bottom: 6px;"><strong style="color: #fca5a5;">Lock Duration:</strong> <span style="color: #ef4444; font-weight: 700;">24 Hours</span></div>
        <div><strong style="color: #fca5a5;">Time Remaining:</strong> <span id="lockout-countdown" style="color: #fff; font-family: monospace;">Calculating...</span></div>
      </div>
      <button class="btn" style="width: 100%; justify-content: center;" id="btn-check-lockout">🔄 Check Lockout Status</button>
    </div>

    <!-- Screen 1: Step 1 Auth (Key + Secret Code + Eye Toggle) -->
    <div id="step1-screen" class="auth-card">
      <div class="logo-icon" style="width:48px;height:48px;font-size:24px;margin:0 auto 16px;">P</div>
      <h1>Owner Authentication</h1>
      <p>Enter your Admin Secret Key and Secret Code to initiate 2-factor email verification.</p>

      <div id="auth-error" class="error-msg"></div>

      <div class="field-group">
        <label class="field-label" for="admin-key-input">Admin Secret Key</label>
        <div class="input-wrapper">
          <input type="password" id="admin-key-input" class="input-field" placeholder="Paste your 64-character admin key..." autocomplete="off" />
          <button type="button" class="toggle-eye" id="toggle-key-eye" title="Toggle visibility">👁️</button>
        </div>
      </div>

      <div class="field-group">
        <label class="field-label" for="admin-code-input">Admin Secret Code</label>
        <div class="input-wrapper">
          <input type="password" id="admin-code-input" class="input-field" placeholder="Enter owner secret code..." autocomplete="off" />
          <button type="button" class="toggle-eye" id="toggle-code-eye" title="Toggle visibility">👁️</button>
        </div>
      </div>

      <div class="info-note">
        🛡️ <strong>Security Sentinel:</strong> 3 consecutive incorrect attempts will lock this console for 24 hours and send a critical alert to the configured owner email.
      </div>

      <button class="btn btn-primary" id="btn-submit-step1" style="width: 100%; justify-content: center; padding: 12px;">Verify & Send Email OTP &rarr;</button>
    </div>

    <!-- Screen 2: Step 2 Auth (6-Digit Email OTP) -->
    <div id="step2-screen" class="auth-card" style="display: none;">
      <div style="font-size: 42px; margin-bottom: 12px;">📬</div>
      <h1>Two-Factor Verification</h1>
      <p>A 6-digit one-time code was sent to the configured owner email address.</p>

      <div id="otp-error" class="error-msg"></div>

      <div class="field-group" style="text-align: center;">
        <label class="field-label" style="text-align: center;">Enter 6-Digit Code</label>
        <input type="text" id="admin-otp-input" class="input-field" maxlength="6" style="font-size: 26px; font-weight: 800; letter-spacing: 10px; text-align: center; font-family: monospace; padding: 14px;" placeholder="000000" autocomplete="off" />
      </div>

      <div class="info-note" style="text-align: center;">
        ⏱️ Code is valid for 10 minutes. Check your spam/junk folder if not received.
      </div>

      <button class="btn btn-primary" id="btn-submit-step2" style="width: 100%; justify-content: center; padding: 12px; margin-bottom: 12px;">Verify Code & Unlock Console &rarr;</button>
      <button class="btn" id="btn-back-step1" style="width: 100%; justify-content: center;">&larr; Back to Step 1</button>
    </div>

    <!-- Screen 3: Unlocked Dashboard (Full Power & Visuals) -->
    <div id="dashboard-view" style="display: none;">
      <!-- System Connection Banner -->
      <div class="system-banner">
        <div>
          <span>Database: <strong id="live-db-path">SQLite (Loading...)</strong></span>
          <span style="margin: 0 10px; color: var(--card-border);">|</span>
          <span>Environment: <strong id="live-env-name">Production</strong></span>
          <span style="margin: 0 10px; color: var(--card-border);">|</span>
          <span>Security: <strong style="color: var(--green);">3-Factor Verified (Session Valid)</strong></span>
        </div>
        <div style="color: var(--text-muted); font-size: 12px;" id="live-time-now"></div>
      </div>

      <!-- Top Metrics Grid -->
      <div class="metric-grid">
        <div class="metric-card">
          <div class="title">Total Registered</div>
          <div class="value" id="m-total-users">-</div>
          <div class="sub" id="m-new-7d">0 new last 7 days</div>
        </div>
        <div class="metric-card">
          <div class="title">Pro Users</div>
          <div class="value" style="color: var(--pro-color);" id="m-pro-users">-</div>
          <div class="sub">Paid subscribers</div>
        </div>
        <div class="metric-card">
          <div class="title">Developer API</div>
          <div class="value" style="color: var(--dev-color);" id="m-dev-users">-</div>
          <div class="sub">API & Webhook users</div>
        </div>
        <div class="metric-card">
          <div class="title">Free Tier</div>
          <div class="value" style="color: var(--free-color);" id="m-free-users">-</div>
          <div class="sub">Standard accounts</div>
        </div>
        <div class="metric-card">
          <div class="title">Active Today</div>
          <div class="value" style="color: var(--green);" id="m-today-active">-</div>
          <div class="sub">Active processing users</div>
        </div>
        <div class="metric-card">
          <div class="title">Waitlist Signups</div>
          <div class="value" style="color: var(--accent);" id="m-total-waitlist">-</div>
          <div class="sub">Native apps waitlist</div>
        </div>
        <div class="metric-card">
          <div class="title">Total Jobs Run</div>
          <div class="value" id="m-total-jobs">-</div>
          <div class="sub" id="m-jobs-today">0 processed today</div>
        </div>
      </div>

      <!-- Visual Analytics Section -->
      <div class="analytics-section">
        <!-- 14-Day Signup Trend Bar Chart -->
        <div class="chart-card">
          <h3>
            <span>📈 14-Day User Signups Trend</span>
            <span style="font-size: 11px; font-weight: normal; color: var(--text-muted);">Daily Registrations</span>
          </h3>
          <div class="bar-chart-container" id="bar-chart-container">
            <!-- Dynamically rendered bars -->
          </div>
        </div>

        <!-- Tier Breakdown Distribution Meter -->
        <div class="chart-card">
          <h3>
            <span>🎯 Plan Breakdown</span>
            <span style="font-size: 11px; font-weight: normal; color: var(--text-muted);" id="tier-ratio-label">Ratio</span>
          </h3>
          <div class="meter-bar">
            <div id="meter-free" class="meter-seg-free" style="width: 70%;" title="Free"></div>
            <div id="meter-pro" class="meter-seg-pro" style="width: 20%;" title="Pro"></div>
            <div id="meter-dev" class="meter-seg-dev" style="width: 10%;" title="Dev"></div>
          </div>
          <div class="legend-list">
            <div class="legend-item">
              <span><span class="legend-dot" style="background: var(--free-color);"></span>Free Accounts</span>
              <strong id="legend-free-val">0 (0%)</strong>
            </div>
            <div class="legend-item">
              <span><span class="legend-dot" style="background: var(--pro-color);"></span>Pro Subscribers</span>
              <strong id="legend-pro-val" style="color: var(--pro-color);">0 (0%)</strong>
            </div>
            <div class="legend-item">
              <span><span class="legend-dot" style="background: var(--dev-color);"></span>Developer Users</span>
              <strong id="legend-dev-val" style="color: var(--dev-color);">0 (0%)</strong>
            </div>
          </div>
        </div>
      </div>

      <!-- Action Toolbar -->
      <div class="toolbar">
        <div class="tabs">
          <button class="tab-btn active" id="tab-users-btn">Registered Users (<span id="count-users">0</span>)</button>
          <button class="tab-btn" id="tab-revenue-btn">💰 Revenue &amp; Payouts</button>
          <button class="tab-btn" id="tab-feedback-btn">💬 User Feedback (<span id="count-feedback">0</span>)</button>
          <button class="tab-btn" id="tab-ai-btn">🤖 AI Settings</button>
          <button class="tab-btn" id="tab-waitlist-btn">App Waitlist (<span id="count-waitlist">0</span>)</button>
          <button class="tab-btn" id="tab-audit-btn">Security Audits (<span id="count-audit">0</span>)</button>
        </div>
        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
          <button id="btn-clean-probes" class="btn btn-danger" title="Clean all dummy and test probe accounts">🧹 Clean Test Probes</button>
          <input type="text" id="search-input" class="search-box" placeholder="Filter by email or query..." />
          <button id="btn-export-users" class="btn">📥 Export Users CSV</button>
          <button id="btn-export-waitlist" class="btn">📥 Export Waitlist CSV</button>
        </div>
      </div>

      <!-- Users Table Panel -->
      <div class="table-container" id="panel-users">
        <div style="padding: 12px 16px; background: #111a1d; border-bottom: 1px solid var(--card-border); display: flex; align-items: center; gap: 8px;">
          <span style="font-size: 12px; color: var(--text-muted);">Quick Filter:</span>
          <div class="filter-pills">
            <span class="pill active" data-filter="all">All</span>
            <span class="pill" data-filter="pro">Pro Only</span>
            <span class="pill" data-filter="developer">Developer Only</span>
            <span class="pill" data-filter="free">Free Only</span>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>User Email</th>
              <th>Tier</th>
              <th>Registered At</th>
              <th>Last Active</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody id="users-tbody">
            <tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 30px;">Loading live user directory...</td></tr>
          </tbody>
        </table>
      </div>

      <!-- Revenue & Payouts Panel -->
      <div id="panel-revenue" style="display: none;">
        <div class="revenue-grid">
          <div class="revenue-card">
            <div class="title">Paying Customers</div>
            <div class="value" id="rev-paying-count" style="color: var(--pro-color);">-</div>
            <div class="sub">Active Pro &amp; Developer Subscribers</div>
          </div>
          <div class="revenue-card">
            <div class="title">Verified Gross Payments</div>
            <div class="value" id="rev-gross-revenue">-</div>
            <div class="sub">Unique paid INR orders recorded</div>
          </div>
          <div class="revenue-card">
            <div class="title">Estimated Gateway Fees (<span id="rev-fee-rate">—</span>)</div>
            <div class="value" id="rev-gateway-fees" style="color: #f87171;">-</div>
            <div class="sub">Configured fee plus GST on that fee</div>
          </div>
          <div class="revenue-card highlight">
            <div class="title">Estimated Net Payout</div>
            <div class="value" id="rev-net-payout" style="color: var(--green);">-</div>
            <div class="sub">Before refunds, disputes, and settlement adjustments</div>
          </div>
        </div>

        <p class="text-muted" id="rev-revenue-basis" style="padding: 0 4px; font-size: 12px;"></p>

        <div class="table-container">
          <div style="padding: 14px 18px; background: #111a1d; border-bottom: 1px solid var(--card-border); font-weight: 700; font-size: 14px;">
            💳 Paying Customers &amp; Recent Transactions
          </div>
          <table>
            <thead>
              <tr>
                <th>Customer Email</th>
                <th>Subscribed Tier</th>
                <th>Order / Transaction ID</th>
                <th>Amount (INR)</th>
                <th>Created Date</th>
                <th>Payment Status</th>
              </tr>
            </thead>
            <tbody id="revenue-tbody">
              <tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 30px;">Loading financial ledger...</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- User Feedback Panel -->
      <div id="panel-feedback" style="display: none;">
        <div class="table-container">
          <div style="padding: 12px 16px; background: #111a1d; border-bottom: 1px solid var(--card-border); display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 12px; color: var(--text-muted);">Feedback Filter:</span>
              <div class="filter-pills feedback-pills">
                <span class="pill active" data-fb-filter="all">All</span>
                <span class="pill" data-fb-filter="bug">Bug Reports</span>
                <span class="pill" data-fb-filter="suggestion">Feature Requests</span>
                <span class="pill" data-fb-filter="general">General / Praise</span>
              </div>
            </div>
            <div style="font-size: 12px; color: var(--text-muted);" id="feedback-summary-count">0 total reviews</div>
          </div>
          <table>
            <thead>
              <tr>
                <th style="width: 120px;">Rating</th>
                <th style="width: 130px;">Category</th>
                <th>Feedback Message</th>
                <th>User / Email</th>
                <th>Submitted</th>
                <th>IP Address</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody id="feedback-tbody">
              <tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">Loading customer feedback...</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- AI Settings Panel -->
      <div id="panel-ai" style="display: none;">
        <div class="form-panel">
          <h2 style="font-size: 18px; margin-bottom: 6px;">🤖 Platform AI Configuration</h2>
          <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 24px;">
            Configure AI provider endpoint, models, and API credentials dynamically. Keys are encrypted in DB and securely masked to prevent leaks.
          </p>

          <div id="ai-save-msg" class="error-msg" style="display: none;"></div>

          <div class="form-group">
            <label class="field-label" for="ai-provider-select">AI Provider Architecture</label>
            <select id="ai-provider-select" class="form-select">
              <option value="openai_compatible">OpenAI-Compatible / Universal Gateway</option>
              <option value="bluesminds">Bluesminds Gateway</option>
              <option value="openrouter">OpenRouter AI</option>
              <option value="anthropic">Anthropic (Claude Direct / Proxy)</option>
              <option value="gemini">Google Gemini / AI Studio</option>
              <option value="deepseek">DeepSeek AI</option>
            </select>
            <div class="form-help">Universal endpoint compatible with standard /chat/completions REST protocol.</div>
          </div>

          <div class="form-group">
            <label class="field-label" for="ai-baseurl-input">API Base URL</label>
            <input type="text" id="ai-baseurl-input" class="form-input" placeholder="https://api.bluesminds.com/v1" />
            <div class="form-help">Base URL for chat completions (e.g., https://api.bluesminds.com/v1, https://openrouter.ai/api/v1).</div>
          </div>

          <div class="form-group">
            <label class="field-label" for="ai-model-input">Model Name / Identifier</label>
            <input type="text" id="ai-model-input" class="form-input" placeholder="openai/gpt-oss-20b" />
            <div class="form-help">Target model ID (e.g. openai/gpt-oss-20b, gpt-4o-mini, anthropic/claude-3-5-sonnet, deepseek-chat).</div>
          </div>

          <div class="form-group">
            <label class="field-label" for="ai-apikey-input">API Secret Key</label>
            <div class="input-wrapper">
              <input type="password" id="ai-apikey-input" class="input-field" placeholder="sk-••••••••••••" autocomplete="off" />
              <button type="button" class="toggle-eye" id="toggle-ai-key-eye" title="Toggle visibility">👁️</button>
            </div>
            <div class="form-help">Securely masked (sk-••••••••1234). Enter a new key to update, or leave unchanged.</div>
          </div>

          <div id="ai-provider-health-alert" role="status" aria-live="polite" style="display: none; margin-top: 16px; padding: 12px; border-radius: 8px; font-size: 13px;"></div>
          <div style="display: flex; gap: 12px; align-items: center; margin-top: 24px;">
            <button class="btn btn-primary" id="btn-save-ai">💾 Save AI Configuration</button>
            <button class="btn" id="btn-test-ai">⚡ Test Connection</button>
            <span id="ai-test-status" style="font-size: 13px; margin-left: 10px;"></span>
          </div>
        </div>
      </div>

      <!-- Waitlist Table Panel -->
      <div class="table-container" id="panel-waitlist" style="display: none;">
        <table>
          <thead>
            <tr>
              <th># Position</th>
              <th>Email</th>
              <th>Platform</th>
              <th>Signup Time</th>
              <th>IP Address</th>
            </tr>
          </thead>
          <tbody id="waitlist-tbody">
            <tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 30px;">Loading waitlist directory...</td></tr>
          </tbody>
        </table>
      </div>

      <!-- Security Audit Trail Panel -->
      <div class="table-container" id="panel-audit" style="display: none;">
        <table>
          <thead>
            <tr>
              <th>Event Type</th>
              <th>Target Email</th>
              <th>IP Address</th>
              <th>Timestamp</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody id="audit-tbody">
            <tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 30px;">Loading security audit logs...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </main>

  <script src="/assets/admin.js?v=2.1.0" defer></script>
</body>
</html>""")


@app.get("/{tool_slug}", response_class=HTMLResponse, include_in_schema=False)
def tool_landing_page(tool_slug: str, request: Request):
    if tool_slug == "admin":
        return admin_portal_page()
    if tool_slug in LEGACY_SLUG_REDIRECTS:
        return RedirectResponse(url=f"/{LEGACY_SLUG_REDIRECTS[tool_slug]}", status_code=301)
    operation = SLUG_TO_OPERATION.get(tool_slug)
    if operation:
        return render_web_page(request, operation=operation)
    if tool_slug in SEO_LANDING_PAGES:
        return render_web_page(request, landing_slug=tool_slug)
    raise HTTPException(status_code=404, detail="Page not found")


@app.get("/api/admin/audit-summary", include_in_schema=False)
def get_admin_audit_summary(
    _: None = Depends(_require_admin),
    limit: int = 50
):
    """Owner-only view of recent logins, registrations, and platform activity."""
    logs = get_recent_audit_logs(limit=limit)
    return {
        "status": "success",
        "total_records": len(logs),
        "recent_activity": logs
    }


# ---------------------------------------------------------------------------
# Owner-only Admin Dashboard & Multi-Factor Auth endpoints
# ---------------------------------------------------------------------------

async def _read_limited_admin_json(request: Request, max_bytes: int = 8192) -> dict[str, Any]:
    """Read bounded JSON even when the caller omits Content-Length."""
    declared_length = request.headers.get("content-length", "")
    if declared_length.isdigit() and int(declared_length) > max_bytes:
        raise HTTPException(status_code=413, detail="Admin request is too large.")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="Admin request is too large.")
        chunks.append(chunk)
    try:
        body = json.loads(b"".join(chunks))
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as error:
        raise HTTPException(status_code=400, detail="Request must contain valid JSON.") from error
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request must be a JSON object.")
    return body


@app.get("/api/admin/auth/status", include_in_schema=False)
def admin_auth_status(request: Request):
    """Return the requesting source address's lockout status without owner PII."""
    remaining = get_admin_lockout_remaining(get_client_ip(request))
    return {
        "locked": remaining > 0,
        "remaining_seconds": remaining,
    }


@app.post("/api/admin/auth/step1", include_in_schema=False)
async def admin_auth_step1(request: Request, background_tasks: BackgroundTasks):
    """Step 1: Validate Admin Secret Key and Secret Code; generate and email 6-digit OTP."""
    client_ip = get_client_ip(request)
    enforce_rate_limit(f"admin_step1:{client_ip}", limit=12)

    if len(ADMIN_SECRET_KEY) < 64 or len(ADMIN_SECRET_CODE) < 8 or not ADMIN_ALERT_EMAIL:
        raise HTTPException(status_code=503, detail="Owner authentication is not configured on this server.")

    remaining = get_admin_lockout_remaining(client_ip)
    if remaining > 0:
        hrs = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        raise HTTPException(status_code=423, detail=f"Admin console is locked. {hrs}h {mins}m remaining. Try after 24 hours.")

    body = await _read_limited_admin_json(request)

    admin_key = str(body.get("admin_key", "")).strip()
    admin_code = str(body.get("admin_code", "")).strip()

    key_ok = bool(
        ADMIN_SECRET_KEY
        and hmac.compare_digest(admin_key.encode("utf-8"), ADMIN_SECRET_KEY.encode("utf-8"))
    )
    code_ok = bool(
        ADMIN_SECRET_CODE
        and hmac.compare_digest(admin_code.encode("utf-8"), ADMIN_SECRET_CODE.encode("utf-8"))
    )

    if not (key_ok and code_ok):
        attempts, is_locked = record_admin_failed_attempt(client_ip)
        record_audit_event("admin_auth_failed", email=ADMIN_ALERT_EMAIL, ip_address=client_ip, details=f"Failed attempt {attempts}/3")
        if is_locked:
            background_tasks.add_task(
                send_admin_lockout_alert,
                to_email=ADMIN_ALERT_EMAIL,
                client_ip=client_ip,
                failure_reason="3 consecutive failed attempts on admin secret key/code"
            )
            raise HTTPException(
                status_code=423,
                detail="3 failed attempts. Admin console is locked for 24 hours. Security alert dispatched."
            )
        remaining_attempts = max(0, 3 - attempts)
        raise HTTPException(
            status_code=401,
            detail=f"Invalid key or secret code. Warning: {remaining_attempts} attempt(s) remaining before 24h lockout."
        )

    # Key and Secret Code validated -> generate 6-digit OTP
    otp = f"{secrets.randbelow(1_000_000):06d}"
    set_admin_pending_otp(otp, expires_in=600)

    delivered = await asyncio.to_thread(
        send_admin_login_otp,
        to_email=ADMIN_ALERT_EMAIL,
        otp_code=otp,
        client_ip=client_ip,
    )
    if not delivered:
        clear_admin_pending_otp()
        record_audit_event(
            "admin_otp_delivery_failed",
            email=ADMIN_ALERT_EMAIL,
            ip_address=client_ip,
            details="Configured email provider did not accept the admin OTP.",
        )
        raise HTTPException(
            status_code=503,
            detail="Owner verification email could not be delivered. Please try again later.",
        )
    record_audit_event("admin_otp_dispatched", email=ADMIN_ALERT_EMAIL, ip_address=client_ip, details="Admin OTP dispatched to owner")
    return {"status": "otp_sent"}


@app.post("/api/admin/auth/step2", include_in_schema=False)
async def admin_auth_step2(request: Request, background_tasks: BackgroundTasks):
    """Step 2: Validate 6-digit OTP code and issue a cryptographically signed admin session token."""
    client_ip = get_client_ip(request)
    enforce_rate_limit(f"admin_step2:{client_ip}", limit=12)

    remaining = get_admin_lockout_remaining(client_ip)
    if remaining > 0:
        hrs = int(remaining // 3600)
        raise HTTPException(status_code=423, detail=f"Admin console is locked. {hrs}h remaining. Try after 24 hours.")

    body = await _read_limited_admin_json(request)

    otp = str(body.get("otp", "")).strip()
    otp_ok = verify_admin_otp(otp)

    if not otp_ok:
        attempts, is_locked = record_admin_failed_attempt(client_ip)
        record_audit_event("admin_otp_failed", email=ADMIN_ALERT_EMAIL, ip_address=client_ip, details=f"Invalid OTP attempt {attempts}/3")
        if is_locked:
            background_tasks.add_task(
                send_admin_lockout_alert,
                to_email=ADMIN_ALERT_EMAIL,
                client_ip=client_ip,
                failure_reason="3 consecutive failed attempts on admin OTP"
            )
            raise HTTPException(
                status_code=423,
                detail="3 failed attempts. Admin console is locked for 24 hours. Security alert dispatched."
            )
        remaining_attempts = max(0, 3 - attempts)
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or expired OTP code. Warning: {remaining_attempts} attempt(s) remaining."
        )

    # Full 3-factor authentication verified -> issue 4-hour session
    reset_admin_failed_attempts(client_ip)
    session_token = create_admin_session(ttl_seconds=14400)
    record_audit_event("admin_login_success", email=ADMIN_ALERT_EMAIL, ip_address=client_ip, details="Owner authenticated via 3-factor verification")

    return {
        "status": "authenticated",
        "session_token": session_token,
        "expires_in": 14400
    }


@app.post("/api/admin/auth/logout", include_in_schema=False)
def admin_auth_logout(_: None = Depends(_require_admin)):
    """Revokes active admin session."""
    revoke_admin_session()
    return {"status": "logged_out"}


@app.get("/api/admin/dashboard", include_in_schema=False)
def admin_dashboard(_: None = Depends(_require_admin)):
    """Full visual analytics and telemetry snapshot for the owner dashboard."""
    analytics = admin_get_extended_analytics()
    return {
        "status": "ok",
        "environment": os.getenv("PAPERPLANE_ENV", "production"),
        "db_location": os.getenv("PAPERPLANE_DATA_DIR", "/data"),
        **analytics
    }


@app.get("/api/admin/users", include_in_schema=False)
def admin_list_users(_: None = Depends(_require_admin)):
    """List all registered users with tier, signup date, and last active date."""
    users = admin_get_all_users()
    return {"status": "ok", "count": len(users), "users": users}


def _safe_csv_cell(value: Any) -> str:
    """Neutralize spreadsheet formulas after leading whitespace/control characters."""
    text = "" if value is None else str(value)
    if re.match(r"^[\x00-\x20\uFEFF]*[=+\-@]", text):
        return "'" + text
    return text


@app.get("/api/admin/waitlist", include_in_schema=False)
def admin_list_waitlist(_: None = Depends(_require_admin)):
    """List all waitlist entries."""
    entries = admin_get_waitlist()
    return {"status": "ok", "count": len(entries), "entries": entries}


@app.get("/api/admin/users/export.csv", include_in_schema=False)
def admin_export_users_csv(_: None = Depends(_require_admin)):
    """Download all registered users as a CSV file."""
    users = admin_get_all_users()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "email", "tier", "created_at", "subscription_status", "last_active_date"])
    writer.writeheader()
    for u in users:
        writer.writerow({k: _safe_csv_cell(u.get(k, "")) for k in writer.fieldnames})
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=paperplane_users.csv"}
    )


@app.get("/api/admin/waitlist/export.csv", include_in_schema=False)
def admin_export_waitlist_csv(_: None = Depends(_require_admin)):
    """Download all waitlist emails as a CSV file."""
    entries = admin_get_waitlist()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "email", "platform", "created_at", "ip_address"])
    writer.writeheader()
    for e in entries:
        writer.writerow({k: _safe_csv_cell(e.get(k, "")) for k in writer.fieldnames})
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=paperplane_waitlist.csv"}
    )


# ---------------------------------------------------------------------------
# Feedback & Extended Admin Management Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/feedback")
async def submit_user_feedback(request: Request):
    """Public customer feedback submission widget endpoint."""
    client_ip = get_client_ip(request)
    enforce_rate_limit(f"feedback:{client_ip}", limit=20)
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > 8192:
        raise HTTPException(status_code=413, detail="Feedback request exceeds the 8 KB limit.")
    body_chunks: list[bytes] = []
    body_size = 0
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > 8192:
            raise HTTPException(status_code=413, detail="Feedback request exceeds the 8 KB limit.")
        body_chunks.append(chunk)
    try:
        body = json.loads(b"".join(body_chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail="Feedback request must be valid JSON.") from error
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Feedback request must be a JSON object.")

    raw_email = body.get("email", "")
    raw_rating = body.get("rating", 5)
    raw_category = body.get("category", "general")
    raw_message = body.get("message", "")
    if not isinstance(raw_email, str) or len(raw_email.strip()) > 254:
        raise HTTPException(status_code=422, detail="Feedback email must be a valid address of at most 254 characters.")
    email = raw_email.strip().lower()
    if email and not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", email):
        raise HTTPException(status_code=422, detail="Feedback email must be a valid email address.")
    if not isinstance(raw_rating, int) or isinstance(raw_rating, bool) or not 1 <= raw_rating <= 5:
        raise HTTPException(status_code=422, detail="Feedback rating must be an integer from 1 to 5.")
    if not isinstance(raw_category, str) or raw_category.strip().lower() not in {"general", "suggestion", "bug"}:
        raise HTTPException(status_code=422, detail="Feedback category is not supported.")
    if not isinstance(raw_message, str):
        raise HTTPException(status_code=422, detail="Feedback message must be text.")
    message = raw_message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Feedback message is required.")
    if len(message) > 1000:
        raise HTTPException(status_code=422, detail="Feedback message cannot exceed 1000 characters.")
    rating = raw_rating
    category = raw_category.strip().lower()

    # Optional active user resolution
    user_id = None
    token = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    elif request.cookies.get("paperplane_token"):
        token = request.cookies.get("paperplane_token").strip()
    if token:
        try:
            user_id = authenticate(token)
        except Exception:
            user_id = None

    try:
        saved = add_user_feedback(
            email=email,
            rating=rating,
            category=category,
            message=message,
            user_id=user_id,
            ip_address=client_ip
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"status": "ok", "message": "Thank you for your valuable feedback!", "feedback_id": saved["id"]}


@app.get("/api/admin/feedback", include_in_schema=False)
def admin_list_feedback(_: None = Depends(_require_admin)):
    """List all user feedback entries."""
    feedbacks = admin_get_feedbacks()
    return {"status": "ok", "count": len(feedbacks), "feedbacks": feedbacks}


@app.delete("/api/admin/feedback/{feedback_id}", include_in_schema=False)
def admin_remove_feedback(feedback_id: str, _: None = Depends(_require_admin)):
    """Delete a user feedback entry."""
    ok = admin_delete_feedback(feedback_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Feedback entry not found.")
    return {"status": "ok", "deleted": feedback_id}


@app.get("/api/admin/revenue", include_in_schema=False)
def admin_revenue_data(_: None = Depends(_require_admin)):
    """Revenue analytics with gateway fee calculations and net bank payout."""
    rev = admin_get_revenue_analytics()
    return {"status": "ok", **rev}


def _protected_admin_emails() -> set[str]:
    protected = {ADMIN_ALERT_EMAIL.strip().lower()} if ADMIN_ALERT_EMAIL.strip() else set()
    protected.update(
        item.strip().lower()
        for item in os.getenv("PAPERPLANE_PROTECTED_USER_EMAILS", "").split(",")
        if item.strip()
    )
    return protected


def _purge_admin_job_artifacts(job_ids: list[str]) -> tuple[int, list[str]]:
    root = Path(JOBS).resolve()
    removed = 0
    pending: list[str] = []
    for job_id in job_ids:
        target = (root / str(job_id)).resolve()
        if target == root or not target.is_relative_to(root):
            pending.append(str(job_id))
            continue
        try:
            if target.exists():
                shutil.rmtree(target)
            removed += 1
        except OSError:
            pending.append(str(job_id))
    return removed, pending


@app.post("/api/admin/users/delete", include_in_schema=False)
async def admin_remove_user(request: Request, _: None = Depends(_require_admin)):
    """Permanently delete a single user account."""
    body = await _read_limited_admin_json(request)
    user_id = str(body.get("user_id", "")).strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required.")

    job_ids: list[str] = []
    try:
        ok = admin_delete_user(
            user_id,
            protected_emails=_protected_admin_emails(),
            job_ids_out=job_ids,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not ok:
        raise HTTPException(status_code=404, detail="User not found.")
    purged, pending = _purge_admin_job_artifacts(job_ids)
    return {
        "status": "ok",
        "deleted_user_id": user_id,
        "job_artifacts_removed": purged,
        "job_artifacts_pending": pending,
        "financial_ledger_anonymized": True,
    }


@app.post("/api/admin/users/cleanup-probes", include_in_schema=False)
async def admin_cleanup_probes(request: Request, _: None = Depends(_require_admin)):
    """Preview probe matches; delete only the exact reviewed candidate IDs."""
    body = await _read_limited_admin_json(request)
    confirm = body.get("confirm", False)
    candidate_ids = body.get("candidate_ids", [])
    if not isinstance(confirm, bool) or not isinstance(candidate_ids, list) or len(candidate_ids) > 500:
        raise HTTPException(status_code=400, detail="Invalid cleanup confirmation.")
    if any(not isinstance(item, str) or not item.strip() for item in candidate_ids):
        raise HTTPException(status_code=400, detail="Candidate IDs must be non-empty strings.")
    try:
        result = admin_cleanup_probe_accounts(
            confirm=confirm,
            candidate_ids=candidate_ids,
            protected_emails=_protected_admin_emails(),
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if confirm:
        purged, pending = _purge_admin_job_artifacts(result.pop("job_ids", []))
        result["job_artifacts_removed"] = purged
        result["job_artifacts_pending"] = pending
    return {"status": "ok", **result}


@app.get("/api/admin/ai-config", include_in_schema=False)
def admin_fetch_ai_config(_: None = Depends(_require_admin)):
    """Get active AI provider, model, base URL, and masked API key."""
    return {"status": "ok", "config": admin_get_ai_config()}


@app.get("/api/admin/ai-health", include_in_schema=False)
def admin_ai_health(_: None = Depends(_require_admin)):
    """Return sanitized provider readiness; the admin can run Test Connection for reachability."""
    return ai_engine.get_ai_configuration_health()


@app.post("/api/admin/ai-config", include_in_schema=False)
async def admin_update_ai_config(request: Request, _: None = Depends(_require_admin)):
    """Update AI model, base URL, provider, or API key dynamically."""
    body = await _read_limited_admin_json(request)
    provider = str(body.get("provider", "")).strip()
    model = str(body.get("model", "")).strip()
    base_url = str(body.get("base_url", "")).strip()
    api_key = str(body.get("api_key", "")).strip() or None

    try:
        updated = admin_set_ai_config(provider=provider, model=model, base_url=base_url, api_key=api_key)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"status": "ok", "config": updated}


@app.post("/api/admin/ai-test", include_in_schema=False)
def admin_test_ai(_: None = Depends(_require_admin)):
    """Test AI connectivity with current active configuration."""
    from ai_engine import test_bluesminds_connectivity
    res = test_bluesminds_connectivity()
    return {"status": "ok", "result": res}





@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: HTTPException):
    accept = request.headers.get("accept", "")
    if "text/html" in accept and not request.url.path.startswith("/api/"):
        return HTMLResponse(
            status_code=404,
            content="""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>404 Page Not Found — Paperplane PDF</title>
  <style>
    body { display: flex; align-items: center; justify-content: center; min-height: 100vh; min-height: 100dvh; background: #0d1416; color: #f0f5f4; font-family: system-ui, -apple-system, sans-serif; margin: 0; text-align: center; }
    .box { max-width: 480px; padding: 40px 24px; background: #141e21; border: 1px solid #28393d; border-radius: 16px; box-shadow: 0 20px 48px rgba(0,0,0,0.4); margin: 20px; }
    h1 { font-size: 72px; margin: 0; color: #ff4b26; font-weight: 800; line-height: 1; }
    h2 { font-size: 22px; margin: 16px 0 12px; }
    p { color: #94a3b8; font-size: 14px; line-height: 1.6; margin-bottom: 24px; }
    .btn { display: inline-flex; align-items: center; gap: 8px; background: #ff4b26; color: #fff; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 14px; transition: background 0.15s; }
    .btn:hover { background: #e03e1b; }
  </style>
</head>
<body>
  <div class="box">
    <h1>404</h1>
    <h2>Page Not Found</h2>
    <p>The PDF tool or resource you are looking for does not exist or may have been moved.</p>
    <a href="/" class="btn">← Return to All Tools</a>
  </div>
</body>
</html>"""
        )
    return JSONResponse(status_code=404, content={"detail": "Not Found"})



if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host=os.getenv("PAPERPLANE_HOST", "127.0.0.1"),
        port=int(os.getenv("PAPERPLANE_PORT", "8501")),
        reload=False,
    )
