"""Run selected v14 browser checks against an isolated, synthetic local server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

import fitz
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = r'''
import json, os, secrets
from pathlib import Path
import persistence, server, ai_engine, uvicorn
persistence.init_db()
tokens = {}
for tier in ("student_pro", "cyber_cafe"):
    email = tier + "-" + secrets.token_hex(5) + "@example.invalid"
    password = secrets.token_urlsafe(24)
    uid = persistence.create_user(email, password)
    persistence.set_user_tier(uid, tier)
    tokens[tier] = persistence.create_session(email, password)["token"]
tokens["admin"] = persistence.create_admin_session(server.PRIMARY_ADMIN_EMAIL)
Path(os.environ["V14_IDENTITIES"]).write_text(json.dumps(tokens))
server.translation_ai_available = lambda: True
ai_engine._current_bluesminds_api_key = lambda: "synthetic-key"
ai_engine._translate_text_batch = lambda blocks, language, deadline=None: {
    index: ("Hola mundo" if language == "es" else "भारत सरकार") for index, text in blocks
}
ai_engine.call_llm = lambda *args, **kwargs: "Grounded document summary. [Page 1]"
def synthetic_chat_stream(*args, **kwargs):
    yield "The text on page two reads Original English content page 2. [[Page 2]] [Page 2] [Page X] [Page 999]"
ai_engine.stream_bluesminds = synthetic_chat_stream
ai_engine._current_agentrouter_api_key = lambda: "synthetic-key"
ai_engine.call_agentrouter = lambda *args, **kwargs: json.dumps({
    "general_data": {"title": "Synthetic document", "document_date": "3.3.1", "detected_topics": ["3.3.1 Fragment", "Machine Learning"]},
    "warnings": [], "source_pages": [1], "contact": {"emails": [], "phones": []},
})
server.ENVIRONMENT = "production"
server.CASHFREE_ENV = "TEST"
server.CASHFREE_APP_ID = "TEST-synthetic"
server.CASHFREE_SECRET_KEY = "synthetic"
server.ALLOW_TEST_PAYMENTS = True
uvicorn.run(server.app, host="127.0.0.1", port=int(os.environ["PAPERPLANE_PORT"]), log_level="error")
'''


def main() -> None:
    evidence = []
    def record(message):
        evidence.append(message)
        print(message, flush=True)
    with tempfile.TemporaryDirectory(prefix="paperplane-v14-browser-") as tmp:
        directory = Path(tmp)
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        identities_path = directory / "identities.json"
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("PAPERPLANE_", "CASHFREE_", "OPENAI_", "GEMINI_", "BLUESMINDS_", "ADMIN_"))}
        env.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development",
                   PAPERPLANE_DATA_DIR=str(directory / "data"), PAPERPLANE_PORT=str(port),
                   PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(48), PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(32),
                   V14_IDENTITIES=str(identities_path))
        server = subprocess.Popen([sys.executable, "-c", BOOTSTRAP], cwd=ROOT, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError("Isolated server exited during startup")
                    time.sleep(.1)
            else:
                raise RuntimeError("Isolated server failed to start")
            tokens = json.loads(identities_path.read_text())
            paths = {}
            for pages in (3, 69):
                paths[pages] = directory / f"{pages}-page.pdf"
                with fitz.open() as pdf:
                    for index in range(pages):
                        sheet = pdf.new_page()
                        sheet.insert_text((72, 72), f"Original English content page {index + 1}")
                        if pages == 69:
                            sheet.insert_text((72, 147), f"Original English content extra A page {index + 1}")
                            sheet.insert_text((72, 222), f"Original English content extra B page {index + 1}")
                    pdf.save(paths[pages])
            large = directory / "synthetic-large.pdf"
            with fitz.open() as pdf:
                for index in range(759):
                    pdf.new_page().insert_text((72, 72), f"Large document page {index + 1}")
                pdf.embfile_add("synthetic.bin", os.urandom(60 * 1024 * 1024))
                pdf.save(large)
            ten = directory / "ten.pdf"
            with fitz.open() as pdf:
                for index in range(10):
                    pdf.new_page().insert_text((72, 72), f"Second document page {index + 1}")
                pdf.save(ten)
            photo = directory / "photo.png"
            Image.frombytes("RGB", (1200, 900), os.urandom(1200 * 900 * 3)).save(photo)
            broken = directory / "broken.pdf"
            broken.write_bytes(b"%PDF-1.7\ninvalid object with no trailer")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(accept_downloads=True)
                context.add_cookies([{"name": "paperplane_token", "value": tokens["cyber_cafe"], "url": base}])
                page = context.new_page()
                page.goto(base + "/", wait_until="domcontentloaded")
                page.keyboard.press("Control+k")
                page.locator("#command-input").fill("merge")
                page.locator(".command-item").first.wait_for(state="visible")
                assert page.locator(".command-item-left > span").count() == 0
                page.locator("#close-command-btn").click()
                record("ID 215: command palette results do not carry an API label")
                for pages in (3, 69):
                    for language, target in (("es", "Hola mundo"), ("hi", "भारत सरकार")):
                        page.goto(base + "/translate-pdf", wait_until="domcontentloaded")
                        page.locator("#file-input").set_input_files(str(paths[pages]))
                        page.locator("#target_language").select_option(label=f"{language} ({'Spanish' if language == 'es' else 'Hindi'})")
                        page.locator("#run-button").click()
                        link = page.get_by_role("link", name="Download translated PDF")
                        link.wait_for(state="visible", timeout=30000)
                        with page.expect_download() as event:
                            link.click()
                        output = directory / f"translated-{pages}-{language}.pdf"
                        event.value.save_as(output)
                        with fitz.open(output) as pdf:
                            assert pdf.page_count == pages
                            assert all(part.get_text().count(target) == (3 if pages == 69 else 1)
                                       and "Original English content" not in part.get_text() for part in pdf)
                        record(f"IDs 1/226: {pages} pages, {language}: translated download and text layer verified with controlled provider")
                page.goto(base + "/summarize-pdf", wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files(str(paths[69]))
                page.locator("#run-button").click()
                page.get_by_text("Grounded document summary.", exact=False).first.wait_for(timeout=30000)
                record("ID 2: 69-page summary rendered with controlled provider")
                page.goto(base + "/ai-intelligence", wait_until="domcontentloaded")
                page.locator("#ai-file-input").set_input_files(str(paths[69]))
                page.get_by_text("Loaded & Ready", exact=True).wait_for(state="visible", timeout=30000)
                page.wait_for_function("state.files.length === 1 && state.files[0].name === '69-page.pdf'", timeout=30000)
                page.locator("#chat-input").fill("This 100-page PDF was written by Albert Einstein, right?")
                with page.expect_response("**/api/ai/chat/stream", timeout=30000) as chat_response:
                    page.locator("#chat-send-btn").click()
                try:
                    page.get_by_text("uploaded PDF contains 69 pages, not 100", exact=False).first.wait_for(timeout=30000)
                except Exception:
                    print("Chat diagnostic:", page.locator("#chat-messages").inner_text(), flush=True)
                    print("Stream diagnostic:", chat_response.value.text()[:1500], flush=True)
                    raise
                assert "can't verify that authorship" in page.locator("#chat-messages").inner_text()
                record("ID 6: the browser answer corrects the page count and addresses the unsupported authorship claim")
                for repeat in range(3):
                    page.locator("#chat-input").fill("What does page 2 say?")
                    with page.expect_response("**/api/ai/chat/stream", timeout=30000):
                        page.locator("#chat-send-btn").click()
                    answer = page.locator("#chat-messages .ai-stream-text").last
                    try:
                        answer.get_by_text("Original English content page 2", exact=False).wait_for(timeout=30000)
                    except Exception:
                        print("Citation diagnostic:", page.locator("#chat-messages").inner_text(), flush=True)
                        raise
                    answer_text = answer.inner_text()
                    assert "[[Page" not in answer_text and "Page X" not in answer_text and "Page 999" not in answer_text
                    citations = page.locator("#chat-messages .chat-citation-tags").last
                    assert citations.locator("[data-ai-page]").count() == 1
                    assert citations.locator("[data-ai-page='2']").count() == 1
                record("IDs 5/12/99: three identical browser chat runs rendered one verified Page 2 chip without raw or unsupported citations")
                page.goto(base + "/remove-pages-pdf", wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files(str(paths[69]))
                page.locator("#pages").wait_for(state="visible", timeout=30000)
                page.locator("#pages").fill("2, 4")
                page.locator("#run-button").click()
                remove_link = page.locator("#result-download-link:not([hidden])")
                remove_link.wait_for(state="visible", timeout=30000)
                with page.expect_download(timeout=30000) as removed_event:
                    remove_link.click()
                removed_file = directory / "removed-pages.pdf"
                assert removed_event.value.suggested_filename == "removed-pages.pdf"
                removed_event.value.save_as(removed_file)
                with fitz.open(removed_file) as removed_pdf:
                    assert removed_pdf.page_count == 67
                    assert "Original English content page 1" in removed_pdf[0].get_text()
                    assert "Original English content page 3" in removed_pdf[1].get_text()
                record("IDs 8/196: browser removed pages 2 and 4 from 69 pages on first attempt, downloaded removed-pages.pdf with 67 ordered pages")
                page.goto(base + "/extract-pdf-data", wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files(str(paths[3]))
                with page.expect_response("**/api/ai/extract", timeout=30000) as extracted:
                    page.locator("#run-button").click()
                payload = extracted.value.json()["data"]
                assert payload["general_data"]["document_date"] is None
                assert "3.3.1" not in payload["csv_export"]
                page.locator("#extraction-results-modal").wait_for(state="visible", timeout=30000)
                assert "3.3.1" not in page.locator("#extraction-results-modal").inner_text()
                record("IDs 9/105: the browser metadata result rejects a provider's section-number date")
                job_requests = []
                page.on("request", lambda request: job_requests.append(request.url)
                        if request.method == "POST" and request.url.endswith("/api/jobs") else None)
                page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                page.locator("#client-privacy-toggle").evaluate("el => { if (!el.checked) el.click(); }")
                page.locator("#file-input").set_input_files([str(paths[3]), str(paths[3])])
                page.locator("#run-button").click()
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
                assert not job_requests
                page.goto(base + "/", wait_until="domcontentloaded", timeout=2000)
                record("ID 185: a completed local merge navigated home within two seconds")
                page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                page.locator("#client-privacy-toggle").evaluate("el => { if (el.checked) el.click(); }")
                usage_before = page.request.get(base + "/api/billing/status").json()["usage_today"]
                page.locator("#file-input").set_input_files([str(paths[3]), str(paths[3])])
                page.locator("#run-button").click()
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
                usage_after = page.request.get(base + "/api/billing/status").json()["usage_today"]
                assert len(job_requests) == 1 and usage_after == usage_before + 1
                page.goto(base + "/split-pdf", wait_until="domcontentloaded")
                assert not page.locator("#client-privacy-toggle").is_checked()
                record("IDs 186/211: server-mode merge created one job and the preference remained off on Split")
                usage_before = page.request.get(base + "/api/billing/status").json()["usage_today"]
                page.goto(base + "/ssc-photo-resizer", wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files(str(photo))
                page.locator("#run-button").click()
                result_link = page.locator("#result-download-link:not([hidden])")
                result_link.wait_for(state="visible", timeout=30000)
                with page.expect_download() as event:
                    result_link.click()
                resized = directory / "exam-photo.jpg"
                event.value.save_as(resized)
                with Image.open(resized) as image:
                    assert image.size == (350, 450)
                assert 20 * 1024 <= resized.stat().st_size <= 50 * 1024
                assert len(job_requests) == 1 and page.request.get(base + "/api/billing/status").json()["usage_today"] == usage_before
                record("ID 187: exam photo ran locally at 350 x 450 within 20 to 50 KiB without a job or quota use")
                page.goto(base + "/developers", wait_until="domcontentloaded")
                assert "ALL-IN-ONE PRO" in page.locator("body").inner_text()
                for tier, expected in (("student_pro", 403), ("cyber_cafe", 200)):
                    context.add_cookies([{"name": "paperplane_token", "value": tokens[tier], "url": base}])
                    result = page.evaluate("""async () => {
                      const r = await fetch('/api/developer/keys', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:'Browser test'})});
                      const data = await r.json(); return {status:r.status, name:data.name};
                    }""")
                    assert result["status"] == expected
                    if expected == 200:
                        assert result["name"] == "Browser test"
                record("ID 223: student denied, developer created a named key through browser")
                payment = page.evaluate("""async () => {
                  const status = await (await fetch('/api/billing/status')).json();
                  const checkout = await fetch('/api/billing/checkout-session', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tier:'student_pro'})});
                  const simulation = await fetch('/api/billing/simulate-pro', {method:'POST'});
                  return {configuredFieldPresent:Object.hasOwn(status, 'cashfree_configured'), environmentFieldPresent:Object.hasOwn(status, 'cashfree_environment'), checkout:checkout.status, simulation:simulation.status};
                }""")
                assert payment == {"configuredFieldPresent": False, "environmentFieldPresent": False, "checkout": 503, "simulation": 403}
                record("ID 98: production configuration rejects sandbox checkout and simulation through browser")
                page.goto(base + "/pricing", wait_until="domcontentloaded")
                page.locator("#pricing-page-content .pricing-tier-card[data-plan-tier='student_pro']").get_by_text("No automatic renewal", exact=False).wait_for()
                assert "/30 days" in page.locator("#pricing-page-content .pricing-tier-card[data-plan-tier='cyber_cafe']").inner_text()
                record("ID 208: paid pricing states 30 days and no automatic renewal")
                page.goto(base + "/compress-image-online", wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files(str(photo))
                assert page.locator("#target_kb").input_value() == "100"
                page.locator("#run-button").click()
                photo_link = page.locator("#result-download-link:not([hidden])")
                photo_link.wait_for(state="visible", timeout=30000)
                with page.expect_download(timeout=30000) as event:
                    photo_link.click()
                compressed = directory / "compressed.jpg"
                event.value.save_as(compressed)
                with Image.open(compressed) as image:
                    image.verify()
                assert compressed.stat().st_size <= 100 * 1024
                record("ID 224: untouched 100 KB target produced a valid image below the target")
                page.goto(base + "/repair-pdf", wait_until="domcontentloaded")
                page.locator("#client-privacy-toggle").evaluate("el => { if (el.checked) el.click(); }")
                page.locator("#file-input").set_input_files(str(paths[3]))
                page.locator("#mode").select_option(label="Validate structure only")
                page.locator("#run-button").click()
                valid_link = page.locator("#result-download-link:not([hidden])")
                valid_link.wait_for(state="visible", timeout=30000)
                with page.expect_download(timeout=30000) as event:
                    valid_link.click()
                validated = directory / "validated.pdf"
                event.value.save_as(validated)
                assert validated.read_bytes() == paths[3].read_bytes()
                record("ID 212: readable repair choices and structure-only download preserve a valid PDF")
                page.goto(base + "/repair-pdf", wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files(str(broken))
                page.locator("#run-button").click()
                page.get_by_text("This PDF is too damaged to repair automatically.", exact=False).first.wait_for(timeout=30000)
                record("ID 225: corrupt PDF displayed the safe repair error")
                page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                page.locator("#cloud-drop-btn").click()
                page.locator("#cloud-url").fill("https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf")
                page.locator("#cloud-submit-btn").click()
                page.locator("#file-list").get_by_text("dummy.pdf", exact=False).wait_for(state="visible", timeout=45000)
                record("ID 4: public W3C PDF imported through the cloud form")
                page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                page.locator("#client-privacy-toggle").evaluate("el => { if (el.checked) el.click(); }")
                page.locator("#file-input").set_input_files([str(large), str(ten)])
                page.locator("#run-button").click()
                merged_link = page.locator("#result-download-link:not([hidden])")
                merged_link.wait_for(state="visible", timeout=180000)
                with page.expect_download(timeout=30000) as event:
                    merged_link.click()
                merged = directory / "large-merged.pdf"
                event.value.save_as(merged)
                with fitz.open(merged) as pdf:
                    assert pdf.page_count == 769
                    assert "Large document page 759" in pdf[758].get_text()
                    assert "Second document page 10" in pdf[768].get_text()
                record("ID 207: synthetic 60 MiB/759-page PDF plus 10 pages merged to 769 pages in server mode")
                slow_context = browser.new_context()
                slow_context.add_cookies([{"name": "paperplane_token", "value": tokens["cyber_cafe"], "url": base}])
                slow_context.add_init_script("""(() => { const original = window.fetch.bind(window); window.fetch = (url, options) => String(url).includes('/api/auth/me') ? new Promise(resolve => setTimeout(() => resolve(original(url, options)), 1500)) : original(url, options); })();""")
                slow_page = slow_context.new_page()
                slow_page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                slow_page.locator("#file-input").set_input_files([str(large), str(ten)])
                slow_page.locator("#file-list").get_by_text("synthetic-large.pdf", exact=False).wait_for(timeout=15000)
                assert slow_page.locator("#run-button").is_enabled()
                slow_context.close()
                record("ID 168 and additional bug: early paid upload waits for account restoration before size checks")
                page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files([str(paths[3]), str(paths[3])])
                page.locator("#client-privacy-toggle").evaluate("el => { if (el.checked) el.click(); }")
                page.evaluate("""() => {
                  const originalOpen = XMLHttpRequest.prototype.open;
                  const originalSend = XMLHttpRequest.prototype.send;
                  const originalAbort = XMLHttpRequest.prototype.abort;
                  XMLHttpRequest.prototype.open = function(method, url, ...rest) { this.__holdJobUpload = String(url) === '/api/jobs'; return originalOpen.call(this, method, url, ...rest); };
                  XMLHttpRequest.prototype.abort = function() { if (this.__holdJobUpload) { window.__uploadAborted = true; this.onabort?.(new Event('abort')); return; } return originalAbort.call(this); };
                  XMLHttpRequest.prototype.send = function(body) {
                    if (this.__holdJobUpload) { this.upload.dispatchEvent(new ProgressEvent('progress', {lengthComputable:true, loaded:50, total:100})); return; }
                    return originalSend.call(this, body);
                  };
                }""")
                page.locator("#run-button").click()
                page.get_by_text("Uploading files…").wait_for()
                page.wait_for_function("document.querySelector('#progress-bar-fill')?.value === 50")
                page.locator("#job-cancel-btn").click()
                page.wait_for_function("window.__uploadAborted === true")
                page.locator("#job-cancel-btn").wait_for(state="hidden")
                record("ID 207: XHR upload progress reached 50%; cancellation restored Run control")
                page.goto(base + "/studio", wait_until="domcontentloaded")
                page.locator("#studio-file-input").set_input_files(str(paths[69]))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '69'", timeout=30000)
                page.wait_for_function("window.PaperplanePageOrganizer?.state?.totalCount === 69", timeout=30000)
                page.locator("#btn-mode-organize").click()
                page.locator('.organizer-thumb-card[data-page="2"] .thumb-checkbox-label').click()
                with page.expect_response("**/api/studio/pages/reorder", timeout=30000) as moved:
                    page.locator("#batch-move-up-btn").click()
                assert moved.value.status == 200
                page.get_by_text("Pages reordered successfully.", exact=True).wait_for(timeout=30000)
                with page.expect_download(timeout=30000) as event:
                    page.locator("#save-studio-btn").click()
                reordered = directory / "reordered.pdf"
                event.value.save_as(reordered)
                with fitz.open(reordered) as pdf:
                    assert "page 2" in pdf[0].get_text() and "page 1" in pdf[1].get_text()
                record("ID 210: mouse selected page 2, moved it earlier and downloaded verified order")
                for button, modal, close in (("#studio-sign-btn", "#digital-sign-modal", "#modal-close-digital-sign"),
                                             ("#studio-security-btn", "#security-modal", "#modal-close-security")):
                    page.locator("#btn-more-tools-trigger").click()
                    page.locator(button).click()
                    page.locator(modal).wait_for(state="visible")
                    assert page.url.endswith("/studio")
                    page.locator(close).click()
                record("ID 227 and additional bug: Studio signature and security actions open their dialogs without navigation")
                for before in (69, 68):
                    page.wait_for_function("number => window.PaperplanePageOrganizer?.state?.totalCount === number", arg=before, timeout=30000)
                    page.evaluate("number => { window.PaperplanePageOrganizer.deletePages([number]); }", before)
                    with page.expect_response("**/api/studio/page/delete", timeout=30000) as deleted:
                        page.get_by_role("button", name="Delete pages").click()
                    assert deleted.value.status == 200
                    page.wait_for_function("number => document.querySelector('#page-total-indicator')?.textContent === String(number)", arg=before - 1, timeout=30000)
                    page.reload(wait_until="domcontentloaded")
                    page.wait_for_function("number => document.querySelector('#page-total-indicator')?.textContent === String(number)", arg=before - 1, timeout=30000)
                    with page.expect_download(timeout=30000) as event:
                        page.locator("#save-studio-btn").click()
                    result = directory / f"retained-{before - 1}.pdf"
                    event.value.save_as(result)
                    with fitz.open(result) as pdf:
                        assert pdf.page_count == before - 1
                        assert f"page {before - 1}" in pdf[-1].get_text()
                record("ID 3: 69 to 68 to 67 deletions survived reload and downloaded files were inspected")
                page.evaluate("() => { writeLocalWork = async () => { throw new Error('synthetic storage failure'); }; }")
                page.locator("#studio-file-input").set_input_files(str(paths[3]))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '3'", timeout=30000)
                page.get_by_text("could not save the PDF locally", exact=False).first.wait_for(timeout=10000)
                page.reload(wait_until="domcontentloaded")
                page.get_by_text("last Studio change was not saved", exact=False).first.wait_for(timeout=15000)
                assert page.locator("#page-total-indicator").inner_text() == "0"
                record("ID 3: a failed local save did not restore an older document after reload")
                admin = context.new_page()
                admin.goto(base + "/", wait_until="domcontentloaded")
                admin.evaluate("token => sessionStorage.setItem('pp_admin_session', token)", tokens["admin"])
                admin.goto(base + "/admin", wait_until="domcontentloaded")
                admin.locator("#tab-feedback-btn").wait_for(state="visible", timeout=15000)
                admin.locator("#tab-feedback-btn").click()
                admin.locator("#feedback-refresh-status").get_by_text("Updated", exact=False).wait_for(timeout=15000)
                page.goto(base + "/feedback", wait_until="domcontentloaded")
                page.locator("#feedback-page-open").click()
                message = "Synthetic browser feedback " + secrets.token_hex(6)
                page.locator("#pp-fb-text-input").fill(message)
                page.locator("#pp-btn-feedback-submit").click()
                page.locator("#pp-feedback-success-body").wait_for(state="visible")
                admin.get_by_text(message, exact=False).wait_for(state="visible", timeout=20000)
                record("ID 102: submitted feedback appeared in the open admin tab without refresh")
                browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
