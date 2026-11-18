"""Two low-impact public-site upload/download checks using a public 5-page PDF."""
from __future__ import annotations

import fitz
import json
from pathlib import Path
import re
from zipfile import ZipFile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://paperplane.qd.je"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "totpdf-sample-5-pages.pdf"


def pdf_text(path: Path) -> tuple[int, list[str]]:
    with fitz.open(path) as document:
        return document.page_count, [page.get_text().strip() for page in document]


def main() -> None:
    output = Path(__file__).resolve().parent
    errors: list[str] = []
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1366, "height": 900})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/merge-pdf", wait_until="commit", timeout=30000)
        page.locator("#tool-title").wait_for(state="visible", timeout=30000)
        local_mode = page.locator("#client-privacy-toggle").is_checked()
        if local_mode:
            page.locator("#client-privacy-toggle").evaluate("el => el.click()")
        assert not page.locator("#client-privacy-toggle").is_checked(), "Expected server processing in isolated browser"
        live_merge_multiple = page.locator("#file-input").get_attribute("multiple") is not None
        page.locator("#file-input").set_input_files(str(FIXTURE))
        page.locator("#run-button").click(timeout=10000)
        page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=60000)
        with page.expect_download(timeout=30000) as event:
            page.locator("#result-download-link").click()
        merge_path = output / "live-merge-5-pages.pdf"
        event.value.save_as(merge_path)
        merge_count, merge_texts = pdf_text(merge_path)
        assert merge_count == 5, merge_count
        assert all(f"page {number} of 5" in text.lower() for number, text in enumerate(merge_texts, 1)), merge_texts
        results.append({"operation": "merge", "source_pages": 5, "inputs": 1, "output_pages": merge_count,
                        "download_bytes": merge_path.stat().st_size, "content_checked": True,
                        "live_merge_file_picker_supports_multiple": live_merge_multiple,
                        "http_result": "browser completed server-backed job"})

        page.goto(BASE + "/split-pdf", wait_until="commit", timeout=30000)
        page.locator("#tool-title").wait_for(state="visible", timeout=15000)
        if page.locator("#client-privacy-toggle").is_checked():
            page.locator("#client-privacy-toggle").evaluate("el => el.click()")
        page.locator("#file-input").set_input_files(str(FIXTURE))
        page.locator("#split_mode").wait_for(state="visible", timeout=15000)
        page.locator("#split_mode").select_option("all_pages")
        page.locator("#run-button").click(timeout=10000)
        page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=60000)
        with page.expect_download(timeout=30000) as event:
            page.locator("#result-download-link").click()
        split_path = output / "live-split-5-pages.zip"
        event.value.save_as(split_path)
        with ZipFile(split_path) as archive:
            names = archive.namelist()
            assert len(names) == 5, names
            split_pages = []
            for name in names:
                with fitz.open(stream=archive.read(name), filetype="pdf") as document:
                    assert document.page_count == 1, (name, document.page_count)
                    text = document[0].get_text().strip()
                    match = re.search(r"page\s+(\d+)\s+of\s+5", text, re.I)
                    assert match, {"name": name, "text": text}
                    split_pages.append(int(match.group(1)))
        assert split_pages == [1, 2, 3, 4, 5], split_pages
        results.append({"operation": "split-all-pages", "source_pages": 5, "output_files": len(names),
                        "output_page_order": split_pages, "download_bytes": split_path.stat().st_size,
                        "content_checked": True, "http_result": "browser completed server-backed job"})

        capability = context.request.get(BASE + "/api/ai/capabilities", timeout=20000)
        capability_payload = capability.json() if capability.ok else {"http_status": capability.status}
        provider_checks = {"capabilities_status": capability.status,
                           "executive_brief_available": capability_payload.get("executive_brief_available"),
                           "summary": None, "translation": None}
        if capability_payload.get("executive_brief_available") is True:
            source_bytes = FIXTURE.read_bytes()
            summary_response = context.request.post(
                BASE + "/api/ai/summarize",
                multipart={"file": {"name": FIXTURE.name, "mimeType": "application/pdf", "buffer": source_bytes}},
                timeout=120000,
            )
            summary_payload = summary_response.json() if summary_response.headers.get("content-type", "").startswith("application/json") else {}
            summary_text = str(summary_payload.get("summary", ""))
            provider_checks["summary"] = {"http_status": summary_response.status,
                "mode": summary_payload.get("summary_mode"), "nonempty": bool(summary_text.strip()),
                "citations": summary_payload.get("citations", []),
                "provider_synthesis_proven": summary_payload.get("summary_mode") == "provider_synthesized"}

            translate_response = context.request.post(
                BASE + "/api/ai/translate",
                multipart={"target_language": "es",
                           "file": {"name": FIXTURE.name, "mimeType": "application/pdf", "buffer": source_bytes}},
                timeout=180000,
            )
            translation_result = {"http_status": translate_response.status,
                                  "content_type": translate_response.headers.get("content-type", "")}
            if translate_response.ok and "pdf" in translation_result["content_type"].lower():
                translation_path = output / "live-translation-es-5-pages.pdf"
                translation_path.write_bytes(translate_response.body())
                pages, translated_texts = pdf_text(translation_path)
                translation_result.update({"pages": pages, "download_bytes": translation_path.stat().st_size,
                    "source_phrase_absent": all("This page exists only to test a tool" not in text for text in translated_texts),
                    "content_checked": pages == 5})
            else:
                try:
                    translation_result["error"] = translate_response.json().get("detail", "")
                except Exception:
                    translation_result["error"] = "Non-JSON provider response"
            provider_checks["translation"] = translation_result
        results.append({"operation": "provider-backed-summary-and-translation", **provider_checks})
        browser.close()
    report = {"site": BASE, "fixture": "TotPDF public 5-page sample", "checks": results,
              "page_errors": errors, "quota_cost": "two server job submissions from an isolated guest browser"}
    (output / "browser-live-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    assert not errors, errors


if __name__ == "__main__":
    main()
