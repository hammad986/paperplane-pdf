"""Prove Studio reload restores the most recently selected PDF, not its prior document."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json

import fitz
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8766"
results = []

def make_pdf(path: Path, markers: list[str]) -> None:
    with fitz.open() as document:
        for marker in markers:
            page = document.new_page()
            page.insert_text((72, 72), marker)
        document.save(path)

with TemporaryDirectory(prefix="paperplane-id269-") as temp:
    stale = Path(temp) / "test-protected_unlock.pdf"
    current = Path(temp) / "current-document.pdf"
    make_pdf(stale, ["STALE PREVIOUS DOCUMENT"])
    make_pdf(current, ["CURRENT DOCUMENT PAGE ONE", "CURRENT DOCUMENT PAGE TWO"])
    current_digest = hashlib.sha256(current.read_bytes()).hexdigest()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for round_no in (1, 2):
            context = browser.new_context(viewport={"width": 1366, "height": 900})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            response = page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
            assert response and response.status == 200
            page.locator("#studio-file-input").set_input_files(str(stale))
            page.wait_for_function("document.querySelector('#studio-page-count')?.textContent.trim() === '1'", timeout=30000)
            page.locator("#studio-file-input").set_input_files(str(current))
            page.wait_for_function("document.querySelector('#studio-page-count')?.textContent.trim() === '2'", timeout=30000)

            saved = page.evaluate("""async () => {
              const db = await new Promise((resolve, reject) => {
                const request = indexedDB.open('paperplane-local-work', 1);
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
              });
              const record = await new Promise((resolve, reject) => {
                const request = db.transaction('work', 'readonly').objectStore('work').get('guest:studio-pdf');
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
              });
              const digest = await crypto.subtle.digest('SHA-256', await record.blob.arrayBuffer());
              return {name:record.name, digest:[...new Uint8Array(digest)].map(byte=>byte.toString(16).padStart(2,'0')).join('')};
            }""")
            assert saved["name"] == current.name, saved
            assert saved["digest"] == current_digest, saved

            response = page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
            assert response and response.status == 200
            page.wait_for_function("document.querySelector('#studio-page-count')?.textContent.trim() === '2'", timeout=30000)
            restored = page.evaluate("""async () => {
              const db = await new Promise((resolve, reject) => {
                const request = indexedDB.open('paperplane-local-work', 1);
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
              });
              const record = await new Promise((resolve, reject) => {
                const request = db.transaction('work', 'readonly').objectStore('work').get('guest:studio-pdf');
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
              });
              const digest = await crypto.subtle.digest('SHA-256', await record.blob.arrayBuffer());
              return {name:record.name, digest:[...new Uint8Array(digest)].map(byte=>byte.toString(16).padStart(2,'0')).join('')};
            }""")
            assert restored["name"] == current.name, restored
            assert restored["digest"] == current_digest, restored
            assert not errors, errors
            results.append({"round":round_no, "previous_file":stale.name, "selected_current_file":current.name, "restored_file":restored["name"], "restored_page_count":2, "sha256_matches_current":True, "page_errors":errors})
            context.close()
        browser.close()

(OUT / "browser-id269-studio-latest-document-restore.json").write_text(json.dumps({"base":BASE,"rounds":results},indent=2),encoding="utf-8")
print(json.dumps({"rounds":len(results),"results":results},indent=2))
