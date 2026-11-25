from __future__ import annotations

import io
from html import escape
import json
import math
import os
import re
import time
import datetime as dt
from email.utils import parsedate_to_datetime
import urllib.request
import urllib.error
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import threading
from pathlib import Path
from typing import Any, Iterator
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as reportlab_canvas
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger("paperplane")

_AI_PROVIDER_STATUS_LOCK = threading.Lock()
_AI_PROVIDER_STATUS: dict[str, Any] = {
    "last_request_at": None,
    "last_status": "not_checked",
    "last_provider": None,
    "fallback_active": False,
    "last_failure": None,
}


def _record_ai_provider_status(
    status: str,
    provider: str | None,
    *,
    fallback_active: bool = False,
    failure: str | None = None,
) -> None:
    """Keep a process-local, credential-free snapshot for the admin health panel."""
    safe_statuses = {"available", "rate_limited", "unavailable", "invalid_response"}
    safe_status = status if status in safe_statuses else "unavailable"
    with _AI_PROVIDER_STATUS_LOCK:
        previous = tuple(_AI_PROVIDER_STATUS.get(key) for key in (
            "last_status", "last_provider", "fallback_active", "last_failure",
        ))
        _AI_PROVIDER_STATUS.update({
            "last_request_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "last_status": safe_status,
            "last_provider": (str(provider or "")[:40] or None),
            "fallback_active": bool(fallback_active),
            "last_failure": failure if failure in {"rate_limit", "network", "invalid_response", "provider_error"} else None,
        })
        snapshot = dict(_AI_PROVIDER_STATUS)
        current = tuple(snapshot.get(key) for key in (
            "last_status", "last_provider", "fallback_active", "last_failure",
        ))
    if current == previous:
        return
    try:
        import persistence
        persistence.set_ai_provider_health_status(snapshot)
    except Exception as error:
        logger.debug("Could not persist sanitized AI provider health: %s", type(error).__name__)


def _get_ai_provider_status() -> dict[str, Any]:
    try:
        import persistence
        persisted = persistence.get_ai_provider_health_status()
        if persisted:
            return persisted
    except Exception as error:
        logger.debug("Could not read persisted AI provider health: %s", type(error).__name__)
    with _AI_PROVIDER_STATUS_LOCK:
        return dict(_AI_PROVIDER_STATUS)

import fitz  # PyMuPDF
from config import (
    GEMINI_API_KEY, OPENAI_API_KEY, GEMINI_MODEL, AI_PROVIDER,
    BLUESMINDS_API_KEY, BLUESMINDS_BASE_URL, BLUESMINDS_MODEL,
    BLUESMINDS_TIMEOUT_SECONDS, BLUESMINDS_MAX_OUTPUT_TOKENS, AI_KILL_SWITCH
)

# Keep the imported value for normal startup, but resolve the environment key
# at call time so a rotated/fresh Bluesminds key is honored without requiring
# a process restart. Tests and embedding applications can still override the
# module value explicitly.
_INITIAL_BLUESMINDS_API_KEY = BLUESMINDS_API_KEY
_INITIAL_AGENTROUTER_API_KEY = BLUESMINDS_API_KEY
AGENTROUTER_API_KEY = BLUESMINDS_API_KEY
AGENTROUTER_MODEL = BLUESMINDS_MODEL
AGENTROUTER_BASE_URL = BLUESMINDS_BASE_URL
AGENTROUTER_MAX_RETRIES = 0
AGENTROUTER_TIMEOUT_SECONDS = BLUESMINDS_TIMEOUT_SECONDS
AGENTROUTER_MAX_OUTPUT_TOKENS = BLUESMINDS_MAX_OUTPUT_TOKENS

TOKEN_PATTERN = re.compile(r"\b[a-zA-Z0-9_\-]{2,}\b")
TESSDATA_DIR = Path(__file__).parent / "tessdata"
CHAT_STOPWORDS = {
    "a", "an", "and", "are", "be", "can", "could", "do", "does", "for",
    "had", "has", "have", "how", "in", "is", "it", "me", "my", "of", "on",
    "or", "please", "that", "the", "this", "to", "was", "were", "what",
    "when", "where", "which", "who", "why", "with", "would", "you", "your",
}


def _current_bluesminds_api_key() -> str:
    try:
        import persistence
        creds = persistence.get_runtime_ai_credentials()
        if creds.get("api_key"):
            return creds["api_key"]
    except Exception:
        pass
    module_key = (BLUESMINDS_API_KEY or "").strip()
    if module_key != (_INITIAL_BLUESMINDS_API_KEY or "").strip():
        return module_key
    return os.getenv("BLUESMINDS_API_KEY", "").strip() or module_key


def _current_agentrouter_api_key() -> str:
    return _current_bluesminds_api_key()


def _tokenize(text: str) -> list[str]:
    """Tokenize searchable terms without discarding short identifiers or hyphens."""
    return [word.lower() for word in TOKEN_PATTERN.findall(text)]


def _content_tokens(text: str) -> set[str]:
    """Return query terms that carry meaning for grounded document matching."""
    return {token for token in _tokenize(text) if token not in CHAT_STOPWORDS}



class DocumentChunk:
    def __init__(self, page_number: int, text: str, chunk_id: int):
        self.page_number = page_number
        self.text = text
        self.chunk_id = chunk_id
        self.tokens = self._tokenize(text)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return _tokenize(text)


class LightweightRAG:
    """Fast, dependency-light BM25 probabilistic keyword retrieval engine for PDF documents."""

    def __init__(self, chunks: list[DocumentChunk]):
        self.chunks = chunks
        self.doc_count = len(chunks)
        self.avg_doc_len = sum(len(c.tokens) for c in chunks) / max(1, self.doc_count)
        # Calculate document frequencies
        self.df: Counter[str] = Counter()
        for chunk in chunks:
            unique_tokens = set(chunk.tokens)
            for token in unique_tokens:
                self.df[token] += 1

    def search_scored(
        self,
        query: str,
        top_k: int = 4,
        min_score: float = 0.05,
    ) -> list[tuple[float, DocumentChunk]]:
        query_tokens = [token for token in _tokenize(query) if token not in CHAT_STOPWORDS]
        if not query_tokens:
            return []

        k1 = 1.5
        b = 0.75
        scores: list[tuple[float, DocumentChunk]] = []

        for chunk in self.chunks:
            score = 0.0
            doc_len = len(chunk.tokens)
            token_counts = Counter(chunk.tokens)

            for token in query_tokens:
                if token in self.df:
                    n_qi = self.df[token]
                    idf = math.log((self.doc_count - n_qi + 0.5) / (n_qi + 0.5) + 1.0)
                    f_qi = token_counts[token]
                    numerator = f_qi * (k1 + 1.0)
                    denominator = f_qi + k1 * (1.0 - b + b * (doc_len / max(1.0, self.avg_doc_len)))
                    score += idf * (numerator / max(0.001, denominator))

            if score >= min_score:
                scores.append((score, chunk))

        scores.sort(key=lambda item: item[0], reverse=True)
        return scores[:top_k]

    def search(self, query: str, top_k: int = 4, min_score: float = 0.05) -> list[DocumentChunk]:
        return [chunk for _, chunk in self.search_scored(query, top_k=top_k, min_score=min_score)]


def extract_chunks_from_pdf(pdf_path: Path, max_chars: int = 800) -> list[DocumentChunk]:
    doc = fitz.open(str(pdf_path))
    chunks: list[DocumentChunk] = []
    chunk_id = 0

    try:
        for page_idx, page in enumerate(doc, 1):
            text = page.get_text("text").strip()
            if not text:
                # Certificates and receipts are frequently image-only PDFs.
                # Use MuPDF's OCR text page when the native text layer is empty,
                # but keep the normal extraction path fast for digital PDFs.
                try:
                    if (TESSDATA_DIR / "eng.traineddata").exists():
                        ocr_text_page = page.get_textpage_ocr(
                            language="eng",
                            dpi=150,
                            full=True,
                            tessdata=str(TESSDATA_DIR),
                        )
                    else:
                        ocr_text_page = page.get_textpage_ocr()
                    text = ocr_text_page.extractText().strip()
                except Exception:
                    text = ""
            if not text:
                continue

            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            current_chunk = []
            current_len = 0

            for para in paragraphs:
                if current_len + len(para) > max_chars and current_chunk:
                    chunks.append(DocumentChunk(page_idx, "\n\n".join(current_chunk), chunk_id))
                    chunk_id += 1
                    current_chunk = [para]
                    current_len = len(para)
                else:
                    current_chunk.append(para)
                    current_len += len(para)

            if current_chunk:
                chunks.append(DocumentChunk(page_idx, "\n\n".join(current_chunk), chunk_id))
                chunk_id += 1
    finally:
        doc.close()

    return chunks


def _query_supporting_chunks(chunks: list[DocumentChunk], question: str) -> list[DocumentChunk]:
    """Find sparse lexical support when short-document retrieval falls back to full context."""
    query_tokens = _content_tokens(question)
    if not query_tokens:
        return []

    ranked: list[tuple[int, DocumentChunk]] = []
    for chunk in chunks:
        overlap = query_tokens & {token for token in chunk.tokens if token not in CHAT_STOPWORDS}
        if overlap:
            ranked.append((len(overlap), chunk))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in ranked]


def _select_broad_summary_chunks(chunks: list[DocumentChunk], max_pages: int = 12) -> list[DocumentChunk]:
    """Sample readable pages across the full document to keep broad answers bounded."""
    by_page: dict[int, DocumentChunk] = {}
    for chunk in chunks:
        by_page.setdefault(chunk.page_number, chunk)
    pages = sorted(by_page)
    if len(pages) <= max_pages:
        return [by_page[page] for page in pages]
    positions = {round(index * (len(pages) - 1) / (max_pages - 1)) for index in range(max_pages)}
    return [by_page[pages[index]] for index in sorted(positions)]


_KNOWN_CAPITALS = {
    "france": "paris",
    "germany": "berlin",
    "italy": "rome",
    "spain": "madrid",
    "japan": "tokyo",
    "india": "new delhi",
    "united kingdom": "london",
    "united states": "washington, d.c.",
    "australia": "canberra",
    "canada": "ottawa",
    "china": "beijing",
    "brazil": "brasilia",
    "mexico": "mexico city",
    "russia": "moscow",
    "south korea": "seoul",
    "north korea": "pyongyang",
    "argentina": "buenos aires",
    "egypt": "cairo",
    "turkey": "ankara",
    "türkiye": "ankara",
    "ireland": "dublin",
    "norway": "oslo",
    "sweden": "stockholm",
    "denmark": "copenhagen",
    "netherlands": "amsterdam",
    "belgium": "brussels",
    "switzerland": "bern",
    "poland": "warsaw",
    "portugal": "lisbon",
    "greece": "athens",
    "new zealand": "wellington",
    "nigeria": "abuja",
    "kenya": "nairobi",
    "south africa": "pretoria",
    "saudi arabia": "riyadh",
    "united arab emirates": "abu dhabi",
    "pakistan": "islamabad",
    "bangladesh": "dhaka",
    "nepal": "kathmandu",
    "thailand": "bangkok",
    "vietnam": "hanoi",
    "indonesia": "jakarta",
    "philippines": "manila",
    "malaysia": "kuala lumpur",
    "singapore": "singapore",
    "israel": "jerusalem",
    "iran": "tehran",
    "iraq": "baghdad",
    "afghanistan": "kabul",
    "ukraine": "kyiv",
    "czech republic": "prague",
    "czechia": "prague",
    "romania": "bucharest",
    "hungary": "budapest",
    "finland": "helsinki",
    "iceland": "reykjavik",
    "chile": "santiago",
    "peru": "lima",
    "colombia": "bogota",
    "venezuela": "caracas",
    "morocco": "rabat",
    "ethiopia": "addis ababa",
    "ghana": "accra",
    "cuba": "havana",
    "jamaica": "kingston",
    "luxembourg": "luxembourg",
}


def _pdf_metadata_facts(pdf_path: Path) -> tuple[int, dict[str, str]]:
    """Read only facts directly carried by the PDF container."""
    doc = fitz.open(str(pdf_path))
    try:
        return doc.page_count, {str(k): str(v or "").strip() for k, v in (doc.metadata or {}).items()}
    finally:
        doc.close()


def _pdf_first_page_title(pdf_path: Path) -> str | None:
    """Find a conservative title candidate from a prominent first-page heading."""
    try:
        with fitz.open(str(pdf_path)) as document:
            if not document.page_count:
                return None
            page = document[0]
            page_center = page.rect.width / 2
            boilerplate = re.compile(
                r"(?:provided proper attribution|hereby grants permission|all rights reserved|copyright|terms of use|license)",
                re.IGNORECASE,
            )
            candidates = []
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") != 0:
                    continue
                text = " ".join(
                    span.get("text", "") for line in block.get("lines", [])
                    for span in line.get("spans", [])
                ).strip()
                if not text or len(text) > 180 or boilerplate.search(text):
                    continue
                sizes = [float(span.get("size", 0)) for line in block.get("lines", [])
                         for span in line.get("spans", []) if span.get("text", "").strip()]
                if not sizes:
                    continue
                rect = fitz.Rect(block.get("bbox", (0, 0, 0, 0)))
                prominence = max(sizes) + (2 if abs(rect.x0 + rect.width / 2 - page_center) < page.rect.width * .12 else 0)
                candidates.append((prominence, text))
            if candidates:
                prominence, title = max(candidates, key=lambda item: item[0])
                if prominence >= 14:
                    return title[:100]
            first_line = next((line.strip() for line in page.get_text("text").splitlines() if line.strip()), "")
            if first_line and len(first_line) <= 100 and not boilerplate.search(first_line):
                return first_line
    except Exception:
        return None
    return None


def _metadata_year(value: str) -> str | None:
    match = re.search(r"(?:19|20)\d{2}", value or "")
    return match.group(0) if match else None


def correct_false_premise(pdf_path: Path | None, question: str) -> str | None:
    """Correct a small set of verifiable false premises without inventing PDF content.

    General facts are deliberately limited to an explicit local table. Document
    facts come only from the PDF page count and embedded metadata, and are
    described as metadata rather than independently verified authorship/date.
    """
    if not question.strip():
        return None

    metadata: dict[str, str] = {}
    document_author = ""
    corrections: list[str] = []
    if pdf_path is not None:
        page_count, metadata = _pdf_metadata_facts(pdf_path)
        try:
            document = fitz.open(str(pdf_path))
            try:
                front_matter = "\n".join(page.get_text("text") for page in list(document)[:3])
            finally:
                document.close()
            author_line = re.search(
                r"(?im)^\s*(?:author|written\s+by|by)\s*[:\-]?\s*([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,4})\s*$",
                front_matter,
            )
            if author_line:
                document_author = author_line.group(1).strip()
        except Exception:
            document_author = ""
        page_count_claim = re.search(r"\b(\d{1,5})\s*[- ]?pages?\b", question, re.IGNORECASE)
        if page_count_claim:
            claimed = int(page_count_claim.group(1))
            if claimed != page_count:
                corrections.append(
                    f"Correction: the uploaded PDF contains {page_count} pages, not {claimed}. "
                    f"I can answer questions using those {page_count} pages."
                )

    capital_patterns = (
        re.compile(r"\b(?P<city>[A-Za-z][A-Za-z .'-]{0,35}?)\s+(?:is\s+)?(?:the\s+)?capital\s+of\s+(?P<country>[A-Za-z][A-Za-z .'-]{0,35}?)\b", re.IGNORECASE),
        re.compile(r"\b(?P<city>[A-Za-z][A-Za-z .'-]{0,35}?)\s+(?P<country>[A-Za-z][A-Za-z .'-]{0,35}?)\s+ki\s+capital\b", re.IGNORECASE),
        re.compile(r"\b(?P<city>[A-Za-z][A-Za-z .'-]{0,35}?)\s+(?:is\s+)?(?P<country>[A-Za-z][A-Za-z .'-]{0,35}?)(?:['’]s|s)?\s+capital\b", re.IGNORECASE),
        re.compile(r"\b(?P<country>[A-Za-z][A-Za-z .'-]{0,35}?)(?:['’]s|s)?\s+capital\s+(?:is|hai)\s+(?P<city>[A-Za-z][A-Za-z .'-]{0,35}?)\b", re.IGNORECASE),
    )
    for pattern in capital_patterns:
        match = pattern.search(question)
        if not match:
            continue
        city = re.sub(r"\s+", " ", match.group("city")).strip(" .'-").lower()
        country = re.sub(r"\s+", " ", match.group("country")).strip(" .'-").lower()
        expected_city = _KNOWN_CAPITALS.get(country)
        if expected_city and city != expected_city:
            if country == "germany" and city == "paris":
                correction = "Paris is the capital of France; Berlin is the capital of Germany."
            else:
                correction = f"{expected_city.title()} is the capital of {country.title()}, not {city.title()}."
            corrections.append(
                f"Correction: {correction} This is a general geography correction; "
                "it is not a fact inferred from the uploaded PDF."
            )
            break

    author = metadata.get("author", "").strip() or document_author
    if re.search(r"\b(author|authored|wrote|written by)\b", question, re.IGNORECASE):
        claimed_author = re.search(
            r"\b(?:author(?:ed)?(?:\s+is|\s+was|\s+by)?|written\s+by|wrote)\s+[\"“]?([A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){0,3})",
            question,
        )
        if claimed_author and author and claimed_author.group(1).casefold() != author.casefold():
            corrections.append(
                f"Correction: the PDF identifies {author} as the author, not "
                f"{claimed_author.group(1)}. This is based on the document text or embedded metadata."
            )
        if claimed_author and not author:
            corrections.append("I can't verify that authorship claim: the PDF's metadata and opening text do not identify an author.")

    creation_year = _metadata_year(metadata.get("creationDate", ""))
    if creation_year and re.search(r"\b(date|year|published|publication|created|written)\b", question, re.IGNORECASE):
        claimed_year = re.search(r"\b(?:19|20)\d{2}\b", question)
        if claimed_year and claimed_year.group(0) != creation_year:
            corrections.append(
                f"Correction: the PDF creation metadata records {creation_year}, not {claimed_year.group(0)}. "
                "A file creation date does not establish the document's original publication date."
            )

    return " ".join(corrections) or None


def align_answer_citations(answer: str, eligible_pages: list[int] | set[int]) -> tuple[str, list[int]]:
    """Make citation chips exactly match supported inline page references.

    Accept the common singular, plural, comma-list, and bounded-range forms, then
    normalize every retained citation so the UI and answer have the same pages.
    """
    allowed = {int(page) for page in eligible_pages}

    def expand_pages(raw: str) -> list[int]:
        pages: list[int] = []
        for part in re.split(r"\s*,\s*", raw.strip()):
            range_match = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", part)
            if range_match:
                start, end = map(int, range_match.groups())
                if end >= start and end - start <= 100:
                    pages.extend(range(start, end + 1))
                continue
            if part.isdigit():
                pages.append(int(part))
        return pages

    citation_patterns = (
        re.compile(r"\[(?:pages?|p\.?)\s*([\d,\s\-–]+)\]", re.IGNORECASE),
        re.compile(r"\((?:pages?|p\.?)\s*([\d,\s\-–]+)\)", re.IGNORECASE),
        re.compile(r"(?<![\[(])\bpages?\s+([\d]+(?:\s*[-–,]\s*[\d]+)*)\b(?![\])])", re.IGNORECASE),
    )
    cited_pages: set[int] = set()

    def keep_supported(match: re.Match[str]) -> str:
        kept = sorted({page for page in expand_pages(match.group(1)) if page in allowed})
        if not kept:
            return ""
        cited_pages.update(kept)
        ranges: list[tuple[int, int]] = []
        for page in kept:
            if ranges and page == ranges[-1][1] + 1:
                ranges[-1] = (ranges[-1][0], page)
            else:
                ranges.append((page, page))
        parts = [str(start) if start == end else f"{start}-{end}" for start, end in ranges]
        label = "Page" if len(kept) == 1 else "Pages"
        citation = f"[{label} {', '.join(parts)}]"
        if len(citation) > 120:
            visible = parts[:8]
            omitted = len(kept) - sum(
                (end - start + 1) for start, end in ranges[:len(visible)]
            )
            citation = f"[{label} {', '.join(visible)}, … +{omitted} more pages]"
        # Keep scattered citations readable. Callers that need the complete
        # citation-chip list should request the tuple from summarize_pdf so
        # they do not re-parse this intentionally abbreviated label.
        return citation

    text = answer or ""
    # Remove literal prompt templates before normalizing real page references.
    text = re.sub(r"\[(?:pages?|p\.?)\s*[xX](?:\s*[-–]\s*[xX])?\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[{2,}\s*([^\[\]]+?)\s*\]{2,}", r"[\1]", text)
    for citation_pattern in citation_patterns:
        text = citation_pattern.sub(keep_supported, text)
    text = re.sub(
        r"(?P<citation>\[(?:Page|Pages) \d+(?:, \d+)*\])(?:\s*\1)+",
        r"\g<citation>",
        text,
    )
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip(), sorted(cited_pages)


def call_gemini_flash(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    timeout_seconds: float | None = None,
) -> str:
    """Calls Google's gemini-1.5-flash model for ultra-low cost, high-speed document synthesis."""
    if not GEMINI_API_KEY:
        return ""
    target_model = model or GEMINI_MODEL or "gemini-1.5-flash"
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\nUSER PROMPT / CONTEXT:\n{user_prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
            }
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout_seconds or 35) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                if parts and "text" in parts[0]:
                    return parts[0]["text"].strip()
    except Exception:
        pass
    return ""


def call_bluesminds(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    timeout_seconds: float | None = None,
) -> str:
    """Backward-compatible entry point that honors the selected provider."""
    return _call_selected_provider(system_prompt, user_prompt, model=model, timeout_seconds=timeout_seconds)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Do not forward provider credentials to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_ai_request(request: urllib.request.Request, timeout: float):
    opener = urllib.request.build_opener(_NoRedirectHandler())
    return opener.open(request, timeout=timeout)


def stream_bluesminds(system_prompt: str, user_prompt: str, timeout_seconds: float = 50) -> Iterator[str]:
    """Yield genuine content deltas from the configured OpenAI-compatible stream."""
    if AI_KILL_SWITCH:
        raise RuntimeError("AI request failed, please try again")
    active_credentials = _runtime_ai_config()
    if active_credentials.get("configuration_error"):
        raise RuntimeError(active_credentials["configuration_error"])
    if active_credentials.get("provider") in {"anthropic", "gemini"}:
        yield _provider_request(system_prompt, user_prompt, active_credentials, timeout_seconds=timeout_seconds)
        return
    api_key = active_credentials.get("api_key") or ""
    if not api_key:
        raise ValueError("AI provider is not configured")
    base = (active_credentials.get("base_url") or BLUESMINDS_BASE_URL or "https://api.bluesminds.com/v1").rstrip("/")
    endpoint = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"
    payload = {
        "model": active_credentials.get("model") or BLUESMINDS_MODEL or "openai/gpt-oss-20b",
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": 0.2,
        "max_tokens": BLUESMINDS_MAX_OUTPUT_TOKENS or 4096,
        "stream": True,
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "text/event-stream", "User-Agent": "Paperplane-PDF/1.0"},
    )
    attempts = 2
    for attempt in range(attempts):
        received_content = False
        try:
            with _open_ai_request(req, timeout=max(5, min(60, timeout_seconds))) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        packet = json.loads(data)
                        delta = packet.get("choices", [{}])[0].get("delta", {}).get("content")
                        if isinstance(delta, str) and delta:
                            received_content = True
                            yield delta
                    except (ValueError, IndexError, AttributeError, TypeError):
                        continue
            return
        except urllib.error.HTTPError as exc:
            logger.warning("AI streaming provider returned HTTP %s", exc.code)
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if retryable and not received_content and attempt + 1 < attempts:
                time.sleep(0.4)
                continue
            raise RuntimeError(f"AI service returned HTTP {exc.code}. Please try again.") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            logger.warning("AI streaming provider connection failed: %s", exc)
            if not received_content and attempt + 1 < attempts:
                time.sleep(0.4)
                continue
            raise RuntimeError("AI service could not be reached or timed out. Please try again.") from exc


def call_agentrouter(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    timeout_seconds: float | None = None,
) -> str:
    """Backward-compatible name for the selected provider dispatcher."""
    return _call_selected_provider(system_prompt, user_prompt, model=model, timeout_seconds=timeout_seconds)


def _runtime_ai_config() -> dict[str, str]:
    try:
        import persistence
        config = persistence.get_runtime_ai_credentials()
    except RuntimeError as error:
        logger.error("Dynamic AI credentials are unavailable: %s", str(error))
        return {"provider": "unavailable", "api_key": "", "configuration_error": str(error)}
    except Exception:
        config = {}
    if (
        not config.get("api_key")
        and not config.get("configuration_error")
        and config.get("provider") == "bluesminds"
    ):
        fallback_key = _current_bluesminds_api_key()
        if fallback_key:
            try:
                import persistence
                safe_base_url = persistence._validate_ai_base_url("bluesminds", BLUESMINDS_BASE_URL)
            except Exception:
                return {
                    "provider": "unavailable",
                    "api_key": "",
                    "configuration_error": "The Bluesminds endpoint failed security validation.",
                }
            config = {
                "provider": "bluesminds",
                "model": BLUESMINDS_MODEL,
                "base_url": safe_base_url,
                "api_key": fallback_key,
            }
    return config


def get_ai_configuration_health() -> dict[str, Any]:
    """Return a startup/admin-safe configuration check without making a request."""
    credentials = _runtime_ai_config()
    provider = str(credentials.get("provider") or "unavailable").lower()
    if credentials.get("configuration_error"):
        health = {
            "status": "configuration_error",
            "provider": provider,
            "configured": False,
            "message": "The saved AI configuration could not be loaded. Check the server encryption configuration.",
        }
    elif not (credentials.get("api_key") and credentials.get("model")):
        health = {
            "status": "configuration_missing",
            "provider": provider,
            "configured": False,
            "message": "AI provider credentials or model are not configured; AI document tools are unavailable.",
        }
    else:
        health = {
            "status": "configured",
            "provider": provider,
            "configured": True,
            "message": "AI provider configuration is present. Run Test Connection to check upstream reachability.",
        }
    runtime_status = _get_ai_provider_status()
    runtime_status["applies_to_current_provider"] = runtime_status["last_provider"] == provider
    health["runtime_status"] = runtime_status
    if runtime_status["applies_to_current_provider"] and runtime_status["last_status"] == "rate_limited" and runtime_status["fallback_active"]:
        health["message"] = "The primary AI provider was rate limited; the configured fallback handled the last request. Check primary provider quota."
    elif runtime_status["applies_to_current_provider"] and runtime_status["last_status"] == "rate_limited":
        health["message"] = "The last AI request was rate limited. Check provider quota or use the configured fallback provider."
    elif runtime_status["applies_to_current_provider"] and runtime_status["last_status"] == "unavailable":
        health["message"] = "The last AI request could not reach a provider. Check provider availability and the configured fallback."
    elif runtime_status["applies_to_current_provider"] and runtime_status["last_status"] == "available" and runtime_status["fallback_active"]:
        health["message"] = "The primary provider failed; the configured fallback handled the last AI request."
    return health


def _provider_request(
    system_prompt: str,
    user_prompt: str,
    credentials: dict[str, str],
    timeout_seconds: float | None = None,
    max_attempts: int = 2,
    temperature: float = 0.2,
) -> str:
    """Make one non-streaming request using the selected provider's native wire format."""
    provider = str(credentials.get("provider") or "bluesminds").lower()
    model = str(credentials.get("model") or BLUESMINDS_MODEL or "").strip()
    api_key = str(credentials.get("api_key") or "").strip()
    base_url = str(credentials.get("base_url") or "").rstrip("/")
    if not api_key:
        raise ValueError("AI provider is not configured")
    if not model:
        raise ValueError("AI model is not configured")
    if not base_url.startswith("https://"):
        raise ValueError("AI provider requires a validated HTTPS endpoint.")

    total_timeout = max(5, min(120, float(timeout_seconds or BLUESMINDS_TIMEOUT_SECONDS)))
    try:
        response_temperature = min(2.0, max(0.0, float(temperature)))
    except (TypeError, ValueError):
        response_temperature = 0.2
    attempts = max(1, min(4, int(max_attempts)))
    retry_delays = (0.4, 2.0, 5.0)
    total_backoff = sum(retry_delays[:max(0, attempts - 1)])
    per_attempt_timeout = max(0.1, (total_timeout - total_backoff) / attempts)
    request_deadline = time.monotonic() + total_timeout
    headers = {"Content-Type": "application/json", "User-Agent": "Paperplane-PDF/1.0"}
    if provider in {"bluesminds", "openrouter", "deepseek", "openai_compatible"}:
        endpoint = f"{base_url}/chat/completions" if base_url.endswith("/v1") else f"{base_url}/v1/chat/completions"
        headers["Authorization"] = f"Bearer {api_key}"
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://paperplane.qd.je"
            headers["X-Title"] = "Paperplane PDF"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": response_temperature,
            "max_tokens": BLUESMINDS_MAX_OUTPUT_TOKENS or 4096,
        }
    elif provider == "anthropic":
        endpoint = f"{base_url}/messages" if base_url.endswith("/v1") else f"{base_url}/v1/messages"
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        payload = {
            "model": model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": BLUESMINDS_MAX_OUTPUT_TOKENS or 4096,
            "temperature": response_temperature,
        }
    elif provider == "gemini":
        endpoint = f"{base_url}/models/{urllib.parse.quote(model, safe='')}:generateContent" if base_url.endswith("/v1beta") else f"{base_url}/v1beta/models/{urllib.parse.quote(model, safe='')}:generateContent"
        headers["x-goog-api-key"] = api_key
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": response_temperature, "maxOutputTokens": BLUESMINDS_MAX_OUTPUT_TOKENS or 4096},
        }
    else:
        raise ValueError("Unsupported AI provider.")

    body = json.dumps(payload).encode("utf-8")
    answer = ""
    provider_host = urllib.parse.urlsplit(endpoint).hostname
    def retry_delay(attempt: int, retry_after: str | None = None) -> float:
        if retry_after:
            try:
                return min(30.0, max(0.0, float(retry_after)))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=dt.timezone.utc)
                    return min(30.0, max(0.0, (retry_at - dt.datetime.now(dt.timezone.utc)).total_seconds()))
                except (TypeError, ValueError, OverflowError):
                    pass
        return retry_delays[min(attempt, len(retry_delays) - 1)]

    for attempt in range(attempts):
        attempts_left = attempts - attempt
        remaining_budget = request_deadline - time.monotonic()
        if remaining_budget <= 0.1:
            raise TimeoutError("AI provider retry budget exhausted")
        future_backoff_reserve = sum(retry_delays[attempt:attempt + attempts_left - 1])
        available_for_requests = max(0.1, remaining_budget - future_backoff_reserve)
        request_timeout = min(per_attempt_timeout, available_for_requests / attempts_left)
        request = urllib.request.Request(endpoint, data=body, headers=headers)
        try:
            started = time.monotonic()
            with _open_ai_request(request, timeout=request_timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                logger.debug("AI provider host=%s attempt=%d timeout=%.1fs HTTP=%s elapsed=%.1fs",
                             provider_host, attempt + 1, request_timeout, getattr(response, "status", None),
                             time.monotonic() - started)
            if not isinstance(data, dict):
                raise ValueError("Invalid provider response")
            if provider == "anthropic":
                content = data.get("content", [])
                answer = "".join(item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text")
            elif provider == "gemini":
                candidates = data.get("candidates", [])
                parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
                answer = "".join(item.get("text", "") for item in parts if isinstance(item, dict))
            else:
                choices = data.get("choices", [])
                answer = choices[0].get("message", {}).get("content", "") if choices else ""
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Empty provider response")
            break
        except urllib.error.HTTPError as error:
            logger.warning("AI provider host=%s attempt=%d timeout=%.1fs HTTP=%s",
                           provider_host, attempt + 1, request_timeout, error.code)
            if attempt + 1 < attempts and error.code in (408, 429, 500, 502, 503, 504):
                retry_after = error.headers.get("Retry-After") if error.headers else None
                future_attempts = attempts - attempt - 1
                reserve_per_attempt = min(5.0, per_attempt_timeout)
                sleep_budget = max(
                    0.0,
                    request_deadline - time.monotonic() - reserve_per_attempt * future_attempts,
                )
                delay = min(retry_delay(attempt, retry_after), sleep_budget)
                if delay <= 0:
                    raise RuntimeError(f"AI service returned HTTP {error.code}. Please try again.") from error
                time.sleep(delay)
                continue
            raise RuntimeError(f"AI service returned HTTP {error.code}. Please try again.") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            logger.warning("AI provider host=%s attempt=%d timeout=%.1fs failure=%s",
                           provider_host, attempt + 1, request_timeout, type(error).__name__)
            if attempt + 1 < attempts:
                future_attempts = attempts - attempt - 1
                reserve_per_attempt = min(5.0, per_attempt_timeout)
                sleep_budget = max(
                    0.0,
                    request_deadline - time.monotonic() - reserve_per_attempt * future_attempts,
                )
                time.sleep(min(retry_delay(attempt), sleep_budget))
                continue
            raise RuntimeError("AI service could not be reached or timed out. Please try again.") from error
        except (ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
            logger.warning("AI provider host=%s attempt=%d returned an empty or invalid response", provider_host, attempt + 1)
            if attempt + 1 < attempts:
                time.sleep(retry_delay(attempt))
                continue
            raise RuntimeError("AI service returned an empty or invalid response. Please try again.") from error
    return answer.strip()


def test_bluesminds_connectivity() -> dict:
    """Test the selected AI provider without exposing its key, model, or upstream body."""
    if AI_KILL_SWITCH:
        return {
            "status": "disabled",
            "message": "AI is disabled by configuration.",
            "fallback_active": False
        }
    credentials = _runtime_ai_config()
    if credentials.get("configuration_error"):
        return {
            "status": "configuration_error",
            "message": credentials["configuration_error"],
            "fallback_active": False,
        }
    if not credentials.get("api_key") or not credentials.get("model"):
        return {
            "status": "configuration_missing",
            "message": "AI provider key or model is not configured",
            "advice": "Ask the site administrator to configure the AI provider, model, and API key.",
            "fallback_active": False
        }

    try:
        answer, fallback_active = _call_selected_provider_with_status(
            "Reply with the word connected.", "ping", timeout_seconds=12, max_attempts=2
        )
        return {
            "status": "inference_succeeded",
            "http_status": 200,
            "message": "AI connected successfully.",
            "fallback_active": fallback_active,
        }
    except Exception as error:
        match = re.search(r"HTTP (\d{3})", str(error))
        status_code = int(match.group(1)) if match else 502
        safe_message = f"AI provider request failed ({_safe_provider_failure_label(error)})."
        return {
            "status": "connection_error",
            "http_status": status_code,
            "message": safe_message,
            "advice": safe_message,
            "fallback_active": False,
        }


def test_agentrouter_connectivity() -> dict:
    """Backward compatibility wrapper delegating to Bluesminds connectivity test."""
    return test_bluesminds_connectivity()


def call_llm(
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: float | None = None,
    model: str | None = None,
    max_attempts: int = 2,
    temperature: float = 0.2,
) -> str:
    """Dispatch inference using the selected provider's native API contract."""
    return _call_selected_provider(
        system_prompt, user_prompt, model=model, timeout_seconds=timeout_seconds, max_attempts=max_attempts,
        temperature=temperature,
    )


def _call_selected_provider(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    timeout_seconds: float | None = None,
    max_attempts: int = 2,
    temperature: float = 0.2,
) -> str:
    answer, _ = _call_selected_provider_with_status(
        system_prompt,
        user_prompt,
        model=model,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        temperature=temperature,
    )
    return answer


def _safe_provider_failure_label(error: BaseException) -> str:
    """Return useful upstream failure metadata without exposing response bodies or credentials."""
    statuses = re.findall(r"\bHTTP\s+(\d{3})\b", str(error), re.IGNORECASE)
    if statuses:
        unique = list(dict.fromkeys(statuses))
        return "; ".join(f"upstream HTTP {status}" for status in unique)
    if re.search(r"timeout|timed out|could not be reached|connection error", str(error), re.IGNORECASE):
        return "network timeout or connection error"
    if re.search(r"empty|invalid|structured response", str(error), re.IGNORECASE):
        return "empty or invalid provider response"
    return type(error).__name__


def complete_with_configured_fallback(
    system_prompt: str,
    user_prompt: str,
    primary_error: BaseException,
    timeout_seconds: float | None = None,
) -> str | None:
    """Complete a failed chat stream through the configured fallback, if present.

    This is used only after streaming fails. It calls the fallback directly so
    the failed primary stream is not restarted and charged a second time.
    """
    credentials = _runtime_ai_config()
    fallback = credentials.get("fallback")
    if not isinstance(fallback, dict) or not fallback.get("api_key") or not fallback.get("model"):
        return None
    primary_provider = str(credentials.get("provider") or "unavailable")
    primary_label = _safe_provider_failure_label(primary_error)
    primary_failure = "rate_limit" if "429" in str(primary_error) else (
        "network" if "network" in primary_label or "timeout" in primary_label else "provider_error"
    )
    try:
        answer = _provider_request(
            system_prompt,
            user_prompt,
            fallback,
            timeout_seconds=timeout_seconds,
            max_attempts=2,
        )
    except Exception as fallback_error:
        fallback_label = _safe_provider_failure_label(fallback_error)
        fallback_failure = "rate_limit" if "429" in str(fallback_error) else (
            "network" if "network" in fallback_label or "timeout" in fallback_label else "provider_error"
        )
        _record_ai_provider_status(
            "rate_limited" if fallback_failure == "rate_limit" else "unavailable",
            str(fallback.get("provider") or primary_provider),
            failure=fallback_failure,
        )
        raise RuntimeError(
            f"AI service failed ({primary_label}); configured fallback failed ({fallback_label}). Please retry later."
        ) from fallback_error
    _record_ai_provider_status(
        "rate_limited" if primary_failure == "rate_limit" else "unavailable",
        primary_provider,
        fallback_active=True,
        failure=primary_failure,
    )
    return answer


def _call_selected_provider_with_status(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    timeout_seconds: float | None = None,
    max_attempts: int = 2,
    temperature: float = 0.2,
) -> tuple[str, bool]:
    """Run the selected provider and report whether the configured fallback succeeded."""
    if AI_KILL_SWITCH:
        return _offline_rag_fallback(system_prompt, user_prompt), False
    credentials = _runtime_ai_config()
    if credentials.get("configuration_error"):
        raise RuntimeError(credentials["configuration_error"])
    if not credentials.get("api_key"):
        raise ValueError("AI provider is not configured")
    if model:
        credentials = dict(credentials)
        credentials["model"] = model
    primary_provider = str(credentials.get("provider") or "unavailable")
    try:
        answer = _provider_request(
            system_prompt, user_prompt, credentials, timeout_seconds=timeout_seconds, max_attempts=max_attempts,
            temperature=temperature,
        )
        _record_ai_provider_status("available", primary_provider)
        return answer, False
    except Exception as primary_error:
        primary_failure_label = _safe_provider_failure_label(primary_error)
        primary_failure = "rate_limit" if "429" in str(primary_error) else (
            "network" if "network" in primary_failure_label or "timeout" in primary_failure_label else "provider_error"
        )
        fallback = credentials.get("fallback")
        if not isinstance(fallback, dict) or not fallback.get("api_key") or not fallback.get("model"):
            status = "rate_limited" if primary_failure == "rate_limit" else "unavailable"
            _record_ai_provider_status(status, primary_provider, failure=primary_failure)
            raise
        logger.warning(
            "Primary AI provider failed; trying configured fallback provider host=%s",
            urllib.parse.urlsplit(str(fallback.get("base_url", ""))).hostname or "unknown",
        )
        try:
            answer = _provider_request(
                system_prompt, user_prompt, fallback, timeout_seconds=timeout_seconds, max_attempts=max_attempts,
                temperature=temperature,
            )
            status = "rate_limited" if primary_failure == "rate_limit" else "unavailable"
            _record_ai_provider_status(status, primary_provider, fallback_active=True, failure=primary_failure)
            return answer, True
        except Exception as fallback_error:
            fallback_label = _safe_provider_failure_label(fallback_error)
            fallback_failure = "rate_limit" if "429" in str(fallback_error) else (
                "network" if "network" in fallback_label or "timeout" in fallback_label else "provider_error"
            )
            _record_ai_provider_status(
                "rate_limited" if fallback_failure == "rate_limit" else "unavailable",
                str(fallback.get("provider") or primary_provider), failure=fallback_failure,
            )
            primary_label = _safe_provider_failure_label(primary_error)
            raise RuntimeError(
                f"Primary AI provider failed ({primary_label}); configured fallback provider failed ({fallback_label})."
            ) from fallback_error


def _offline_rag_fallback(system_prompt: str, user_prompt: str) -> str:
    """Intelligent local deterministic answer builder (Offline RAG mode)."""
    if "Executive Summary" in system_prompt or "summariz" in system_prompt.lower():
        doc_text = user_prompt.replace("DOCUMENT CONTENT:\n\n", "")
        pages = re.split(r"--- Page (\d+) ---", doc_text)
        parsed_pages: list[tuple[str, list[str]]] = []
        line_frequency: dict[str, int] = {}
        for index in range(1, len(pages) - 1, 2):
            number, page_text = pages[index], pages[index + 1]
            lines = [
                line.strip() for line in page_text.splitlines()
                if len(line.strip()) >= 10
                and not re.search(
                    r"\b(?:attribution|copyright|all rights reserved|generated automatically|"
                    r"local extractive notes|confidentiality notice)\b",
                    line,
                    re.IGNORECASE,
                )
            ]
            parsed_pages.append((number, lines))
            for line in lines:
                normalized = re.sub(r"\s+", " ", line.lower()).strip()
                line_frequency[normalized] = line_frequency.get(normalized, 0) + 1

        summary_points = []
        priority_terms = re.compile(
            r"\b(?:decision|deadline|due|total|amount|finding|fact|completion|risk|action|"
            r"approved|approval|recommend(?:ation)?|required|result|milestone|final|conclusion)\b",
            re.IGNORECASE,
        )
        for number, lines in parsed_pages:
            ranked: list[tuple[float, int, str]] = []
            for line_index, line in enumerate(lines):
                normalized = re.sub(r"\s+", " ", line.lower()).strip()
                score = 4.0 * len(priority_terms.findall(line))
                # Values, percentages, and dates often carry the key fact even
                # when the source line has no explicit heading word.
                if re.search(r"(?:[$€£₹]|\b\d{1,4}(?:[.,]\d+)?\s*(?:%|percent|days?|weeks?|months?|years?))", line, re.I):
                    score += 4.0
                if len(line.strip()) >= 18:
                    score += 1.0
                if line_frequency.get(normalized, 0) > 1:
                    score -= 3.0
                if score > 0:
                    ranked.append((score, line_index, line))
            # Pick high-value lines across a page before filling slots by score.
            # Score-only selection favored early lines and could omit a unique
            # decision near the bottom of a long page.
            selected_by_region: dict[int, tuple[float, int, str]] = {}
            for entry in ranked:
                region = min(2, (entry[1] * 3) // max(1, len(lines)))
                current = selected_by_region.get(region)
                if current is None or (entry[0], -entry[1]) > (current[0], -current[1]):
                    selected_by_region[region] = entry
            selected = sorted(selected_by_region.values(), key=lambda entry: entry[1])
            selected_indices = {entry[1] for entry in selected}
            for entry in sorted(ranked, key=lambda value: (-value[0], value[1])):
                if len(selected) >= 4:
                    break
                if entry[1] not in selected_indices:
                    selected.append(entry)
                    selected_indices.add(entry[1])
            selected.sort(key=lambda entry: entry[1])
            if not selected and lines:
                selected = [(0.0, idx, line) for idx, line in enumerate(lines[:2])]
            for _score, _line_index, line in selected:
                summary_points.append(f"{line[:240]} [Page {number}]")

        pts = "\n".join(f"- {pt}" for pt in summary_points) if summary_points else "- General document overview available."
        return (
            "### Executive Summary (Offline Analysis)\n\n"
            "This document was reviewed with deterministic local extraction, showing up to four page-grounded highlights per text page. "
            "This concise extractive fallback is not a complete synthesis; review the source pages.\n\n"
            "#### Key Findings & Extracted Topics\n"
            f"{pts}\n\n"
            "*(Generated from local document text analysis.)*"
        )

    # For chat Q&A fallback
    excerpts_match = re.search(r'DOCUMENT EXCERPTS:\n(.*?)\n\nUSER QUESTION:\s*(.*)', user_prompt, re.DOTALL)
    if excerpts_match:
        excerpts = excerpts_match.group(1).strip()
        question = excerpts_match.group(2).strip()

        requested_page = re.search(r"\bpage\s+(\d+)\b", question, re.IGNORECASE)
        if requested_page:
            requested_number = int(requested_page.group(1))
            for block in re.split(r"\n\s*---\s*\n", excerpts):
                page_match = re.match(r"\[Page\s*(\d+)\]\s*:\s*", block)
                if page_match and int(page_match.group(1)) == requested_number:
                    page_text = re.sub(r"\s+", " ", block[page_match.end():]).strip()
                    if page_text:
                        return f"{page_text} [Page {requested_number}]"

        if re.search(r"\b(summar(?:y|ize|ise)|overview|key points|important information|about (?:this|the) document|describe (?:this|the) document)\b|\bwhat is (?:this|the) (?:pdf|document) about\b|\btell me about (?:this|the) (?:pdf|document)\b", question, re.IGNORECASE):
            # A broad-summary retrieval deliberately samples pages across the
            # document, so a lexical overlap query may have no topical terms.
            # Return short extractive page notes instead of falsely claiming
            # that the document has no relevant content. Each note keeps its
            # source text and citation together for deterministic chip parity.
            page_notes = []
            for block in re.split(r"\n\s*---\s*\n", excerpts):
                page_match = re.search(r"\[Page\s*(\d+)\]\s*:\s*", block)
                if not page_match:
                    continue
                page_number = int(page_match.group(1))
                page_text = re.sub(r"\s+", " ", block[page_match.end():]).strip()
                if not page_text:
                    continue
                if len(page_text) > 240:
                    page_text = page_text[:237].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
                # The visible `Page N:` prefix is citation-aligned downstream;
                # appending a second `[Page N]` generated duplicate chat chips.
                page_notes.append(f"Page {page_number}: {page_text}")
            if page_notes:
                return "Document overview from sampled pages:\n\n" + "\n\n".join(page_notes)

        current_page = None
        best_lines = []
        question_tokens = _content_tokens(question)
        for raw_line in excerpts.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("---"):
                continue
            page_match = re.match(r"\[Page\s*(\d+)\]", line)
            if page_match:
                current_page = page_match.group(1)
                continue

            overlap = len(question_tokens & _content_tokens(line))
            if overlap > 0:
                best_lines.append((overlap, line, current_page))
        best_lines.sort(key=lambda x: x[0], reverse=True)

        if best_lines:
            ans_text = " ".join(line for _, line, _ in best_lines[:4])
            pages = sorted({page for _, _, page in best_lines[:4] if page}, key=int)
            page_ref = f" [Page {', '.join(pages)}]" if pages else ""
            return f"{ans_text}{page_ref}\n\n*(Extracted via deterministic local BM25 keyword matching)*"
        else:
            return "No relevant information found in the document for your question. The active document does not contain matching keywords or passages."

    return f"Based on the retrieved document contents:\n\n{user_prompt[:500]}..."



_SUMMARY_CURRENCY_AMOUNT = re.compile(
    r"(?:(?P<prefix>[$€£₹¥]\s*|\b(?:USD|EUR|GBP|INR|JPY|CAD|AUD|RMB|CNY|Rs\.?|rupees?|dollars?|euros?|pounds?)\s+)"
    r"(?P<prefix_amount>\d(?:[\d,]*\d)?(?:\.\d+)?)|"
    r"(?P<suffix_amount>\d(?:[\d,]*\d)?(?:\.\d+)?)\s*(?P<suffix>[$€£₹¥]|\b(?:USD|EUR|GBP|INR|JPY|CAD|AUD|RMB|CNY|Rs\.?|rupees?|dollars?|euros?|pounds?)\b))",
    re.IGNORECASE,
)
_SUMMARY_SOURCE_NUMBER = re.compile(r"(?<![\w.])(?:\d[\d,]*\d|\d)(?:\.\d+)?(?!\w|,\d|\.\d)")
_SUMMARY_CURRENCY_PREFIX = re.compile(
    r"(?:[$€£₹¥]|\b(?:USD|EUR|GBP|INR|JPY|CAD|AUD|RMB|CNY|Rs\.?|rupees?|dollars?|euros?|pounds?)\b)\s*$",
    re.IGNORECASE,
)
_SUMMARY_CURRENCY_SUFFIX = re.compile(
    r"^\s*[\(\[]?\s*(?:[$€£₹¥]|\b(?:USD|EUR|GBP|INR|JPY|CAD|AUD|RMB|CNY|Rs\.?|rupees?|dollars?|euros?|pounds?)\b)\s*[\)\]]?(?!\s*\d)",
    re.IGNORECASE,
)
_SUMMARY_UNSPECIFIED_CURRENCY = re.compile(
    r"(?P<amount>\d(?:[\d,]*\d)?(?:\.\d+)?)\s*"
    r"(?:\(\s*currency\s+(?:unspecified|not\s+specified|unidentified)\s*\)|"
    r"\[\s*currency\s+(?:unspecified|not\s+specified|unidentified)\s*\])",
    re.IGNORECASE,
)


def _numeric_amount_key(amount: str) -> str:
    """Normalize grouping separators without changing the represented amount."""
    return amount.replace(",", "").lstrip("0") or "0"


def _source_amount_currency(source_text: str, amount: str) -> str | None:
    amount_key = _numeric_amount_key(amount)
    for source_match in _SUMMARY_SOURCE_NUMBER.finditer(source_text):
        if _numeric_amount_key(source_match.group()) != amount_key:
            continue
        prefix = source_text[max(0, source_match.start() - 24):source_match.start()]
        suffix = source_text[source_match.end():source_match.end() + 24]
        currency_match = _SUMMARY_CURRENCY_PREFIX.search(prefix) or _SUMMARY_CURRENCY_SUFFIX.search(suffix)
        if not currency_match:
            continue
        token = currency_match.group().strip().strip("()[] ")
        folded = token.casefold().rstrip(".")
        if token == "₹" or folded in {"inr", "rs", "rupee", "rupees"}:
            return "INR"
        if folded in {"usd", "dollar", "dollars"}:
            return "USD"
        if folded in {"eur", "euro", "euros"}:
            return "EUR"
        if folded in {"gbp", "pound", "pounds"}:
            return "GBP"
        if folded in {"jpy"}:
            return "JPY"
        if folded in {"cad"}:
            return "CAD"
        if folded in {"aud"}:
            return "AUD"
        if folded in {"rmb", "cny"}:
            return "CNY"
        return token
    return None


def _source_amount_has_currency(source_text: str, amount: str) -> bool:
    return _source_amount_currency(source_text, amount) is not None


def _restore_explicit_summary_currency(summary: str, source_text: str) -> str:
    """Restore a source currency the model marked unspecified for a matching amount."""
    def restore(match: re.Match[str]) -> str:
        amount = match.group("amount")
        currency = _source_amount_currency(source_text, amount)
        return f"{currency} {amount}" if currency else match.group()

    return _SUMMARY_UNSPECIFIED_CURRENCY.sub(restore, summary)


def _remove_unsupported_summary_currency(summary: str, source_text: str) -> str:
    """Require nearby source evidence for each currency assigned to a number."""
    def replace_if_unsupported(match: re.Match[str]) -> str:
        amount = match.group("prefix_amount") or match.group("suffix_amount")
        if _source_amount_has_currency(source_text, amount):
            return match.group()
        return f"{amount} (currency unspecified)"

    return _SUMMARY_CURRENCY_AMOUNT.sub(replace_if_unsupported, summary)


def _remove_unsupported_summary_absence_claims(summary: str, source_text: str) -> str:
    """Drop document-wide absence claims unless the source states that claim."""
    claim = re.compile(
        r"(?i)\b(?:the\s+document\s+)?(?:contains?\s+|shows?\s+|identifies?\s+)?"
        r"(?:no|none\s+of\s+the|not\s+any)\s+(?:additional\s+|further\s+|other\s+)?"
        r"(?:dates?|deadlines?|risks?|decisions?|requirements?|obligations?|milestones?)\b[^.!?\n]*[.!?]?"
    )
    normalized_source = re.sub(r"\s+", " ", source_text).casefold()

    def keep_if_supported(match: re.Match[str]) -> str:
        sentence = re.sub(r"\s+", " ", match.group()).strip().casefold()
        return match.group() if sentence and sentence in normalized_source else ""

    return claim.sub(keep_if_supported, summary)


# ----------------------------------------------------------------------
# PUBLIC AI CAPABILITIES
# ----------------------------------------------------------------------

def sparse_document_text_response(chunks: list[DocumentChunk], page_count: int, question: str) -> dict | None:
    """Return explicit OCR guidance for broad questions on image-heavy PDFs."""
    broad_document_question = bool(re.search(
        r"\b(?:what is|tell me about|describe) (?:this|the) (?:pdf|document)|\b(?:overview|summar(?:y|ize|ise))\b",
        question,
        re.IGNORECASE,
    ))
    if not broad_document_question:
        return None
    extracted_chars = sum(len(re.sub(r"\s+", "", chunk.text)) for chunk in chunks)
    sparse_text_limit = max(240, page_count * 50)
    if extracted_chars >= sparse_text_limit:
        return None
    return {
        "answer": (
            f"This PDF has very little searchable text ({extracted_chars} characters across "
            f"{page_count} pages), so I cannot reliably identify its subject. It may "
            "contain scanned pages or a photo gallery. Run OCR to make its text searchable, "
            "then ask again."
        ),
        "citations": [],
        "retrieval_method": "Sparse PDF Text Check",
        "fallback_used": True,
        "relevant_passages": [],
    }


def chat_with_pdf(pdf_path: Path, question: str, filename: str | None = None) -> dict:
    """Queries the PDF via RAG with BM25 probabilistic keyword retrieval and verified page citations."""
    greeting = _simple_greeting_reply(question)
    if greeting:
        return {"answer": greeting, "citations": [], "retrieval_method": None, "fallback_used": False}
    private_reply = _private_information_request_reply(question)
    if private_reply:
        return {"answer": private_reply, "citations": [], "retrieval_method": None, "fallback_used": False}
    if _is_code_request(question):
        return {"answer": _CODE_SCOPE_REPLY, "citations": [], "retrieval_method": None, "fallback_used": False}
    if _is_identity_question(question):
        return {"answer": _PAPERPLANE_IDENTITY, "citations": [], "retrieval_method": None, "fallback_used": False}
    chunks = extract_chunks_from_pdf(pdf_path)
    document_page_count, document_metadata = _pdf_metadata_facts(pdf_path)
    display_filename = Path(str(filename or pdf_path.name).replace("\\", "/")).name or pdf_path.name
    document_title = document_metadata.get("title") or _pdf_first_page_title(pdf_path) or Path(display_filename).stem
    metadata_header = (
        "DOCUMENT METADATA\n"
        f"Filename: {display_filename}\n"
        f"Page count: {document_page_count}\n"
        f"Title: {document_title}\n"
    )


    metadata_question = bool(re.search(
        r"\b(how many pages?|page count|number of pages|document title|pdf title|file name|filename|title of (?:this|the) (?:document|pdf)|what(?:'s| is) (?:the )?(?:document )?title)\b",
        question,
        re.IGNORECASE,
    ))
    if metadata_question:
        normalized_question = question.lower()
        if re.search(r"\b(how many pages?|page count|number of pages)\b", normalized_question):
            answer = f"This document has {document_page_count} pages."
        elif re.search(r"\b(title|name|filename)\b", normalized_question):
            answer = f"The document title is \"{document_title}\". The file name is \"{display_filename}\"."
        else:
            answer = metadata_header.strip()
        return {
            "answer": answer,
            "citations": [],
            "retrieval_method": "Verified PDF Metadata",
            "fallback_used": False,
            "relevant_passages": [],
        }
    correction = correct_false_premise(pdf_path, question)
    if correction:
        return {
            "answer": correction,
            "citations": [],
            "retrieval_method": "Verified PDF Metadata and Local Fact Check",
            "fallback_used": False,
            "relevant_passages": [],
        }
    if not chunks:
        return {
            "answer": "No readable text was found in this document to answer your question.",
            "citations": [],
            "retrieval_method": "BM25 Keyword Retrieval",
            "fallback_used": True
        }

    rag = LightweightRAG(chunks)
    page_match = re.search(
        r"\bpage\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b",
        question,
        re.IGNORECASE,
    )
    broad_summary = bool(re.search(r"\b(summar(?:y|ize|ise)|overview|key points|important information)\b|\bwhat is (?:this|the) (?:pdf|document) about\b|\btell me about (?:this|the) (?:pdf|document)\b", question, re.IGNORECASE))
    if page_match:
        page_value = page_match.group(1).lower()
        page_words = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        }
        requested_page = int(page_value) if page_value.isdigit() else page_words[page_value]
        retrieved_chunks = [chunk for chunk in chunks if chunk.page_number == requested_page]
        scored_chunks = [(1.0, chunk) for chunk in retrieved_chunks]
    elif broad_summary:
        retrieved_chunks = _select_broad_summary_chunks(chunks)
        scored_chunks = [(1.0, chunk) for chunk in retrieved_chunks]
    else:
        scored_chunks = rag.search_scored(question, top_k=8)
        retrieved_chunks = [chunk for _, chunk in scored_chunks]
    doc = fitz.open(str(pdf_path))
    try:
        document_page_count = doc.page_count
    finally:
        doc.close()

    is_short_document = document_page_count <= 5 or len(chunks) <= 6
    context_chunks = retrieved_chunks
    citation_chunks = retrieved_chunks
    sparse_response = sparse_document_text_response(chunks, document_page_count, question)
    if sparse_response:
        return sparse_response
    broad_document_question = bool(re.search(
        r"\b(?:what is|tell me about|describe) (?:this|the) (?:pdf|document)|\b(?:overview|summar(?:y|ize|ise))\b",
        question,
        re.IGNORECASE,
    ))
    if broad_document_question and chunks:
        context_chunks = chunks[:24]
        citation_chunks = context_chunks
    low_score_threshold = 0.15
    if is_short_document and (
        not scored_chunks or scored_chunks[0][0] < low_score_threshold
    ):
        # Small certificates and receipts are cheap enough to pass in full. BM25
        # can suppress a one-off field label or identifier, so retain complete
        # document context while keeping citations limited to lexical support.
        context_chunks = chunks
        citation_chunks = _query_supporting_chunks(chunks, question)

    if not context_chunks:
        extracted_chars = sum(len(re.sub(r"\s+", "", chunk.text)) for chunk in chunks)
        no_context_answer = (
            "This PDF has very little extractable text, so I could not reliably identify its subject. It may contain scanned or image based pages. Try OCR or provide a clearer text copy."
            if extracted_chars < 240 else
            "No relevant information found in the document for this question. The active document does not contain matching keywords or passages."
        )
        return {
            "answer": no_context_answer,
            "citations": [],
            "retrieval_method": "BM25 Keyword Retrieval",
            "fallback_used": False,
            "relevant_passages": []
        }

    context_parts = []
    citations = []
    for chunk in context_chunks:
        context_parts.append(f"[Page {chunk.page_number}]:\n{chunk.text}")
    for chunk in citation_chunks:
        if chunk.page_number not in citations:
            citations.append(chunk.page_number)

    context_str = "\n\n---\n\n".join(context_parts)
    system_prompt = (
        "You are an expert AI document assistant. Answer the user's question accurately using ONLY "
        "the provided document excerpts. Always cite specific page numbers like [Page X] when referencing facts.\n\n"
        + metadata_header
    )
    user_prompt = f"DOCUMENT EXCERPTS:\n{context_str}\n\nUSER QUESTION: {question}"

    provider_unavailable = AI_KILL_SWITCH or not _current_bluesminds_api_key()
    if provider_unavailable:
        answer = _offline_rag_fallback(system_prompt, user_prompt)
    else:
        answer = _guard_ai_output(call_llm(_PAPERPLANE_SYSTEM_PROMPT + " " + system_prompt, user_prompt, timeout_seconds=50))
    if not citation_chunks:
        # The full short document was still supplied to the answering engine,
        # but unsupported questions must not receive fabricated answers or broad
        # citations merely because fallback context was used.
        answer = "No relevant information found in the document for your question. The active document does not contain matching keywords or passages."
    is_fallback = bool(provider_unavailable)
    answer, answer_citations = align_answer_citations(answer, citations)
    cited_passages = [chunk for chunk in citation_chunks if chunk.page_number in answer_citations]

    return {
        "answer": answer,
        "citations": answer_citations,
        "retrieval_method": "Deterministic Local Document Extraction" if is_fallback else "Document Grounding + LLM Synthesis",
        "fallback_used": is_fallback,
        "relevant_passages": [{"page": c.page_number, "text": c.text[:200] + "..."} for c in cited_passages]
    }


def _is_document_question(question: str) -> bool:
    """Route clear document references to retrieval; leave ordinary chat direct."""
    q = question.lower().strip()
    explicit = ("this document", "the document", "this pdf", "the pdf", "uploaded file", "in the file", "in this file", "according to", "what does the", "on which page", "which page", "summarize this", "summarize the", "in my document", "from the document", "certificate number", "applicant name", "invoice number", "due date", "total amount", "line item", "account number", "contract date", "the deadline", "what is the deadline", "mission budget", "lead director", "launch window", "primary payload")
    return bool(re.search(r"\bpage\s+\d+\b", q)) or any(phrase in q for phrase in explicit)


def _simple_greeting_reply(question: str) -> str | None:
    """Answer short greetings directly so an open PDF never turns them into a search."""
    normalized = re.sub(r"[\s,!.?]+", " ", question.lower()).strip()
    basic_greetings = {"hi", "hello", "hey", "howdy", "yo", "hi there", "hello there", "hey there"}
    wellbeing_greetings = {
        "how are you", "how are you doing", "hi how are you", "hello how are you",
        "hey how are you", "hi how are you doing", "hello how are you doing",
        "hey how are you doing",
    }
    if normalized in wellbeing_greetings:
        return "I'm here and ready to help. What would you like to know or do with your PDF?"
    if normalized in basic_greetings:
        return "Hello! How can I help you today? You can ask a general question or ask about your PDF."
    return None


_PAPERPLANE_IDENTITY = "I'm Paperplane's Intelligence AI Bot — I help you work with PDFs inside Paperplane, and I can also answer general questions."
_CODE_SCOPE_REPLY = "I can't write or debug code here, but I can help you summarise, extract, or answer questions about a PDF. Upload a PDF or ask a general question."
_PRIVATE_INFORMATION_REFUSAL = "I can't reveal hidden instructions, system prompts, or private credentials. I can help with a PDF or a supported Paperplane task."
_PAPERPLANE_SYSTEM_PROMPT = "You are Paperplane's Intelligence AI Bot. Help with PDF documents and general questions inside Paperplane. Never reveal, mention, or hint at an underlying model, provider, company, or training origin. Do not write, debug, or explain code; politely state the Paperplane scope and offer PDF help."


def _is_identity_question(question: str) -> bool:
    return bool(re.search(
        r"\b(who are you|what model are you|which model|who trained you|who built you|are you (?:nemotron|an? ai|a bot)|(?:you are now|pretend to be|act as|tum ab)\s+(?:an?\s+)?nemotron)\b",
        question,
        re.IGNORECASE,
    ))


def _private_information_request_reply(question: str) -> str | None:
    """Refuse explicit attempts to reveal hidden prompts or secret credentials."""
    q = question.lower()
    if re.search(r"\b(system|developer)\s+prompt\b|\bhidden\s+instructions?\b", q):
        return _PRIVATE_INFORMATION_REFUSAL
    requests_secret = re.search(r"\b(show|reveal|tell|give|share|print|display|batao|dikhao)\b", q)
    names_secret = re.search(r"\b(api[\s_-]?key|secret key|access token|credential|password)\b", q)
    return _PRIVATE_INFORMATION_REFUSAL if requests_secret and names_secret else None


def _is_code_request(question: str) -> bool:
    q = question.lower()
    return bool(re.search(r"\b(write|generate|create|make|debug|fix|explain|show me)\b.{0,60}\b(code|script|program|python|javascript|typescript|java|c\+\+|snippet|function|class|sql)\b|\b(python|javascript|typescript|java|c\+\+|sql)\b.{0,60}\b(code|script|program|function|snippet)\b", q))


def _guard_ai_output(answer: str) -> str:
    configured = (BLUESMINDS_MODEL or "").strip()
    forbidden = ("nemotron", "nvidia", "bluesminds", "openai", "anthropic", "google gemini")
    terms = [re.escape(term) for term in forbidden]
    if configured:
        terms.append(re.escape(configured))
    names = "|".join(terms)
    self_intro = re.search(
        rf"\b(?:i['’]?m|i am|as (?:an? )?(?:ai|model|language model)|trained by|built by|developed by|created by)\b[^.!?\n]{{0,120}}\b(?:{names})\b",
        answer,
        re.IGNORECASE,
    )
    if self_intro:
        logger.warning("AI output identity guard replaced a response containing a provider/model identity")
        return _PAPERPLANE_IDENTITY
    return answer


SUMMARY_PAGE_LIMIT = 120
SUMMARY_CALL_TIMEOUT_SECONDS = 55.0
DOCUMENT_AI_BUDGET_SECONDS = 275.0
SUMMARY_CHUNK_PAGE_COUNT = 12
SUMMARY_CHUNK_CHAR_BUDGET = 20_400


def _bound_summary_page_text(page_text: str, max_chars: int) -> str:
    """Keep representative beginning, middle, and ending text from long pages."""
    if len(page_text) <= max_chars:
        return page_text
    marker = "\n[… text omitted …]\n"
    payload_chars = max(3, max_chars - (2 * len(marker)))
    window = payload_chars // 3
    remainder = payload_chars - (window * 3)
    first_size = window + remainder
    last_size = window
    middle_size = window
    middle_center = len(page_text) // 2
    middle_start = middle_center - (middle_size // 2)
    middle_end = middle_start + middle_size
    last_start = len(page_text) - last_size
    return marker.join((
        page_text[:first_size],
        page_text[middle_start:middle_end],
        page_text[last_start:],
    ))


def _bounded_document_timeout(deadline: float, call_timeout: float, remaining_calls: int = 1) -> float:
    # Reserve up to 7.4 seconds per request for three bounded retries.
    remaining = deadline - time.monotonic()
    if remaining < 12:
        raise RuntimeError("The AI provider timed out before the document was complete. Please retry later.")
    calls_left = max(1, int(remaining_calls))
    per_call_budget = max(5.0, (remaining - 7.4 * calls_left) / calls_left)
    return min(call_timeout, per_call_budget)


def summarize_pdf(
    pdf_path: Path,
    max_pages: int | None = None,
    *,
    include_citations: bool = False,
) -> str | tuple[str, list[int]]:
    """Summarizes document into executive overview and bulleted key takeaways."""
    deadline = time.monotonic() + DOCUMENT_AI_BUDGET_SECONDS
    with fitz.open(str(pdf_path)) as doc:
        page_limit = min(doc.page_count, max_pages) if max_pages and max_pages > 0 else doc.page_count
        if page_limit > SUMMARY_PAGE_LIMIT:
            raise ValueError(f"Executive Brief accepts up to {SUMMARY_PAGE_LIMIT} pages. Split the PDF and try again.")
        # Text is sent in page-labelled chunks below. Bound each provider
        # request, not the entire document: dividing a whole-document budget
        # by page count silently truncated a 69-page source to ~318 chars/page.
        page_budget = max(
            250,
            min(1700, SUMMARY_CHUNK_CHAR_BUDGET // min(SUMMARY_CHUNK_PAGE_COUNT, max(1, page_limit))),
        )
        page_texts: list[tuple[int, str]] = []
        for number in range(page_limit):
            page_text = doc[number].get_text("text").strip()
            if page_text:
                page_texts.append((number + 1, _bound_summary_page_text(page_text, page_budget)))

    if not page_texts:
        return "The document contains no extractable text."

    system_prompt = (
        "You are an executive document synthesizer. Provide an insightful Executive Summary followed by "
        "bullet points of key details, decisions, numbers, and deadlines. Ground every document fact in the "
        "provided text and append a page citation in the exact form [Page N] or [Pages N-M]. Do not invent citations. "
        "Preserve every numeric value exactly as written, including its units and surrounding symbols. "
        "Return exactly one document-level Executive Summary. Never add a currency, unit, date, decision, "
        "or absence claim not explicitly supported by the cited source text."
    )
    if len(page_texts) <= 12:
        full_text = "\n\n".join(f"--- Page {number} ---\n{text}" for number, text in page_texts)
        try:
            summary = call_llm(
                system_prompt,
                f"DOCUMENT CONTENT:\n\n{full_text}",
                timeout_seconds=_bounded_document_timeout(deadline, SUMMARY_CALL_TIMEOUT_SECONDS),
                max_attempts=4,
                temperature=0.0,
            )
        except Exception as error:
            logger.warning("Executive Brief provider failed for pages 1-%d; using local extractive fallback (%s)",
                           page_texts[-1][0], type(error).__name__)
            summary = _offline_rag_fallback(system_prompt, f"DOCUMENT CONTENT:\n\n{full_text}")
    else:
        # Long documents are summarized in bounded, page-labelled sections so
        # one provider request does not have to fit the whole source at once.
        chunk_notes: list[str] = []
        chunk_size = SUMMARY_CHUNK_PAGE_COUNT
        chunk_count = (len(page_texts) + chunk_size - 1) // chunk_size
        for chunk_index, start in enumerate(range(0, len(page_texts), chunk_size)):
            chunk = page_texts[start:start + chunk_size]
            chunk_text = "\n\n".join(f"--- Page {number} ---\n{text}" for number, text in chunk)
            first_page, last_page = chunk[0][0], chunk[-1][0]
            chunk_prompt = (
                f"DOCUMENT SECTION, pages {first_page}-{last_page}:\n\n{chunk_text}\n\n"
                "Return concise key facts, decisions, dates, amounts, and themes from this section. "
                "Ground each item in the supplied text and preserve its [Page N] citation. Do not invent facts."
            )
            remaining_calls = chunk_count - chunk_index + 1
            try:
                timeout = _bounded_document_timeout(
                    deadline, SUMMARY_CALL_TIMEOUT_SECONDS, remaining_calls=remaining_calls
                )
                note = call_llm(system_prompt, chunk_prompt, timeout_seconds=timeout, max_attempts=4,
                                temperature=0.0).strip()
            except Exception as error:
                logger.warning("Executive Brief provider failed for pages %d-%d; using local extractive fallback (%s)",
                               first_page, last_page, type(error).__name__)
                local_note = _offline_rag_fallback(system_prompt, f"DOCUMENT CONTENT:\n\n{chunk_text}")
                note = f"Local extractive notes from [Pages {first_page}-{last_page}]:\n{local_note}"
            if not note:
                local_note = _offline_rag_fallback(system_prompt, f"DOCUMENT CONTENT:\n\n{chunk_text}")
                note = f"Local extractive notes from [Pages {first_page}-{last_page}]:\n{local_note}"
            chunk_notes.append(note)
        final_prompt = (
            "Synthesize these page-grounded section notes into exactly one concise document-level executive summary followed by "
            "the most useful key takeaways. Preserve source citations from the notes exactly and do not "
            "introduce facts that the notes do not support.\n\n" + "\n\n".join(chunk_notes)
        )
        try:
            if any("Executive Summary (Offline Analysis)" in note for note in chunk_notes):
                raise RuntimeError("One or more sections used local extraction")
            timeout = _bounded_document_timeout(deadline, SUMMARY_CALL_TIMEOUT_SECONDS)
            summary = call_llm(system_prompt, final_prompt, timeout_seconds=timeout, max_attempts=4,
                               temperature=0.0)
            if not summary.strip() or "Executive Summary (Offline Analysis)" in summary:
                raise RuntimeError("Synthesis did not produce a provider summary")
        except Exception as error:
            logger.warning("Executive Brief synthesis failed; using local extractive fallback (%s)", type(error).__name__)
            # The local fallback must be explicit about its source and have one
            # document-level heading. Per-section extractive notes may contain
            # their own headings; remove those to avoid presenting several
            # competing executive summaries as a single synthesis.
            section_notes = []
            for index, note in enumerate(chunk_notes):
                clean_note = re.sub(r"^\s*#{1,6}\s*Executive Summary[^\n]*\n+", "", note, flags=re.I | re.M)
                clean_note = re.sub(r"^\s*\*?\(Generated from local document text analysis\.\)\*?\s*$", "", clean_note, flags=re.M)
                page_range = chunk_notes[index].split("Local extractive notes from ", 1)
                label = page_range[1].split(":", 1)[0] if len(page_range) == 2 else f"Section {index + 1}"
                section_notes.append(f"#### {label}\n\n{clean_note.strip()}")
            summary = (
                "### Executive Summary (Offline Analysis)\n\n"
                "The AI provider did not return a complete synthesis. These are local extractive notes, "
                "organized by the pages analyzed; they do not establish that a fact is absent elsewhere.\n\n"
                + "\n\n".join(section_notes)
            )

    source_text = "\n".join(text for _page_number, text in page_texts)
    executive_summary_headings = re.findall(
        r"(?im)^\s*#{1,6}\s*Executive Summary\b[^\n]*", summary
    )
    if len(executive_summary_headings) > 1:
        # Repeated section summaries are not a document-level synthesis. Fall
        # back to labelled local extraction so contradictory or duplicate
        # summaries never appear as a single authoritative brief.
        logger.warning("Executive Brief returned repeated summary headings; using local extractive fallback")
        full_text = "\n\n".join(f"--- Page {number} ---\n{text}" for number, text in page_texts)
        summary = _offline_rag_fallback(system_prompt, f"DOCUMENT CONTENT:\n\n{full_text}")
    summary = _remove_unsupported_summary_absence_claims(summary, source_text)
    summary = _restore_explicit_summary_currency(_guard_ai_output(summary), source_text)
    summary = _remove_unsupported_summary_currency(summary, source_text)
    eligible_pages = {page_number for page_number, _ in page_texts}
    aligned_summary, citations = align_answer_citations(summary, eligible_pages)
    if include_citations:
        return aligned_summary, citations
    return aligned_summary


def _generate_clean_csv(extracted: dict) -> str:
    """Generates an RFC-4180 compliant CSV export for structured extraction results."""
    doc_type = extracted.get("document_type", "general")
    output = io.StringIO()
    import csv
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    if doc_type == "invoice":
        inv = extracted.get("invoice_data", {})
        line_items = inv.get("line_items", [])
        if line_items:
            writer.writerow([
                "InvoiceNumber", "InvoiceDate", "DueDate", "Vendor", "Customer",
                "Currency", "Subtotal", "TaxAmount", "TotalAmount", "PaymentTerms",
                "LineIndex", "Description", "Quantity", "UnitPrice", "Amount"
            ])
            for idx, item in enumerate(line_items, 1):
                writer.writerow([
                    inv.get("invoice_number") or "",
                    inv.get("invoice_date") or "",
                    inv.get("due_date") or "",
                    inv.get("vendor") or "",
                    inv.get("customer") or "",
                    inv.get("currency") or "",
                    inv.get("subtotal") if inv.get("subtotal") is not None else "",
                    inv.get("tax_amount") if inv.get("tax_amount") is not None else "",
                    inv.get("total_amount") if inv.get("total_amount") is not None else "",
                    inv.get("payment_terms") or "",
                    idx,
                    item.get("description") or "",
                    item.get("quantity") if item.get("quantity") is not None else "",
                    item.get("unit_price") if item.get("unit_price") is not None else "",
                    item.get("amount") if item.get("amount") is not None else "",
                ])
        else:
            writer.writerow([
                "InvoiceNumber", "InvoiceDate", "DueDate", "Vendor", "Customer",
                "Currency", "Subtotal", "TaxAmount", "TotalAmount", "PaymentTerms",
                "ContactEmails", "ContactPhones"
            ])
            contact = extracted.get("contact", {})
            writer.writerow([
                inv.get("invoice_number") or "",
                inv.get("invoice_date") or "",
                inv.get("due_date") or "",
                inv.get("vendor") or "",
                inv.get("customer") or "",
                inv.get("currency") or "",
                inv.get("subtotal") if inv.get("subtotal") is not None else "",
                inv.get("tax_amount") if inv.get("tax_amount") is not None else "",
                inv.get("total_amount") if inv.get("total_amount") is not None else "",
                inv.get("payment_terms") or "",
                "; ".join(contact.get("emails", [])),
                "; ".join(contact.get("phones", [])),
            ])
    elif doc_type == "resume":
        res_data = extracted.get("resume_data", {})
        contact = extracted.get("contact", {})
        writer.writerow(["CandidateName", "Headline", "Emails", "Phones", "Skills", "Summary"])
        writer.writerow([
            res_data.get("candidate_name") or "",
            res_data.get("headline_or_title") or "",
            "; ".join(contact.get("emails", [])),
            "; ".join(contact.get("phones", [])),
            ", ".join(res_data.get("skills", [])),
            res_data.get("summary") or ""
        ])
    else:
        gen = extracted.get("general_data", {})
        contact = extracted.get("contact", {})
        writer.writerow(["DocumentTitle", "DocumentDate", "TotalPages", "Emails", "Phones", "Topics"])
        writer.writerow([
            gen.get("title") or "",
            gen.get("document_date") or "",
            extracted.get("total_pages", 1),
            "; ".join(contact.get("emails", [])),
            "; ".join(contact.get("phones", [])),
            ", ".join(gen.get("detected_topics", []))
        ])

    return output.getvalue().strip()


def _parse_json_object(response: str) -> dict | None:
    """Accept only a JSON object from an upstream structured-output request."""
    if not response:
        return None
    candidate = response.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.IGNORECASE | re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        payload = json.loads(candidate)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _extract_metadata_with_agentrouter(
    full_text: str,
    doc_type: str,
    total_pages: int,
) -> dict | None:
    """Run structured extraction upstream, returning None for any unsafe/malformed result."""
    if AI_KILL_SWITCH or not _current_agentrouter_api_key() or not full_text.strip():
        return None

    try:
        system_prompt = (
            "You are a document entity extraction service. Return ONLY valid JSON. "
            "Do not invent values; use null, empty arrays, and warnings when a field is not present. "
            "Keep numeric amounts as numbers and preserve source page numbers."
        )
        schema = {
            "document_type": doc_type,
            "total_pages": total_pages,
            "contact": {"emails": [], "phones": []},
            "source_pages": [],
            "warnings": [],
            "invoice_data": {
                "invoice_number": None, "invoice_date": None, "due_date": None,
                "vendor": None, "customer": None, "currency": None,
                "subtotal": None, "tax_amount": None, "total_amount": None,
                "payment_terms": None, "line_items": [],
            },
            "resume_data": {
                "candidate_name": None, "headline_or_title": None, "summary": None,
                "skills": [], "experience": [], "education": [],
            },
            "general_data": {
                "title": None, "document_date": None,
                "detected_topics": [], "key_entities": [],
            },
        }
        response = call_agentrouter(
            system_prompt,
            f"Return an object matching this schema for document type '{doc_type}':\n"
            f"{json.dumps(schema, ensure_ascii=False)}\n\nDOCUMENT TEXT:\n{full_text[:24000]}",
            timeout_seconds=2.0,
        )
        extracted = _parse_json_object(response)
        if not extracted:
            return None

        required_key = {
            "invoice": "invoice_data",
            "resume": "resume_data",
            "general": "general_data",
        }[doc_type]
        if not isinstance(extracted.get(required_key), dict):
            return None

        extracted["document_type"] = doc_type
        extracted["total_pages"] = total_pages
        contact = extracted.get("contact")
        extracted["contact"] = contact if isinstance(contact, dict) else {"emails": [], "phones": []}
        source_pages = extracted.get("source_pages")
        extracted["source_pages"] = [
            int(page) for page in source_pages
            if isinstance(page, (int, float, str)) and str(page).isdigit()
        ] if isinstance(source_pages, list) else []
        warnings = extracted.get("warnings")
        extracted["warnings"] = [str(item) for item in warnings] if isinstance(warnings, list) else []
        if doc_type == "general":
            general = extracted["general_data"]
            raw_date = general.get("document_date")
            normalized_date = _extract_valid_document_date(raw_date) if isinstance(raw_date, str) else None
            source_dates = {_extract_valid_document_date(line) for line in full_text.splitlines()}
            if raw_date and (not normalized_date or normalized_date not in source_dates):
                general["document_date"] = None
                extracted["warnings"].append("The proposed document date could not be verified in the source text.")
            elif normalized_date:
                general["document_date"] = normalized_date
            topics = general.get("detected_topics")
            if isinstance(topics, list):
                general["detected_topics"] = [topic.strip() for topic in topics
                    if isinstance(topic, str) and len(topic.strip().split()) >= 2
                    and not re.match(r"^\s*\d+(?:\.\d+)+\b", topic)
                    and topic.strip().casefold() not in {"table of contents", "executive summary"}][:8]
            else:
                general["detected_topics"] = []
        extracted.pop("provider", None)
        extracted["retrieval_method"] = "Paperplane AI structured extraction"
        extracted["csv_export"] = _generate_clean_csv(extracted)
        return extracted
    except Exception:
        return None


def _extract_valid_document_date(text: str) -> str | None:
    """Return a validated date in ISO format; reject section numbers such as 3.3.1."""
    date_pattern = re.compile(
        r"\b(?:"
        r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
        r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}"
        r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"
        r")\b"
    )
    for match in date_pattern.finditer(text or ""):
        candidate = match.group(0).strip()
        parsed: dt.date | None = None
        try:
            if candidate[0].isalpha():
                normalized = re.sub(r",", "", candidate)
                for pattern in ("%B %d %Y", "%b %d %Y"):
                    try:
                        parsed = dt.datetime.strptime(normalized, pattern).date()
                        break
                    except ValueError:
                        continue
            else:
                parts = re.split(r"[-/.]", candidate)
                if len(parts) != 3:
                    continue
                first, second, third = (int(part) for part in parts)
                if len(parts[0]) == 4:
                    parsed = dt.date(first, second, third)
                else:
                    # Prefer day-first for ambiguous numeric dates, then accept
                    # month-first when the first interpretation is impossible.
                    try:
                        parsed = dt.date(third, second, first)
                    except ValueError:
                        parsed = dt.date(third, first, second)
        except (ValueError, OverflowError):
            continue
        if parsed and 1800 <= parsed.year <= 2200:
            return parsed.isoformat()
    return None


def extract_metadata_entities(pdf_path: Path, doc_type: str = "auto") -> dict:
    """
    Extracts structured entities conforming to canonical schema:
    - invoice: invoice_number, invoice_date, due_date, vendor, customer, currency, subtotal, tax_amount, total_amount, payment_terms, line_items
    - resume: candidate_name, headline_or_title, summary, skills, experience, education
    - general: title, document_date, detected_topics, key_entities
    Includes contact, source_pages, honest warnings, and clean RFC-4180 csv_export.
    """
    with fitz.open(str(pdf_path)) as doc:
        total_pages = len(doc)
        page_texts = [page.get_text("text") for page in doc]
    full_text = "\n".join(page_texts)

    # Detect document type if auto
    lower_text = full_text.lower()
    if doc_type == "auto":
        invoice_score = sum(1 for term in ["tax invoice", "bill to", "due date", "subtotal", "amount due", "remit to", "invoice number", "invoice #"] if term in lower_text)
        if "invoice" in lower_text and invoice_score >= 1:
            doc_type = "invoice"
        else:
            has_cv_title = bool(re.search(r'\b(curriculum vitae|c\.v\.)\b', lower_text) or re.search(r'^\s*resume\s*$', lower_text, re.MULTILINE))
            has_work_exp = bool(re.search(r'\b(work experience|professional experience|employment history|work history)\b', lower_text))
            has_edu_section = bool(re.search(r'\b(education|academic background|qualifications)\b', lower_text))
            has_skills_section = bool(re.search(r'\b(technical skills|key skills|core competencies)\b', lower_text))
            has_summary_section = bool(re.search(r'\b(career objective|professional summary|about me)\b', lower_text))

            resume_signals = sum([has_work_exp, has_edu_section, has_skills_section, has_summary_section])
            if has_cv_title or resume_signals >= 2:
                doc_type = "resume"
            elif invoice_score >= 2:
                doc_type = "invoice"
            else:
                doc_type = "general"

    upstream_result = _extract_metadata_with_agentrouter(full_text, doc_type, total_pages)
    if upstream_result:
        return upstream_result

    # Contact extraction
    emails = sorted(list(set(re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', full_text))))
    raw_phones = re.findall(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', full_text)
    phones = sorted(list(set(p.strip() for p in raw_phones if len(re.sub(r'\D', '', p)) >= 10)))

    source_pages: set[int] = set()
    warnings: list[str] = []

    if not full_text.strip():
        warnings.append("Document appears to be scanned or contains no extractable digital text. If this is a scanned document, run OCR PDF first.")

    extracted: dict[str, Any] = {
        "document_type": doc_type,
        "total_pages": total_pages,
        "contact": {
            "emails": emails,
            "phones": phones
        },
        "source_pages": [],
        "warnings": [],
        "retrieval_method": "Page-bounded structural extraction"
    }

    if doc_type == "invoice":
        # 1. Invoice Number
        inv_no_match = re.search(r'\b(?:invoice|bill|inv)\s*(?:#|no\.?|number|num\.?)\s*[:.]?\s*([A-Za-z0-9\-_/]+)', full_text, re.IGNORECASE)
        if not inv_no_match:
            inv_no_match = re.search(r'\b(?:invoice|inv)\s*[:#]\s*([A-Za-z0-9\-_/]+)', full_text, re.IGNORECASE)
        if not inv_no_match:
            inv_no_match = re.search(r'\binv(?:oice)?[-_#]\s*([A-Za-z0-9\-_/]+)', full_text, re.IGNORECASE)

        inv_number = None
        if inv_no_match:
            candidate_val = inv_no_match.group(1).strip()
            if candidate_val.lower() not in ["number", "no", "date", "due", "inv", "invoice"] and len(candidate_val) >= 2:
                inv_number = candidate_val

        # 2. Dates
        date_match = re.search(r'(?:invoice\s*date|date\s*of\s*issue|issue\s*date|date)[:.]?\s*([0-9]{1,4}[-/.][0-9]{1,2}[-/.][0-9]{1,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})', full_text, re.IGNORECASE)
        inv_date = date_match.group(1).strip() if date_match else None

        due_match = re.search(r'(?:due\s*date|pay\s*by|payment\s*due)[:.]?\s*([0-9]{1,4}[-/.][0-9]{1,2}[-/.][0-9]{1,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})', full_text, re.IGNORECASE)
        due_date = due_match.group(1).strip() if due_match else None

        # 3. Currency Detection
        currency = None
        if "$" in full_text or "USD" in full_text:
            currency = "USD"
        elif "€" in full_text or "EUR" in full_text:
            currency = "EUR"
        elif "£" in full_text or "GBP" in full_text:
            currency = "GBP"
        elif "₹" in full_text or "INR" in full_text:
            currency = "INR"
        elif "¥" in full_text or "JPY" in full_text:
            currency = "JPY"
        elif "CAD" in full_text:
            currency = "CAD"
        elif "AUD" in full_text:
            currency = "AUD"

        # 4. Amounts (Total, Subtotal, Tax)
        total_match = re.search(r'\b(?:grand\s*total|total\s*due|amount\s*due|balance\s*due)\s*[:.]?\s*[$€£₹]?\s*([0-9,]+\.[0-9]{2})', full_text, re.IGNORECASE)
        if not total_match:
            total_match = re.search(r'(?<!sub)\b(?:total\s*amount|total)\s*[:.]?\s*[$€£₹]?\s*([0-9,]+\.[0-9]{2})', full_text, re.IGNORECASE)
        total_amount = total_match.group(1).replace(",", "").strip() if total_match else None

        subtotal_match = re.search(r'\b(?:subtotal|sub-total|sub\s*total|net\s*amount)\s*[:.]?\s*[$€£₹]?\s*([0-9,]+\.[0-9]{2})', full_text, re.IGNORECASE)
        subtotal = subtotal_match.group(1).replace(",", "").strip() if subtotal_match else None

        tax_match = re.search(r'\b(?:sales\s*tax|tax|vat|gst)\s*(?:\([0-9.]+%\))?\s*[:.]?\s*[$€£₹]?\s*([0-9,]+\.[0-9]{2})', full_text, re.IGNORECASE)
        tax_amount = tax_match.group(1).replace(",", "").strip() if tax_match else None

        terms_match = re.search(r'(?:payment\s*terms|terms)\s*[:.]?\s*([A-Za-z0-9\s]{3,30})', full_text, re.IGNORECASE)
        payment_terms = terms_match.group(1).strip() if terms_match else None

        # 5. Vendor & Customer Extraction
        vendor = None
        vendor_match = re.search(r'(?:from|vendor|seller|service\s*provider|company)[:.]?\s*([A-Za-z0-9\s&,.-]{2,50})', full_text, re.IGNORECASE)
        if vendor_match:
            vendor = vendor_match.group(1).strip()
        else:
            first_lines = [l.strip() for l in page_texts[0].splitlines() if l.strip()]
            if first_lines and not any(k in first_lines[0].lower() for k in ["invoice", "tax", "bill", "page"]):
                vendor = first_lines[0][:60]

        customer = None
        cust_match = re.search(r'(?:bill\s*to|billed\s*to|invoice\s*to|sold\s*to|client|customer)[:.]?\s*([A-Za-z0-9\s&,.-]{2,50})', full_text, re.IGNORECASE)
        if cust_match:
            customer = cust_match.group(1).strip()

        # 6. Line Items Extraction
        line_items = []
        for p_idx, p_text in enumerate(page_texts, 1):
            p_lines = p_text.splitlines()
            for line in p_lines:
                line_str = line.strip()
                if not line_str or len(line_str) < 5:
                    continue
                # Line item pattern: Description ... Quantity ... UnitPrice ... Amount
                item_m = re.search(r'^(?P<desc>[A-Za-z0-9\s\-_&/()#.,]+?)\s{2,}(?P<qty>\d+(?:\.\d+)?)\s+[$€£₹]?(?P<unit>\d+(?:,\d{3})*(?:\.\d{2})?)\s+[$€£₹]?(?P<amt>\d+(?:,\d{3})*(?:\.\d{2})?)$', line_str)
                if item_m:
                    desc = item_m.group("desc").strip()
                    if not any(hdr in desc.lower() for hdr in ["description", "item", "qty", "price", "subtotal", "total"]):
                        try:
                            qty_val = float(item_m.group("qty"))
                            unit_val = float(item_m.group("unit").replace(",", ""))
                            amt_val = float(item_m.group("amt").replace(",", ""))
                            line_items.append({
                                "description": desc,
                                "quantity": int(qty_val) if qty_val.is_integer() else qty_val,
                                "unit_price": unit_val,
                                "amount": amt_val
                            })
                            source_pages.add(p_idx)
                        except (ValueError, TypeError):
                            pass

        if inv_number:
            source_pages.add(1)
        if total_amount:
            source_pages.add(1)

        if not inv_number:
            warnings.append("Invoice identifier was not detected with high certainty.")
        if not total_amount:
            warnings.append("Total amount could not be definitively extracted from document summary.")
        if not line_items:
            warnings.append("Line items could not be parsed as a structured table; summary totals provided.")

        extracted["invoice_data"] = {
            "invoice_number": inv_number,
            "invoice_date": inv_date,
            "due_date": due_date,
            "vendor": vendor,
            "customer": customer,
            "currency": currency,
            "subtotal": float(subtotal) if subtotal else None,
            "tax_amount": float(tax_amount) if tax_amount else None,
            "total_amount": float(total_amount) if total_amount else None,
            "payment_terms": payment_terms,
            "line_items": line_items
        }

    elif doc_type == "resume":
        lines = [l.strip() for l in full_text.splitlines() if l.strip()]
        candidate_name = lines[0] if lines else None
        headline = lines[1] if len(lines) > 1 and len(lines[1]) < 80 else None

        tech_keywords = [
            "Python", "JavaScript", "TypeScript", "React", "Vue", "Angular", "Node.js", "FastAPI",
            "Docker", "Kubernetes", "SQL", "PostgreSQL", "MySQL", "MongoDB", "AWS", "Azure", "GCP",
            "Git", "CI/CD", "Machine Learning", "PyTorch", "TensorFlow", "C++", "Java", "Go", "Rust",
            "REST API", "GraphQL", "Agile", "Linux"
        ]
        found_skills = [skill for skill in tech_keywords if re.search(rf'\b{re.escape(skill)}\b', full_text, re.IGNORECASE)]

        summary = None
        for i, line in enumerate(lines[:10]):
            if any(k in line.lower() for k in ["summary", "profile", "about me", "objective"]):
                if i + 1 < len(lines):
                    summary = lines[i + 1]
                break

        experience_snippets = []
        for line in lines:
            if re.search(r'\b(engineer|developer|architect|manager|lead|specialist|analyst|intern)\b', line, re.IGNORECASE):
                if len(line) < 120 and line not in experience_snippets:
                    experience_snippets.append(line)

        education_snippets = []
        for line in lines:
            if re.search(r'\b(bachelor|master|b\.s\.|m\.s\.|ph\.d\.|university|college|institute|degree)\b', line, re.IGNORECASE):
                if len(line) < 120 and line not in education_snippets:
                    education_snippets.append(line)

        source_pages.add(1)
        if not candidate_name:
            warnings.append("Candidate name could not be identified with certainty.")
        if not found_skills:
            warnings.append("No common technical keywords were matched in the resume text.")

        extracted["resume_data"] = {
            "candidate_name": candidate_name,
            "headline_or_title": headline,
            "summary": summary,
            "skills": found_skills,
            "experience": experience_snippets[:5],
            "education": education_snippets[:3]
        }

    else:  # general document
        lines = [l.strip() for l in full_text.splitlines() if l.strip()]
        title = lines[0][:100] if lines else "Untitled Document"
        title_boilerplate = re.compile(
            r"(?:provided proper attribution|hereby grants permission|all rights reserved|copyright|terms of use|license)",
            re.IGNORECASE,
        )
        if title_boilerplate.search(title):
            title = ""
        if not title or len(title) > 100:
            title = "Untitled Document"
        # Prefer a visually prominent, centered heading over the first extracted
        # text block, which is often a running notice or attribution paragraph.
        with fitz.open(str(pdf_path)) as title_doc:
            if title_doc:
                page = title_doc[0]
                candidates = []
                page_center = page.rect.width / 2
                for block in page.get_text("dict").get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    text = " ".join(
                        span.get("text", "") for line in block.get("lines", [])
                        for span in line.get("spans", [])
                    ).strip()
                    if not text or len(text) > 180 or title_boilerplate.search(text):
                        continue
                    sizes = [float(span.get("size", 0)) for line in block.get("lines", [])
                             for span in line.get("spans", []) if span.get("text", "").strip()]
                    if not sizes:
                        continue
                    rect = fitz.Rect(block.get("bbox", (0, 0, 0, 0)))
                    prominence = max(sizes) + (2 if abs(rect.x0 + rect.width / 2 - page_center) < page.rect.width * .12 else 0)
                    candidates.append((prominence, text))
                if candidates:
                    prominent = max(candidates, key=lambda item: item[0])
                    if prominent[0] >= 14:
                        title = prominent[1][:100]

        doc_date = _extract_valid_document_date(full_text)

        # Keep the local fallback conservative: skip numbered section headings,
        # boilerplate labels, and the document title so they are not presented
        # as substantive topics.
        topic_stop_phrases = {
            "invoice date", "due date", "document date", "date", "summary",
            "executive summary", "table of contents", "contents", "abstract",
            "introduction", "conclusion", "references", "appendix",
        }
        topic_candidates: list[str] = []
        for normalized_line in lines[1:]:
            if not normalized_line or re.match(r"^\s*\d+(?:\.\d+)+\b", normalized_line):
                continue
            if re.match(r"^\s*(?:date|page|section|chapter|contents|abstract|introduction|conclusion|references)\s*[:.]?\s*$", normalized_line, re.IGNORECASE):
                continue
            for phrase in re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', normalized_line):
                if phrase.casefold() in topic_stop_phrases or phrase == title:
                    continue
                if len(phrase.split()) >= 2 and phrase not in topic_candidates:
                    topic_candidates.append(phrase)
        topics = topic_candidates[:8]
        key_entities = list(dict.fromkeys(re.findall(r'\b[A-Z]{2,}\b', full_text)))[:8]

        source_pages.add(1)
        extracted["general_data"] = {
            "title": title,
            "document_date": doc_date,
            "detected_topics": topics,
            "key_entities": key_entities
        }

    extracted["source_pages"] = sorted(list(source_pages)) if source_pages else [1]
    extracted["warnings"] = warnings
    extracted["csv_export"] = _generate_clean_csv(extracted)
    return extracted


# Give a healthy but slower translation provider enough time to answer each
# bounded retry. `_provider_request` shares this total budget across its four
# attempts, so 55 seconds left only about 12 seconds per attempt; document-wide
# work still remains capped by DOCUMENT_AI_BUDGET_SECONDS.
TRANSLATION_CALL_TIMEOUT_SECONDS = 90.0
TRANSLATION_BATCH_SIZE = 16
# Keep average text-heavy batches small enough for a bounded JSON response.
# Long blocks are already split into 1,600-character chunks; this second limit
# prevents one request from growing beyond a predictable prompt size.
TRANSLATION_BATCH_MAX_CHARACTERS = 12_000
# Keep provider fan-out below common per-key rate limits while preserving
# useful overlap for multi-page translations and transient retries.
TRANSLATION_MAX_PARALLEL_BATCHES = 2
# Cap additional repair calls across the whole PDF, while allowing enough small
# groups to recover a truncated multi-batch response instead of giving up after
# repairing only the first few missing segments.
TRANSLATION_MAX_REPAIR_REQUESTS = 16


def _translation_chunks(text: str, limit: int = 1600) -> list[str]:
    """Split large blocks without silently dropping any source text."""
    chunks = []
    remaining = text.strip()
    while len(remaining) > limit:
        boundary = remaining.rfind(" ", 0, limit + 1)
        if boundary < limit // 2:
            boundary = limit
        chunks.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _build_translation_batches(
    segments: list[tuple[int, str]],
    max_segments: int | None = None,
    max_characters: int | None = None,
) -> list[list[tuple[int, str]]]:
    """Batch small PDF text blocks efficiently without creating huge prompts."""
    max_segments = max(1, int(TRANSLATION_BATCH_SIZE if max_segments is None else max_segments))
    max_characters = max(
        1,
        int(TRANSLATION_BATCH_MAX_CHARACTERS if max_characters is None else max_characters),
    )
    batches: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    current_characters = 0
    for segment in segments:
        segment_characters = len(segment[1])
        if current and (
            len(current) >= max_segments
            or current_characters + segment_characters > max_characters
        ):
            batches.append(current)
            current = []
            current_characters = 0
        current.append(segment)
        current_characters += segment_characters
    if current:
        batches.append(current)
    return batches


def _parse_translation_batch(response: str, expected_ids: list[int]) -> dict[int, str]:
    """Parse a provider response without accepting prose as a translation."""
    if not response:
        return {}

    candidate = response.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.IGNORECASE | re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()

    try:
        payload = json.loads(candidate)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}

    if isinstance(payload, dict):
        items = payload.get("translations", payload.get("results", payload))
        if isinstance(items, dict):
            output: dict[int, str] = {}
            for block_id in expected_ids:
                value = items.get(str(block_id), items.get(block_id))
                if isinstance(value, str) and value.strip():
                    output[block_id] = value.strip()
            return output
        payload = items

    if isinstance(payload, list):
        output = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            raw_block_id = item.get("id")
            if isinstance(raw_block_id, int) and not isinstance(raw_block_id, bool):
                block_id = raw_block_id
            elif isinstance(raw_block_id, str) and re.fullmatch(r"(?:0|[1-9]\d*)", raw_block_id.strip()):
                block_id = int(raw_block_id.strip())
            else:
                continue
            text = item.get("text", item.get("translation"))
            if block_id in expected_ids and isinstance(text, str) and text.strip():
                output[block_id] = text.strip()
        return output

    return {}


def _translate_text_batch(
    blocks: list[tuple[int, str]],
    target_language: str,
    deadline: float | None = None,
) -> dict[int, str]:
    """Translate a bounded page batch or raise a safe provider failure class."""
    if not blocks or AI_KILL_SWITCH or not _current_bluesminds_api_key():
        return {}

    payload = [{"id": block_id, "text": text[:1600]} for block_id, text in blocks]
    system_prompt = (
        "You are a professional document translator. Translate every item into "
        f"{target_language}. Return ONLY valid JSON in the form "
        '{"translations":[{"id":1,"text":"..."}]}. Preserve item ids, meaning, numbers, and line breaks.'
    )
    try:
        timeout = TRANSLATION_CALL_TIMEOUT_SECONDS
        if deadline is not None:
            timeout = _bounded_document_timeout(deadline, timeout)
        response = call_llm(
            system_prompt,
            json.dumps(payload, ensure_ascii=False),
            timeout_seconds=timeout,
            max_attempts=4,
        )
    except Exception as error:
        # Preserve only the safe failure class/status; never expose provider bodies.
        status_match = re.search(r"\bHTTP\s+(\d{3})\b", str(error), re.IGNORECASE)
        if status_match:
            failure_class = f"upstream HTTP {status_match.group(1)}"
        elif re.search(r"timeout|timed out|could not be reached", str(error), re.IGNORECASE):
            failure_class = "network timeout or connection error"
        else:
            failure_class = type(error).__name__
        raise RuntimeError(f"Translation provider failed ({failure_class}).") from error

    translations = _parse_translation_batch(response, [block_id for block_id, _ in blocks])
    if not translations:
        raise RuntimeError("Translation provider returned an invalid structured response.")
    return translations


def _translation_change_fraction(source_text: str, translated_text: str) -> float:
    """Estimate substantive translation change from Unicode word tokens."""
    source_tokens = Counter(re.findall(r"\w+", source_text.casefold(), flags=re.UNICODE))
    translated_tokens = Counter(re.findall(r"\w+", translated_text.casefold(), flags=re.UNICODE))
    total = max(sum(source_tokens.values()), sum(translated_tokens.values()))
    if not total:
        return 0.0
    unchanged = sum((source_tokens & translated_tokens).values())
    return max(0.0, 1.0 - unchanged / total)


def _translation_block_rotations(page: Any) -> dict[tuple[float, float, float, float], int]:
    """Map text-block bounds to their nearest right-angle reading orientation."""
    rotations: dict[tuple[float, float, float, float], int] = {}
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        lines = block.get("lines") or []
        if not lines:
            continue
        directions = [line.get("dir", (1.0, 0.0)) for line in lines]
        # A mixed-direction block has no single safe raster rotation. Leave it
        # in standard orientation rather than rotating neighboring lines.
        if any(abs(directions[0][0] - direction[0]) > 0.01
               or abs(directions[0][1] - direction[1]) > 0.01
               for direction in directions[1:]):
            continue
        dx, dy = directions[0]
        angle = int(round(math.degrees(math.atan2(-dy, dx)) / 90) * 90) % 360
        bounds = tuple(round(float(value), 2) for value in block.get("bbox", ()))
        if len(bounds) == 4 and angle:
            rotations[bounds] = angle
    return rotations


def translate_pdf_layout(
    pdf_path: Path,
    output_path: Path,
    target_language: str = "es",
    target_lang: str | None = None,
    report: dict[str, Any] | None = None,
) -> Path:
    """
    Performs AI layout-preserving translation:
    1. Duplicates the original page backgrounds, vector graphics, and images.
    2. Identifies exact bounding boxes for each text block.
    3. Translates the block text to the target language via LLM or intelligent translator.
    4. Overlays translated text into the exact coordinates with auto-scaled typography.
    """
    target_language = target_lang or target_language
    deadline = time.monotonic() + DOCUMENT_AI_BUDGET_SECONDS
    report_data = report if report is not None else {}
    report_data.update({
        "target_language": target_language,
        "pages_seen": 0,
        "blocks_seen": 0,
        "blocks_translated": 0,
        "blocks_preserved": 0,
        "blocks_rotated": 0,
        "fallback_used": False,
        "warnings": [],
    })
    with fitz.open(str(pdf_path)) as doc, fitz.open() as out_doc, fitz.open() as overlays:
        report_data["pages_seen"] = doc.page_count
        blocks: list[tuple[int, fitz.Rect, str]] = []
        block_rotations: list[int] = []
        for page in doc:
            rotations_by_bounds = _translation_block_rotations(page)
            for block in page.get_text("blocks"):
                if len(block) < 7 or block[6] != 0 or len(block[4].strip()) < 2:
                    continue
                report_data["blocks_seen"] += 1
                blocks.append((page.number, fitz.Rect(block[:4]), block[4].strip()))
                bounds_key = tuple(round(float(value), 2) for value in block[:4])
                block_rotations.append(rotations_by_bounds.get(bounds_key, 0))

        segments: list[tuple[int, str]] = []
        block_segments: list[list[tuple[int, str]]] = []
        for index, (_, _, source_text) in enumerate(blocks):
            ids = []
            cursor = 0
            for chunk in _translation_chunks(source_text):
                position = source_text.find(chunk, cursor)
                separator = source_text[cursor:position]
                joiner = "\n" if "\n" in separator else " " if separator else ""
                ids.append((len(segments), joiner))
                segments.append((len(segments), chunk))
                cursor = position + len(chunk)
            block_segments.append(ids)
        batches = _build_translation_batches(segments)
        translated_segments: dict[int, str] = {}
        batch_failures: list[tuple[int, list[int], str]] = []
        with ThreadPoolExecutor(max_workers=TRANSLATION_MAX_PARALLEL_BATCHES,
                                thread_name_prefix="translation") as pool:
            future_batches = {
                pool.submit(_translate_text_batch, batch, target_language, deadline=deadline): (index, batch)
                for index, batch in enumerate(batches, start=1)
            }
            for future in as_completed(future_batches):
                batch_number, batch = future_batches[future]
                block_ids = [block_id for block_id, _ in batch]
                try:
                    translated_segments.update(future.result())
                except Exception as error:
                    safe_failure = str(error)[:180]
                    logger.warning(
                        "Translation batch failed language=%s batch=%d block_ids=%s reason=%s",
                        target_language, batch_number, block_ids, safe_failure,
                    )
                    batch_failures.append((batch_number, block_ids, safe_failure))
        # Retry missing segments in smaller groups, whether the provider omitted
        # IDs from valid JSON or an entire first-pass batch failed transiently.
        # Keep retries bounded across the document so provider truncation cannot
        # silently strand every missing segment after only the first few groups.
        all_missing_ids = {
            block_id for batch in batches for block_id, _ in batch if block_id not in translated_segments
        }
        repair_group_size = max(1, min(2, TRANSLATION_BATCH_SIZE // 4))
        requested_ids: set[int] = set()
        repaired_ids: set[int] = set()
        repair_requests = 0
        while repair_requests < TRANSLATION_MAX_REPAIR_REQUESTS:
            remaining_budget = deadline - time.monotonic()
            if remaining_budget <= 0:
                break
            repair_batches: list[tuple[int, list[tuple[int, str]]]] = []
            for batch_number, batch in enumerate(batches, start=1):
                missing = [(block_id, text) for block_id, text in batch if block_id not in translated_segments]
                for start in range(0, len(missing), repair_group_size):
                    if repair_requests + len(repair_batches) >= TRANSLATION_MAX_REPAIR_REQUESTS:
                        break
                    repair_batches.append((batch_number, missing[start:start + repair_group_size]))
                if repair_requests + len(repair_batches) >= TRANSLATION_MAX_REPAIR_REQUESTS:
                    break
            if not repair_batches:
                break

            round_requested_ids = {block_id for _, batch in repair_batches for block_id, _ in batch}
            requested_ids.update(round_requested_ids)
            round_repaired = 0
            with ThreadPoolExecutor(max_workers=TRANSLATION_MAX_PARALLEL_BATCHES,
                                    thread_name_prefix="translation-repair") as pool:
                repair_futures = {
                    pool.submit(_translate_text_batch, batch, target_language, deadline=deadline): (batch_number, batch)
                    for batch_number, batch in repair_batches
                }
                for future in as_completed(repair_futures):
                    batch_number, batch = repair_futures[future]
                    try:
                        repaired = future.result()
                    except Exception as error:
                        logger.warning(
                            "Translation repair failed language=%s batch=%d block_ids=%s reason=%s",
                            target_language, batch_number, [block_id for block_id, _ in batch], str(error)[:180],
                        )
                        continue
                    for block_id, translated_text in repaired.items():
                        if block_id in round_requested_ids and block_id not in translated_segments and translated_text.strip():
                            translated_segments[block_id] = translated_text.strip()
                            repaired_ids.add(block_id)
                            round_repaired += 1
            repair_requests += len(repair_batches)
            # Avoid repeatedly charging for a provider that made no progress.
            if round_repaired == 0:
                break

        if requested_ids:
            report_data["partial_translation_repair"] = {
                "requests": repair_requests,
                "segments_requested": len(requested_ids),
                "segments_recovered": len(repaired_ids),
                "segments_missing": len(all_missing_ids),
                "segments_remaining": len(all_missing_ids - translated_segments.keys()),
                "segments_deferred": len(all_missing_ids - requested_ids),
            }
        for batch_number, block_ids, failure in batch_failures:
            if all(block_id in translated_segments for block_id in block_ids):
                report_data["warnings"].append(
                    f"Translation batch {batch_number} initially failed ({failure}); smaller retries recovered all affected text."
                )
            else:
                report_data["warnings"].append(
                    f"Translation batch {batch_number} failed ({failure}); untranslated source text was preserved."
                )
        if batch_failures:
            report_data["failed_batches"] = [
                {"batch": batch_number, "block_ids": block_ids, "reason": reason}
                for batch_number, block_ids, reason in batch_failures
            ]
            report_data["fallback_used"] = True
        translated = {
            index: "".join(separator + translated_segments[segment_id] for segment_id, separator in ids)
            for index, ids in enumerate(block_segments)
            if ids and all(segment_id in translated_segments for segment_id, _ in ids)
        }

        # Copy the actual page contents so that text successfully translated can
        # be removed from the searchable layer rather than hidden under a box.
        out_doc.insert_pdf(doc, links=True, annots=True)

        placed: list[tuple[int, fitz.Rect, str, int, int]] = []
        placed_block_ids: set[int] = set()
        placed_source_chars = 0
        changed_source_chars = 0.0
        for index, translation in translated.items():
            number, bounds, source_text = blocks[index]
            bounds &= out_doc[number].rect
            if bounds.is_empty:
                continue
            rotation = block_rotations[index]
            vertical = rotation in (90, 270)
            overlay_width, overlay_height = (
                (bounds.height, bounds.width) if vertical else (bounds.width, bounds.height)
            )
            overlay = overlays.new_page(width=overlay_width, height=overlay_height)
            # MuPDF's HTML renderer uses shaped Unicode fonts, including Devanagari.
            font_size = 5.5 if vertical else 10
            scale_low = 0.7 if vertical else 0.45
            spare, _ = overlay.insert_htmlbox(
                overlay.rect,
                escape(translation).replace("\n", "<br>"),
                css=(f"body {{ margin: 0; font: {font_size}pt 'Noto Sans Devanagari', 'Nirmala UI', "
                     "'Mangal', 'DejaVu Sans', sans-serif; color: #19202a; }"),
                scale_low=scale_low,
            )
            if spare < 0:
                continue
            placed.append((number, bounds, translation, overlay.number, rotation))
            placed_block_ids.add(index)
            placed_source_chars += len(blocks[index][2])
            changed_source_chars += len(source_text) * _translation_change_fraction(source_text, translation)
            report_data["blocks_rotated"] += int(bool(rotation))

        # Redact only blocks for which a replacement fitted. Keep images and
        # vector artwork, and leave failed/untranslated blocks intact.
        for number, bounds, _, _, _ in placed:
            out_doc[number].add_redact_annot(bounds, fill=False, cross_out=False)
        for number in {number for number, _, _, _, _ in placed}:
            out_doc[number].apply_redactions(images=0, graphics=0)

        # MuPDF currently shapes Devanagari visually but can write a broken
        # ToUnicode map for its generated PDF text. Rasterize only translated
        # text boxes, then add an invisible standards-based Unicode text layer
        # below with ReportLab's embedded TrueType font.
        for number, bounds, _, overlay_number, rotation in placed:
            page = out_doc[number]
            text_page = overlays[overlay_number]
            rendered = text_page.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=True)
            page.insert_image(bounds, stream=rendered.tobytes("png"), overlay=True, rotate=rotation)
            report_data["blocks_translated"] += 1

        report_data["blocks_preserved"] = report_data["blocks_seen"] - report_data["blocks_translated"]
        total_source_chars = sum(len(source_text) for _, _, source_text in blocks)
        translated_source_chars = placed_source_chars
        report_data["source_characters_seen"] = total_source_chars
        report_data["source_characters_translated"] = translated_source_chars
        report_data["translated_fraction"] = (
            translated_source_chars / total_source_chars if total_source_chars else 0.0
        )
        report_data["text_segments_seen"] = len(segments)
        report_data["text_segments_translated"] = sum(
            len(block_segments[index]) for index in placed_block_ids
        )
        report_data["translated_segment_fraction"] = (
            report_data["text_segments_translated"] / len(segments) if segments else 0.0
        )
        report_data["translated_block_fraction"] = (
            report_data["blocks_translated"] / report_data["blocks_seen"]
            if report_data["blocks_seen"] else 0.0
        )
        report_data["minimum_acceptable_fraction"] = 0.5
        block_fraction = report_data["translated_block_fraction"]
        segment_fraction = report_data["translated_segment_fraction"]
        character_fraction = report_data["translated_fraction"]
        if not report_data["blocks_translated"]:
            report_data["translation_status"] = "failed"
            report_data["fallback_used"] = True
            report_data["warnings"].append("No text blocks were translated.")
            if batch_failures:
                failure_labels = list(dict.fromkeys(
                    _safe_provider_failure_label(RuntimeError(reason))
                    for _, _, reason in batch_failures
                ))
                report_data["failure_class"] = failure_labels
                failure_summary = "; ".join(failure_labels[:3])
                raise RuntimeError(
                    f"Translation failed for all text batches ({failure_summary}). "
                    "No text was translated; no translated PDF was produced."
                )
            raise RuntimeError(
                "No text was translated. The translation service did not produce a translated PDF; please retry later."
            )
        if (block_fraction < report_data["minimum_acceptable_fraction"]
                or character_fraction < report_data["minimum_acceptable_fraction"]):
            report_data["translation_status"] = "failed"
            block_percent = round(block_fraction * 100)
            segment_percent = round(segment_fraction * 100)
            character_percent = round(character_fraction * 100)
            report_data["warnings"].append(
                f"Only {block_percent}% of text blocks, {segment_percent}% of text segments, and "
                f"{character_percent}% of source characters were translated; block and character "
                "coverage must each reach at least 50%."
            )
            raise RuntimeError(
                f"Only {block_percent}% of text blocks, {segment_percent}% of text segments, and "
                f"{character_percent}% of source characters were translated (minimum 50% for "
                "blocks and characters). No translated PDF was produced."
            )
        report_data["translation_change_fraction"] = (
            changed_source_chars / total_source_chars if total_source_chars else 0.0
        )
        report_data["minimum_change_fraction"] = 0.1
        if report_data["blocks_translated"] and report_data["translation_change_fraction"] < report_data["minimum_change_fraction"]:
            report_data["translation_status"] = "failed"
            change_percent = report_data["translation_change_fraction"]
            report_data["warnings"].append(
                f"Only {change_percent:.0%} of source text changed in the translation; "
                "at least 10% is required to provide a translated PDF."
            )
            raise RuntimeError(
                f"Only {change_percent:.0%} of source text changed during translation "
                "(minimum 10%). No translated PDF was produced."
            )
        report_data["translation_status"] = (
            "translated" if report_data["blocks_preserved"] == 0 else "partial"
        )
        if report_data["blocks_preserved"]:
            report_data["fallback_used"] = True
            report_data["warnings"].append(
                "Some source blocks were preserved because the translation was missing or could not fit."
            )
        if not report_data["blocks_translated"]:
            report_data["fallback_used"] = True
            report_data["warnings"].append("No text blocks were translated.")
            if batch_failures:
                failure_labels = list(dict.fromkeys(
                    _safe_provider_failure_label(RuntimeError(reason))
                    for _, _, reason in batch_failures
                ))
                report_data["failure_class"] = failure_labels
                failure_summary = "; ".join(failure_labels[:3])
                raise RuntimeError(
                    f"Translation failed for all text batches ({failure_summary}). "
                    "No text was translated; no translated PDF was produced."
                )
            raise RuntimeError("No text was translated. The translation service did not produce a translated PDF; please retry later.")
        rendered_pdf = output_path.with_name(f"{output_path.stem}_rendered.pdf")
        out_doc.save(str(rendered_pdf), garbage=4, deflate=True)

    # Use a TrueType Unicode cmap for text extraction/search/accessibility. The
    # visible translation above remains correctly shaped by MuPDF's HTML engine.
    repo_font = Path(__file__).resolve().parent / "deploy" / "fonts" / "FreeSans.ttf"
    font_candidates = [
        (Path(r"C:\Windows\Fonts\Nirmala.ttc"), 0),
        (repo_font, 0),
        (Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"), 0),
        (Path("/usr/share/fonts/truetype/freefont/FreeSerif.ttf"), 0),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), 0),
    ]
    font_path, font_index = next(((path, index) for path, index in font_candidates if path.is_file()), (None, 0))
    if font_path is None:
        rendered_pdf.unlink(missing_ok=True)
        raise RuntimeError("Hindi translation requires an embeddable Unicode font for its searchable text layer.")
    font_name = "PaperplaneTranslationUnicode"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font_name, str(font_path), subfontIndex=font_index))
    base = PdfReader(str(rendered_pdf))
    hidden_stream = io.BytesIO()
    hidden = reportlab_canvas.Canvas(hidden_stream, pagesize=(float(base.pages[0].mediabox.width), float(base.pages[0].mediabox.height)))
    by_page: dict[int, list[tuple[fitz.Rect, str]]] = {}
    for number, bounds, translation, _, _ in placed:
        by_page.setdefault(number, []).append((bounds, translation))
    for page_number, base_page in enumerate(base.pages):
        width, height = float(base_page.mediabox.width), float(base_page.mediabox.height)
        hidden.setPageSize((width, height))
        for bounds, translation in by_page.get(page_number, []):
            text_object = hidden.beginText()
            text_object.setTextOrigin(max(0, bounds.x0 + 1), max(1, height - bounds.y0 - 10))
            text_object.setFont(font_name, 8)
            text_object.setTextRenderMode(3)
            max_width = max(20, bounds.width - 2)
            for paragraph in translation.splitlines() or [translation]:
                line = ""
                for word in paragraph.split():
                    candidate = f"{line} {word}".strip()
                    if line and pdfmetrics.stringWidth(candidate, font_name, 8) > max_width:
                        text_object.textLine(line)
                        line = word
                    else:
                        line = candidate
                if line:
                    text_object.textLine(line)
            hidden.drawText(text_object)
        hidden.showPage()
    hidden.save()
    hidden_stream.seek(0)
    hidden_reader = PdfReader(hidden_stream)
    writer = PdfWriter()
    try:
        for index, base_page in enumerate(base.pages):
            writer.add_page(base_page)
            writer.pages[-1].merge_page(hidden_reader.pages[index])
        with output_path.open("wb") as output_file:
            writer.write(output_file)
    finally:
        rendered_pdf.unlink(missing_ok=True)
    return output_path
