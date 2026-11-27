"""Content-check PDF-to-Markdown and Word in a disposable production image."""
from __future__ import annotations
import json, secrets, socket, subprocess, time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PDF = ROOT / "tmp/pdfs/arxiv-1706.03762-v7.pdf"
IMAGE = "pdf_splitter-paperplane:latest"
CONTAINER = "paperplane-v24-id334-335-production-smoke"
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0)); PORT = sock.getsockname()[1]
BASE = f"http://127.0.0.1:{PORT}"
run = lambda args, **kw: subprocess.run(args, check=True, capture_output=True, text=True, **kw)
if subprocess.run(["docker", "ps", "-aq", "--filter", f"name=^{CONTAINER}$"], capture_output=True, text=True).stdout.strip():
    raise RuntimeError("Refusing to reuse an existing container")
admin, code, session = (secrets.token_urlsafe(n) for n in (48, 32, 48))
started = False
evidence = {"image": run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"]).stdout.strip(), "checks": {}, "page_errors": [], "console_errors": []}
try:
    run(["docker", "run", "-d", "--name", CONTAINER, "--restart=no", "--cpus=4", "--memory=4g", "--pids-limit=1024", "--security-opt=no-new-privileges", "-p", f"127.0.0.1:{PORT}:8501", "--tmpfs", "/data:rw,nosuid,nodev,size=256m", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m", "-e", "PAPERPLANE_ENV=production", "-e", "PAPERPLANE_SKIP_DOTENV=1", "-e", "PAPERPLANE_WORKERS=2", "-e", "PAPERPLANE_DATA_DIR=/data", "-e", "PAPERPLANE_PORT=8501", "-e", "PAPERPLANE_PUBLIC_URL=https://paperplane.example.test", "-e", "PAPERPLANE_SECURE_COOKIES=false", "-e", f"PAPERPLANE_ADMIN_KEY={admin}", "-e", f"PAPERPLANE_ADMIN_CODE={code}", "-e", f"PAPERPLANE_SESSION_SECRET={session}", "-e", "CASHFREE_ENV=TEST", IMAGE])
    started = True
    for _ in range(90):
        try:
            with urlopen(BASE + "/api/health", timeout=2) as response:
                if response.status == 200: break
        except Exception: time.sleep(1)
    else: raise RuntimeError("Production image did not become healthy")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
        page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
        page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
        page.goto(BASE + "/pdf-to-markdown", wait_until="domcontentloaded")
        asset = page.locator('script[src*="/assets/app.js"]').get_attribute("src")
        worker = page.evaluate("fetch('/assets/service-worker.js').then(r => r.text())")
        stylesheet = page.locator('link[href*="/assets/styles.css"]').get_attribute("href")
        assert "app.js?v=187" in asset and "styles.css?v=69" in stylesheet
        assert "paperplane-shell-v138" in worker and "app.js?v=187" in worker and "styles.css?v=69" in worker
        layout_checks = []
        for width in (320, 390, 1366):
            page.set_viewport_size({"width": width, "height": 900})
            metrics = page.locator("#file-hint").evaluate("el => { const r=el.getBoundingClientRect(); const p=el.parentElement.getBoundingClientRect(); return {left:r.left,parentLeft:p.left,right:r.right,parentRight:p.right,scrollWidth:el.scrollWidth,clientWidth:el.clientWidth,height:r.height,display:getComputedStyle(el).display}; }")
            assert metrics["left"] >= metrics["parentLeft"] - 1 and metrics["right"] <= metrics["parentRight"] + 1, (width, metrics)
            assert metrics["scrollWidth"] <= metrics["clientWidth"] + 1 and metrics["display"] == "block", (width, metrics)
            layout_checks.append({"width": width, **metrics})
        page.set_viewport_size({"width": 320, "height": 900})
        page.evaluate("window.openSettingsModal('privacy')")
        privacy_tab = page.locator("#settings-tab-btn-privacy")
        privacy_tab.wait_for(state="visible")
        privacy_metrics = privacy_tab.evaluate("el => { const r=el.getBoundingClientRect(); return {left:r.left,right:r.right,selected:el.classList.contains('active'),scrollLeft:el.closest('.settings-tabs').scrollLeft}; }")
        assert privacy_metrics["selected"] and privacy_metrics["left"] >= -1 and privacy_metrics["right"] <= 321, privacy_metrics
        page.locator("#close-settings-modal").click()
        page.set_viewport_size({"width": 1366, "height": 900})
        page.locator("#file-input").set_input_files({"name": "a5e7074e4bb844cdb8a39a50783e06b5_browser-download-1706.03762v7.pdf", "mimeType": "application/pdf", "buffer": PDF.read_bytes()})
        page.locator("#run-button").click()
        link = page.locator("#result-download-link"); link.wait_for(state="visible", timeout=120000)
        page.wait_for_function("document.querySelector('#result-meta')?.innerText.includes('math/custom-font glyphs were replaced')", timeout=120000)
        with page.expect_download(timeout=60000) as info: link.click()
        download = info.value; target = OUT / download.suggested_filename; download.save_as(target)
        content = target.read_text(encoding="utf-8")
        assert "Attention Is All You Need" in content
        assert "# a5e7074e4bb844cdb8a39a50783e06b5" not in content
        assert "performing models also connect the encoder and decoder through an attention mechanism." in " ".join(content.split())
        assert "We propose a new simple network architecture, the Transformer," in " ".join(content.split())
        assert "[math/custom glyph]" in content
        ai_calls = []
        def controlled_chat(route):
            ai_calls.append(route.request.post_data or "")
            if len(ai_calls) == 1:
                body = 'event: error\ndata: {"message":"AI service returned HTTP 429. Please retry later."}\n\n'
            else:
                body = ('event: replace\ndata: {"text":"Fallback answer for the question."}\n\n'
                        'event: done\ndata: {"citations":[],"mode":"provider_fallback"}\n\n')
            route.fulfill(status=200, content_type="text/event-stream", body=body)
        page.route("**/api/ai/chat/stream", controlled_chat)
        page.goto(BASE + "/ai-intelligence", wait_until="domcontentloaded")
        page.locator("#chat-input").wait_for(state="visible", timeout=15000)
        question = "Explain why the sky looks blue."
        page.locator("#chat-input").fill(question)
        page.locator("#chat-send-btn").click()
        page.locator(".ai-chat-retry").wait_for(state="visible", timeout=15000)
        failed_user_count = page.locator(".chat-bubble.user").count()
        page.locator(".ai-chat-retry").click()
        page.get_by_text("Fallback answer for the question.", exact=False).wait_for(timeout=15000)
        page.wait_for_function("document.querySelectorAll('.chat-bubble.user').length === 1")
        retry_user_count = page.locator(".chat-bubble.user").count()
        assert len(ai_calls) == 2 and failed_user_count == 1
        retry_error_removed = page.get_by_text("Connection interrupted", exact=True).count() == 0
        assert retry_error_removed and retry_user_count == 1
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(BASE + "/studio", wait_until="domcontentloaded")
        clear_label = page.locator("#studio-clear-pdf-btn .tool-btn-text")
        clear_label.wait_for(state="visible", timeout=15000)
        clear_label_metrics = clear_label.evaluate("el => ({text:el.innerText.trim(),scrollHeight:el.scrollHeight,clientHeight:el.clientHeight})")
        assert clear_label_metrics["text"] == "Clear PDF" and clear_label_metrics["scrollHeight"] <= clear_label_metrics["clientHeight"] + 1, clear_label_metrics
        evidence["checks"] = {"health": "ok", "assets": {"app": asset, "stylesheet": stylesheet, "service_worker": "v138 includes app.js?v=187 and styles.css?v=69"}, "dropzone_hint_layout": layout_checks, "settings_privacy_tab_at_320px": privacy_metrics, "markdown": {"bytes": len(content.encode()), "paper_title_present": True, "internal_uuid_heading_absent": True, "spacing_phrases_preserved": True, "fallback_glyph_count": content.count("[math/custom glyph]")}}
        evidence["checks"]["studio_clear_pdf_label_at_390px"] = clear_label_metrics
        evidence["checks"]["ai_chat_retry"] = {"requests": len(ai_calls), "failed_state_user_question_count": failed_user_count, "after_retry_user_question_count": retry_user_count, "fallback_answer_visible": True, "retry_error_removed": retry_error_removed}
        assert not evidence["page_errors"] and not evidence["console_errors"], evidence
        evidence["result"] = "passed"; browser.close()
finally:
    if started:
        subprocess.run(["docker", "stop", "--time", "10", CONTAINER], check=False, capture_output=True, timeout=30)
        subprocess.run(["docker", "rm", "--force", CONTAINER], check=False, capture_output=True, timeout=30)
(OUT / "browser-id334-335-docker-image.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps(evidence, indent=2))
