"""Provider-backed AI smoke against the public site using a public 5-page PDF."""
from __future__ import annotations

import fitz
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://paperplane.qd.je"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "totpdf-sample-5-pages.pdf"


def main() -> None:
    output = Path(__file__).resolve().parent
    results = {"site": BASE, "fixture_pages": 5, "providers": {}}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(BASE + "/ai-translate", wait_until="domcontentloaded", timeout=30000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        capability = context.request.get(BASE + "/api/ai/capabilities", timeout=20000)
        payload = capability.json() if capability.ok else {}
        results["providers"]["capabilities"] = {"http_status": capability.status,
            "executive_brief_available": payload.get("executive_brief_available"),
            "reason": payload.get("reason")}
        if payload.get("executive_brief_available") is True:
            source_bytes = FIXTURE.read_bytes()
            summary = context.request.post(BASE + "/api/ai/summarize",
                multipart={"file": {"name": FIXTURE.name, "mimeType": "application/pdf", "buffer": source_bytes}},
                timeout=120000)
            summary_payload = summary.json() if summary.headers.get("content-type", "").startswith("application/json") else {}
            results["providers"]["summary"] = {"http_status": summary.status,
                "mode": summary_payload.get("summary_mode"),
                "nonempty": bool(str(summary_payload.get("summary", "")).strip()),
                "citations": summary_payload.get("citations", []),
                "provider_synthesis_proven": summary_payload.get("summary_mode") == "provider_synthesized"}

            translations = {}
            for language, rounds in (("es", 2), ("hi", 2)):
                language_results = []
                for attempt in range(1, rounds + 1):
                    translated = context.request.post(BASE + "/api/ai/translate",
                        multipart={"target_language": language,
                            "file": {"name": FIXTURE.name, "mimeType": "application/pdf", "buffer": source_bytes}},
                        timeout=180000)
                    item = {"attempt": attempt, "http_status": translated.status,
                            "content_type": translated.headers.get("content-type", "")}
                    if translated.ok and "pdf" in item["content_type"].lower():
                        translated_path = output / f"live-translation-{language}-attempt-{attempt}-5-pages.pdf"
                        translated_path.write_bytes(translated.body())
                        with fitz.open(translated_path) as document:
                            texts = [p.get_text() for p in document]
                        if language == "es":
                            translated_pages = [
                                "Muestra" in text and ("página" in text or "pagina" in text)
                                for text in texts
                            ]
                        else:
                            translated_pages = [
                                any("\u0900" <= char <= "\u097f" for char in text)
                                for text in texts
                            ]
                        item.update({"pages": len(texts), "download_bytes": translated_path.stat().st_size,
                            "translated_marker_pages": sum(translated_pages),
                            "translated_marker_pages_by_page": translated_pages,
                            "source_phrase_retained_pages": sum("This page exists only to test a tool" in text for text in texts),
                            "content_checked": len(texts) == 5})
                    else:
                        try:
                            item["error"] = translated.json().get("detail", "")
                        except Exception:
                            item["error"] = "Non-JSON provider response"
                    language_results.append(item)
                translations[language] = language_results
            results["providers"]["translations"] = translations
        results["browser_page_errors"] = errors
        browser.close()
    (output / "browser-live-ai.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
