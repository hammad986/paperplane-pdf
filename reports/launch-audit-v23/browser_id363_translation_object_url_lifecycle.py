from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import tempfile
import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
BASE_URL = os.environ.get("PAPERPLANE_BROWSER_BASE_URL", "http://127.0.0.1:8501").rstrip("/")
errors = []
with fitz.open() as source_pdf:
    source_pdf.new_page().insert_text((72, 72), "Translation object URL content marker v23")
    source_pdf_bytes = source_pdf.tobytes()
source_pdf_b64 = base64.b64encode(source_pdf_bytes).decode("ascii")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.on("pageerror", lambda error: errors.append(str(error)))
    response = page.goto(BASE_URL + "/", wait_until="networkidle")
    if not response or response.status != 200:
        raise RuntimeError("Local Paperplane did not return HTTP 200")
    setup = page.evaluate("""encodedPdf => {
      if (typeof renderTranslationResult !== 'function' || typeof clearResultPanel !== 'function') {
        throw new Error('Translation result UI functions were not loaded');
      }
      window.__translationUrlAudit = {
        nativeCreate: URL.createObjectURL.bind(URL),
        nativeRevoke: URL.revokeObjectURL.bind(URL), created: [], revoked: []
      };
      const audit = window.__translationUrlAudit;
      URL.createObjectURL = blob => { const url = audit.nativeCreate(blob); audit.created.push(url); return url; };
      URL.revokeObjectURL = url => { audit.revoked.push(url); audit.nativeRevoke(url); };
      const bytes = Uint8Array.from(atob(encodedPdf), char => char.charCodeAt(0));
      const blob = new Blob([bytes], { type: 'application/pdf' });
      window.__translationBlob = blob;
      renderTranslationResult(blob, 'first.pdf', 'Spanish', 100, 100, 0, 'complete');
      const first = audit.created.at(-1);
      renderTranslationResult(blob, 'second.pdf', 'Spanish', 100, 100, 0, 'complete');
      const second = audit.created.at(-1);
      const firstReleasedOnReplace = audit.revoked.includes(first);
      const secondLinkMatches = document.querySelector('#result-content a.btn-download')?.href === second;
      return { firstReleasedOnReplace, secondLinkMatches };
    }""", source_pdf_b64)
    with page.expect_download(timeout=10000) as download_event:
        page.evaluate("document.querySelector('#result-content a.btn-download').click()")
    with tempfile.TemporaryDirectory(prefix="paperplane-id363-download-") as temporary:
        download_path = Path(temporary) / download_event.value.suggested_filename
        download_event.value.save_as(download_path)
        with fitz.open(download_path) as downloaded_pdf:
            downloaded_content = {
                "valid_pdf": True,
                "pages": downloaded_pdf.page_count,
                "marker_present": "Translation object URL content marker v23" in downloaded_pdf[0].get_text(),
            }
    result = page.evaluate("""() => {
      const audit = window.__translationUrlAudit;
      const second = audit.created[1];
      showRichAiResult('Summary ready', 'synthetic', '<p>Next result</p>');
      const secondReleasedOnOtherResult = audit.revoked.includes(second);
      renderTranslationResult(window.__translationBlob, 'third.pdf', 'Spanish', 100, 100, 0, 'complete');
      const third = audit.created.at(-1);
      clearResultPanel();
      const thirdReleasedOnClear = audit.revoked.includes(third);
      const output = { createdCount: audit.created.length, revokedCount: audit.revoked.length,
        secondReleasedOnOtherResult, thirdReleasedOnClear };
      URL.createObjectURL = audit.nativeCreate;
      URL.revokeObjectURL = audit.nativeRevoke;
      delete window.__translationUrlAudit;
      delete window.__translationBlob;
      return output;
    }""")
    result.update(setup)
    errors.extend(page.evaluate("window.__browserErrors || []"))
    browser.close()

report = {
    "url": BASE_URL + "/",
    "http_status": response.status,
    "result": result,
    "download_content": downloaded_content,
    "page_errors": errors,
    "verified": response.status == 200 and result == {
        "createdCount": 3,
        "revokedCount": 3,
        "firstReleasedOnReplace": True,
        "secondLinkMatches": True,
        "secondReleasedOnOtherResult": True,
        "thirdReleasedOnClear": True,
    } and downloaded_content == {"valid_pdf": True, "pages": 1, "marker_present": True} and not errors,
}
output_name = "browser-id363-translation-object-url-lifecycle-docker-v135.json" if "18501" in BASE_URL else "browser-id363-translation-object-url-lifecycle.json"
(ROOT / output_name).write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
if not report["verified"]:
    raise SystemExit(1)
