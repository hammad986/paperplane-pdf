from __future__ import annotations

import io
from html import escape
import json
import math
import os
import re
import time
import datetime as dt
import urllib.request
import urllib.error
from collections import Counter
import logging
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger("paperplane")

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
                return (
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
            return (
                f"Correction: {correction} This is a general geography correction; "
                "it is not a fact inferred from the uploaded PDF."
            )

    author = metadata.get("author", "").strip() or document_author
    if re.search(r"\b(author|authored|wrote|written by)\b", question, re.IGNORECASE):
        claimed_author = re.search(
            r"\b(?:author(?:ed)?(?:\s+is|\s+was|\s+by)?|written\s+by|wrote)\s+[\"“]?([A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){0,3})",
            question,
        )
        if claimed_author and author and claimed_author.group(1).casefold() != author.casefold():
            return (
                f"Correction: the PDF identifies {author} as the author, not "
                f"{claimed_author.group(1)}. This is based on the document text or embedded metadata."
            )
        if claimed_author and not author:
            return "I can't verify that authorship claim: the PDF's metadata and opening text do not identify an author."

    creation_year = _metadata_year(metadata.get("creationDate", ""))
    if creation_year and re.search(r"\b(date|year|published|publication|created|written)\b", question, re.IGNORECASE):
        claimed_year = re.search(r"\b(?:19|20)\d{2}\b", question)
        if claimed_year and claimed_year.group(0) != creation_year:
            return (
                f"Correction: the PDF creation metadata records {creation_year}, not {claimed_year.group(0)}. "
                "A file creation date does not establish the document's original publication date."
            )

    return None


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
        label = "Page" if len(kept) == 1 else "Pages"
        return f"[{label} {', '.join(map(str, kept))}]"

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


def get_ai_configuration_health() -> dict[str, str | bool]:
    """Return a startup/admin-safe configuration check without making a request."""
    credentials = _runtime_ai_config()
    provider = str(credentials.get("provider") or "unavailable").lower()
    if credentials.get("configuration_error"):
        return {
            "status": "configuration_error",
            "provider": provider,
            "configured": False,
            "message": "The saved AI configuration could not be loaded. Check the server encryption configuration.",
        }
    configured = bool(credentials.get("api_key") and credentials.get("model"))
    if not configured:
        return {
            "status": "configuration_missing",
            "provider": provider,
            "configured": False,
            "message": "AI provider credentials or model are not configured; AI document tools are unavailable.",
        }
    return {
        "status": "configured",
        "provider": provider,
        "configured": True,
        "message": "AI provider configuration is present. Run Test Connection to check upstream reachability.",
    }


def _provider_request(system_prompt: str, user_prompt: str, credentials: dict[str, str], timeout_seconds: float | None = None) -> str:
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

    timeout = max(5, min(120, float(timeout_seconds or BLUESMINDS_TIMEOUT_SECONDS)))
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
            "temperature": 0.2,
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
            "temperature": 0.2,
        }
    elif provider == "gemini":
        endpoint = f"{base_url}/models/{urllib.parse.quote(model, safe='')}:generateContent" if base_url.endswith("/v1beta") else f"{base_url}/v1beta/models/{urllib.parse.quote(model, safe='')}:generateContent"
        headers["x-goog-api-key"] = api_key
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": BLUESMINDS_MAX_OUTPUT_TOKENS or 4096},
        }
    else:
        raise ValueError("Unsupported AI provider.")

    body = json.dumps(payload).encode("utf-8")
    data = None
    provider_host = urllib.parse.urlsplit(endpoint).hostname
    for attempt in range(2):
        request = urllib.request.Request(endpoint, data=body, headers=headers)
        try:
            started = time.monotonic()
            with _open_ai_request(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                logger.debug("AI provider host=%s attempt=%d timeout=%.1fs HTTP=%s elapsed=%.1fs",
                             provider_host, attempt + 1, timeout, getattr(response, "status", None),
                             time.monotonic() - started)
            break
        except urllib.error.HTTPError as error:
            logger.warning("AI provider host=%s attempt=%d timeout=%.1fs HTTP=%s",
                           provider_host, attempt + 1, timeout, error.code)
            if attempt == 0 and error.code in (408, 429, 500, 502, 503, 504):
                time.sleep(0.4)
                continue
            raise RuntimeError(f"AI service returned HTTP {error.code}. Please try again.") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            logger.warning("AI provider host=%s attempt=%d timeout=%.1fs failure=%s",
                           provider_host, attempt + 1, timeout, type(error).__name__)
            if attempt == 0:
                time.sleep(0.4)
                continue
            raise RuntimeError("AI service could not be reached or timed out. Please try again.") from error
    if not isinstance(data, dict):
        raise RuntimeError("AI service returned an invalid response. Please try again.")

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
        raise RuntimeError("AI service returned an empty response. Please try again.")
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
        answer = _provider_request("Reply with the word connected.", "ping", credentials, timeout_seconds=12)
        return {
            "status": "inference_succeeded",
            "http_status": 200,
            "message": "AI connected successfully.",
            "fallback_active": False,
        }
    except RuntimeError as error:
        match = re.search(r"HTTP (\d{3})", str(error))
        status_code = int(match.group(1)) if match else 502
        return {
            "status": "connection_error",
            "http_status": status_code,
            "message": str(error),
            "advice": str(error),
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
) -> str:
    """Dispatch inference using the selected provider's native API contract."""
    return _call_selected_provider(system_prompt, user_prompt, model=model, timeout_seconds=timeout_seconds)


def _call_selected_provider(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    timeout_seconds: float | None = None,
) -> str:
    if AI_KILL_SWITCH:
        return _offline_rag_fallback(system_prompt, user_prompt)
    credentials = _runtime_ai_config()
    if credentials.get("configuration_error"):
        raise RuntimeError(credentials["configuration_error"])
    if not credentials.get("api_key"):
        raise ValueError("AI provider is not configured")
    if model:
        credentials = dict(credentials)
        credentials["model"] = model
    return _provider_request(system_prompt, user_prompt, credentials, timeout_seconds=timeout_seconds)


def _offline_rag_fallback(system_prompt: str, user_prompt: str) -> str:
    """Intelligent local deterministic answer builder (Offline RAG mode)."""
    if "Executive Summary" in system_prompt or "summariz" in system_prompt.lower():
        doc_text = user_prompt.replace("DOCUMENT CONTENT:\n\n", "")
        pages = doc_text.split("--- Page ")
        summary_points = []
        for p in pages:
            if not p.strip():
                continue
            lines = [l.strip() for l in p.splitlines() if l.strip() and not l.startswith("---")]
            for l in lines:
                if len(l) >= 10 and not any(l.startswith(prefix) for prefix in ("---", "Page")) and len(summary_points) < 8:
                    summary_points.append(l)

        pts = "\n".join(f"- {pt}" for pt in summary_points) if summary_points else "- General document overview available."
        return (
            "### Executive Summary (Offline Analysis)\n\n"
            "This document was indexed and analyzed using Paperplane's deterministic local extraction engine.\n\n"
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

        if re.search(r"\b(summar(?:y|ize|ise)|overview|key points|important information)\b", question, re.IGNORECASE):
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
                page_notes.append(f"Page {page_number}: {page_text} [Page {page_number}]")
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



# ----------------------------------------------------------------------
# PUBLIC AI CAPABILITIES
# ----------------------------------------------------------------------

def chat_with_pdf(pdf_path: Path, question: str) -> dict:
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
    broad_summary = bool(re.search(r"\b(summar(?:y|ize|ise)|overview|key points|important information)\b", question, re.IGNORECASE))
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
        return {
            "answer": "No relevant information found in the document for your question. The active document does not contain matching keywords or passages.",
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
        "the provided document excerpts. Always cite specific page numbers like [Page X] when referencing facts."
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


def _bounded_document_timeout(deadline: float, call_timeout: float) -> float:
    # Account for both attempts and backoff in the transport.
    remaining = deadline - time.monotonic()
    if remaining < 12:
        raise RuntimeError("The AI provider timed out before the document was complete. Please retry later.")
    return min(call_timeout, (remaining - 1) / 2)


def summarize_pdf(pdf_path: Path, max_pages: int | None = None) -> str:
    """Summarizes document into executive overview and bulleted key takeaways."""
    deadline = time.monotonic() + DOCUMENT_AI_BUDGET_SECONDS
    with fitz.open(str(pdf_path)) as doc:
        page_limit = min(doc.page_count, max_pages) if max_pages and max_pages > 0 else doc.page_count
        if page_limit > SUMMARY_PAGE_LIMIT:
            raise ValueError(f"Executive Brief accepts up to {SUMMARY_PAGE_LIMIT} pages. Split the PDF and try again.")
        page_budget = max(250, min(1500, 22000 // max(1, page_limit)))
        page_texts: list[tuple[int, str]] = []
        for number in range(page_limit):
            page_text = doc[number].get_text("text").strip()
            if page_text:
                page_texts.append((number + 1, page_text[:page_budget]))

    if not page_texts:
        return "The document contains no extractable text."

    system_prompt = (
        "You are an executive document synthesizer. Provide an insightful Executive Summary followed by "
        "bullet points of key details, decisions, numbers, and deadlines. Ground every document fact in the "
        "provided text and append a page citation in the exact form [Page N] or [Pages N-M]. Do not invent citations."
    )
    if len(page_texts) <= 24:
        full_text = "\n\n".join(f"--- Page {number} ---\n{text}" for number, text in page_texts)
        summary = call_llm(system_prompt, f"DOCUMENT CONTENT:\n\n{full_text}", timeout_seconds=_bounded_document_timeout(deadline, SUMMARY_CALL_TIMEOUT_SECONDS))
    else:
        # Long documents are summarized in bounded, page-labelled sections so
        # one provider request does not have to fit the whole source at once.
        chunk_notes: list[str] = []
        chunk_size = 24
        for start in range(0, len(page_texts), chunk_size):
            chunk = page_texts[start:start + chunk_size]
            chunk_text = "\n\n".join(f"--- Page {number} ---\n{text}" for number, text in chunk)
            first_page, last_page = chunk[0][0], chunk[-1][0]
            chunk_prompt = (
                f"DOCUMENT SECTION, pages {first_page}-{last_page}:\n\n{chunk_text}\n\n"
                "Return concise key facts, decisions, dates, amounts, and themes from this section. "
                "Ground each item in the supplied text and preserve its [Page N] citation. Do not invent facts."
            )
            timeout = _bounded_document_timeout(deadline, SUMMARY_CALL_TIMEOUT_SECONDS)
            note = call_llm(system_prompt, chunk_prompt, timeout_seconds=timeout).strip()
            if not note:
                raise RuntimeError(f"AI service returned an empty summary for pages {first_page}-{last_page}.")
            chunk_notes.append(note)
        final_prompt = (
            "Synthesize these page-grounded section notes into one concise executive summary followed by "
            "the most useful key takeaways. Preserve source citations from the notes exactly and do not "
            "introduce facts that the notes do not support.\n\n" + "\n\n".join(chunk_notes)
        )
        timeout = _bounded_document_timeout(deadline, SUMMARY_CALL_TIMEOUT_SECONDS)
        summary = call_llm(system_prompt, final_prompt, timeout_seconds=timeout)

    summary = _guard_ai_output(summary)
    eligible_pages = {page_number for page_number, _ in page_texts}
    return align_answer_citations(summary, eligible_pages)[0]


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


TRANSLATION_CALL_TIMEOUT_SECONDS = 30.0
TRANSLATION_MAX_BLOCKS = 120
TRANSLATION_BATCH_SIZE = 8


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
            block_id = item.get("id")
            text = item.get("text", item.get("translation"))
            if block_id in expected_ids and isinstance(text, str) and text.strip():
                output[int(block_id)] = text.strip()
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
        )
    except Exception as error:
        # call_bluesminds performs one bounded retry with backoff for transient
        # upstream failures. Preserve only the safe failure class/status here.
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
        "fallback_used": False,
        "warnings": [],
    })
    with fitz.open(str(pdf_path)) as doc, fitz.open() as out_doc, fitz.open() as overlays:
        report_data["pages_seen"] = doc.page_count
        blocks: list[tuple[int, fitz.Rect, str]] = []
        for page in doc:
            for block in page.get_text("blocks"):
                if len(block) < 7 or block[6] != 0 or len(block[4].strip()) < 2:
                    continue
                report_data["blocks_seen"] += 1
                # Preserve the full source of any block we cannot safely fit in a request.
                if len(block[4].strip()) <= 1600 and len(blocks) < TRANSLATION_MAX_BLOCKS:
                    blocks.append((page.number, fitz.Rect(block[:4]), block[4].strip()))

        translated: dict[int, str] = {}
        for start in range(0, len(blocks), TRANSLATION_BATCH_SIZE):
            batch = [
                (index, blocks[index][2])
                for index in range(start, min(start + TRANSLATION_BATCH_SIZE, len(blocks)))
            ]
            try:
                translated.update(_translate_text_batch(batch, target_language, deadline=deadline))
            except RuntimeError as error:
                report_data["fallback_used"] = True
                report_data["warnings"].append(str(error))
                raise

        for source_page in doc:
            page = out_doc.new_page(width=source_page.rect.width, height=source_page.rect.height)
            if source_page.get_contents():
                page.show_pdf_page(page.rect, doc, source_page.number)

        placed = []
        for index, translation in translated.items():
            number, bounds, _ = blocks[index]
            bounds &= out_doc[number].rect
            if bounds.is_empty:
                continue
            overlay = overlays.new_page(width=bounds.width, height=bounds.height)
            # MuPDF's HTML renderer uses shaped Unicode fonts, including Devanagari.
            spare, _ = overlay.insert_htmlbox(
                overlay.rect,
                escape(translation).replace("\n", "<br>"),
                css="body { margin: 0; font: 10pt sans-serif; color: #19202a; }",
                scale_low=0.45,
            )
            if spare < 0:
                continue
            placed.append((number, bounds, overlay.number))

        # Complete the source document before grafting pages out of it.
        for number, bounds, overlay_number in placed:
            page = out_doc[number]
            page.draw_rect(bounds, color=None, fill=(1, 1, 1))
            page.show_pdf_page(bounds, overlays, overlay_number, keep_proportion=False)
            report_data["blocks_translated"] += 1

        report_data["blocks_preserved"] = report_data["blocks_seen"] - report_data["blocks_translated"]
        if report_data["blocks_preserved"]:
            report_data["fallback_used"] = True
            report_data["warnings"].append(
                "Some source blocks were preserved because the translation was missing or could not fit."
            )
        if not report_data["blocks_translated"]:
            report_data["fallback_used"] = True
            report_data["warnings"].append("No text blocks were translated.")
            raise RuntimeError("No text was translated. The translation service did not produce a translated PDF; please retry later.")
        out_doc.save(str(output_path), garbage=4, deflate=True)
    return output_path
