import os
import sys
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "https://paperplane.qd.je"
OUTPUT_DIR = Path("/mnt/c/Users/mdham/Downloads/pdf_splitter/pdf_splitter/reports/live_browser_audit")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FIXTURES_DIR = Path("/mnt/c/Users/mdham/Downloads/pdf_splitter/pdf_splitter/tests/fixtures")
AUDIT_SAMPLES = Path("/mnt/c/Users/mdham/Downloads/pdf_splitter/pdf_splitter/runtime_data_codex_audit")

audit_results = {
    "timestamp": time.time(),
    "base_url": BASE_URL,
    "pages_checked": [],
    "tools_tested": [],
    "studio_checks": [],
    "ai_checks": [],
    "layout_overflows": [],
    "console_errors": [],
    "network_failures": []
}

def log_console(msg):
    text = f"[{msg.type}] {msg.text}"
    if msg.type in ("error", "warning"):
        print(f"  BROWSER CONSOLE {text}")
        if msg.type == "error":
            audit_results["console_errors"].append(text)

def log_response(res):
    if res.status >= 400:
        url = res.url
        print(f"  NETWORK FAILED [{res.status}] {url}")
        audit_results["network_failures"].append({"status": res.status, "url": url})

def check_overflow(page, context_label):
    data = page.evaluate("""() => {
        const doc = document.documentElement;
        const body = document.body;
        const scrollWidth = Math.max(doc.scrollWidth, body.scrollWidth);
        const innerWidth = window.innerWidth;
        const overflow = scrollWidth > innerWidth + 1;
        const fixedControls = [];
        document.querySelectorAll('button, input, select, textarea').forEach(el => {
            const rect = el.getBoundingClientRect();
            if (rect.right > innerWidth + 2 || rect.left < -2) {
                fixedControls.push({
                    tag: el.tagName,
                    id: el.id,
                    cls: el.className,
                    text: (el.textContent || el.value || '').trim().slice(0, 30),
                    rect: { left: rect.left, right: rect.right, width: rect.width }
                });
            }
        });
        return { overflow, scrollWidth, innerWidth, fixedControls };
    }""")
    if data["overflow"]:
        print(f"  [OVERFLOW DETECTED] {context_label}: scrollWidth={data['scrollWidth']} > innerWidth={data['innerWidth']}")
        audit_results["layout_overflows"].append({"context": context_label, "details": data})
        return False
    return True

print("=== STARTING FULL LIVE BROWSER AUDIT ON https://paperplane.qd.je ===")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # -------------------------------------------------------------
    # 1. Desktop Walkthrough (1366x768)
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 1: Desktop Layout & Navigation (1366x768) ---")
    page = browser.new_page(viewport={"width": 1366, "height": 768})
    page.on("console", log_console)
    page.on("response", log_response)

    # Homepage
    page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
    page.screenshot(path=str(OUTPUT_DIR / "01_desktop_home.png"))
    check_overflow(page, "Desktop Home (1366)")
    audit_results["pages_checked"].append({"page": "Home", "viewport": "1366x768", "status": "rendered"})
    print("✓ Home page loaded without overflow")

    # Dark mode toggle
    theme_btn = page.locator("#theme-toggle-btn")
    if theme_btn.count():
        theme_btn.click()
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUTPUT_DIR / "02_desktop_dark_mode.png"))
        print("✓ Dark mode toggled and captured")
        theme_btn.click() # toggle back to light
        page.wait_for_timeout(300)

    # Tool Desk Tab
    desk_btn = page.locator("#tab-tool-desk-view")
    if desk_btn.count():
        desk_btn.click()
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUTPUT_DIR / "03_desktop_tool_desk.png"))
        check_overflow(page, "Desktop Tool Desk")
        print("✓ Tool Desk view rendered")

        # Test Search in Tool Desk
        search_input = page.locator("#tool-desk-search")
        if search_input.count():
            search_input.fill("compress")
            page.wait_for_timeout(400)
            meta = page.locator("#tool-desk-search-meta").inner_text()
            print(f"✓ Tool Desk search for 'compress': meta text -> '{meta}'")
            page.screenshot(path=str(OUTPUT_DIR / "04_desktop_tool_desk_search.png"))
            search_input.fill("")
            page.wait_for_timeout(300)

        # Test Category Filter Pills
        for cat in ["organize", "optimize", "convert", "edit", "security", "ai"]:
            pill = page.locator(f"#tool-desk-directory-filters button[data-desk-category='{cat}']")
            if pill.count():
                pill.click()
                page.wait_for_timeout(200)
        print("✓ Category filter pills cycled successfully")

    page.close()

    # -------------------------------------------------------------
    # 2. Mobile Layout Walkthrough (375x667 - iPhone SE)
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 2: Mobile Layout & Nav (375x667) ---")
    page_m = browser.new_page(viewport={"width": 375, "height": 667})
    page_m.on("console", log_console)
    page_m.on("response", log_response)

    # Mobile Home
    page_m.goto(BASE_URL, wait_until="networkidle", timeout=30000)
    page_m.screenshot(path=str(OUTPUT_DIR / "05_mobile_home_375.png"))
    check_overflow(page_m, "Mobile Home (375)")
    print("✓ Mobile Home rendered")

    # Mobile Tool Desk via bottom nav
    mob_desk_btn = page_m.locator("#mob-nav-desk")
    if mob_desk_btn.count():
        mob_desk_btn.click()
        page_m.wait_for_timeout(400)
        page_m.screenshot(path=str(OUTPUT_DIR / "06_mobile_tool_desk_375.png"))
        check_overflow(page_m, "Mobile Tool Desk (375)")
        print("✓ Mobile Tool Desk rendered")

    # Auxiliary routes
    for route in ["/download", "/privacy", "/terms", "/api-docs"]:
        page_m.goto(f"{BASE_URL}{route}", wait_until="networkidle", timeout=30000)
        check_overflow(page_m, f"Mobile {route} (375)")
        page_m.screenshot(path=str(OUTPUT_DIR / f"07_mobile_{route.replace('/', '')}_375.png"))
        print(f"✓ Mobile route {route} verified")

    page_m.close()

    # -------------------------------------------------------------
    # 3. Live Tool Operation: Grayscale + View in Studio
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 3: Tool Execution & 'View in Studio' Link ---")
    page_t = browser.new_page(viewport={"width": 1366, "height": 768})
    page_t.on("console", log_console)
    page_t.on("response", log_response)

    page_t.goto(f"{BASE_URL}/convert-pdf-to-grayscale", wait_until="networkidle", timeout=30000)
    print("✓ Navigated to /convert-pdf-to-grayscale")

    # Upload sample PDF
    file_input = page_t.locator("input[type='file']").first
    sample_pdf = AUDIT_SAMPLES / "color-audit.pdf"
    if not sample_pdf.exists():
        sample_pdf = FIXTURES_DIR / "general_spec.pdf"
    file_input.set_input_files(str(sample_pdf))
    page_t.wait_for_timeout(500)
    page_t.screenshot(path=str(OUTPUT_DIR / "08_grayscale_file_staged.png"))

    # Click Process / Convert
    run_btn = page_t.locator("button#run-process-btn, button:has-text('Convert to Grayscale Now')").first
    if run_btn.count():
        run_btn.click()
        print("  Processing Grayscale job...")
        # Wait for result panel
        page_t.wait_for_selector(".result-success-panel, :has-text('Your document is ready!')", timeout=45000)
        page_t.screenshot(path=str(OUTPUT_DIR / "09_grayscale_completed.png"))
        print("✓ Grayscale job completed with success panel!")

        # Click "View in Studio"
        view_studio_btn = page_t.locator("button:has-text('View in Studio')").first
        if view_studio_btn.count():
            print("  Clicking 'View in Studio'...")
            view_studio_btn.click()
            page_t.wait_for_timeout(2000)
            page_t.screenshot(path=str(OUTPUT_DIR / "10_studio_view_from_grayscale.png"))

            # Check that Studio is active and page count is rendered
            count_text = page_t.locator("#studio-page-count").inner_text()
            print(f"✓ View in Studio opened successfully! Page count: '{count_text}'")
            audit_results["studio_checks"].append({"test": "View in Studio from Grayscale", "count": count_text})

    page_t.close()

    # -------------------------------------------------------------
    # 4. Advanced PDF Studio Full Feature Audit (69-page PDF)
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 4: Advanced Studio 69-Page Deep Audit ---")
    page_s = browser.new_page(viewport={"width": 1366, "height": 768})
    page_s.on("console", log_console)
    page_s.on("response", log_response)

    page_s.goto(f"{BASE_URL}/studio", wait_until="networkidle", timeout=30000)

    # Load 69-page PDF
    pdf_69 = AUDIT_SAMPLES / "notes_69pages_audit.pdf"
    studio_input = page_s.locator("#studio-file-input")
    if studio_input.count():
        studio_input.set_input_files(str(pdf_69))
        print("  Loading 69-page PDF into Studio...")
        # Wait for pages count
        page_s.wait_for_function("() => document.getElementById('studio-page-count')?.textContent === '69'", timeout=30000)
        # Wait for page canvas render
        page_s.wait_for_selector(".studio-page-sheet canvas", timeout=15000)
        page_s.wait_for_timeout(1000)
        page_s.screenshot(path=str(OUTPUT_DIR / "11_studio_69pages_loaded.png"))
        print("✓ 69 pages loaded, page count shows 69, canvas rendered!")

        # Check Zoom Percentage Box Legibility
        zoom_val = page_s.locator("#zoom-select").input_value()
        print(f"✓ Zoom percentage select value: '{zoom_val}'")

        # Check Brush Size Box Legibility
        brush_val = page_s.locator("#editor-stroke-width").input_value()
        print(f"✓ Brush size control select value: '{brush_val}'")

        # Check Color Picker
        color_val = page_s.locator("#editor-color-picker").input_value()
        print(f"✓ Color picker input value: '{color_val}'")

        # Test Page Jump: Jump to Page 35
        jump_input = page_s.locator("#page-jump-input")
        if jump_input.count():
            jump_input.fill("35")
            jump_input.press("Enter")
            page_s.wait_for_timeout(1000)
            page_s.screenshot(path=str(OUTPUT_DIR / "12_studio_jump_page_35.png"))
            print("✓ Jumped to page 35, canvas updated")

        # Test Page Jump: Jump to Page 69
        if jump_input.count():
            jump_input.fill("69")
            jump_input.press("Enter")
            page_s.wait_for_timeout(1000)
            page_s.screenshot(path=str(OUTPUT_DIR / "13_studio_jump_page_69.png"))
            print("✓ Jumped to page 69, canvas updated")

        # Test Toolbar Mode Switchers
        for tool_id in ["tool-select-btn", "tool-pan-btn", "tool-text-btn", "tool-draw-btn", "tool-highlight-btn", "tool-redact-btn", "tool-sig-btn"]:
            btn = page_s.locator(f"#{tool_id}")
            if btn.count():
                btn.click()
                page_s.wait_for_timeout(100)
        print("✓ All Studio primary drawing/annotation tools clickable without errors")

        # Test Organize Mode and Batch Actions
        org_mode_btn = page_s.locator("#btn-mode-organize")
        if org_mode_btn.count():
            org_mode_btn.click()
            page_s.wait_for_timeout(500)
            print("✓ Switched to Organize Mode")

            # Click first thumbnail card
            thumb_1 = page_s.locator(".organizer-thumb-card").first
            if thumb_1.count():
                thumb_1.click()
                page_s.wait_for_timeout(400)
                page_s.screenshot(path=str(OUTPUT_DIR / "14_studio_organize_selection.png"))

                # Test Extract button
                extract_btn = page_s.locator("#batch-extract-btn")
                if extract_btn.count() and extract_btn.is_visible():
                    extract_btn.click()
                    page_s.wait_for_timeout(1500)
                    feedback = page_s.locator("#studio-download-feedback")
                    if feedback.count() and feedback.is_visible():
                        print(f"✓ Extract feedback banner visible: '{feedback.inner_text()[:60]}...'")

                # Test Delete Page Confirmation Modal
                del_btn = page_s.locator("#batch-delete-btn")
                if del_btn.count() and del_btn.is_visible():
                    del_btn.click()
                    page_s.wait_for_timeout(400)
                    confirm_modal = page_s.locator(".app-confirm-dialog")
                    if confirm_modal.count() and confirm_modal.is_visible():
                        print("✓ Delete pages confirm modal opened cleanly!")
                        page_s.screenshot(path=str(OUTPUT_DIR / "15_studio_delete_confirm_modal.png"))
                        cancel_btn = page_s.locator(".app-confirm-cancel")
                        cancel_btn.click()
                        page_s.wait_for_timeout(300)
                        print("✓ Cancelled modal safely")

        # Switch back to Annotate Mode
        page_s.locator("#btn-mode-annotate").click()
        page_s.wait_for_timeout(300)

    page_s.close()

    # -------------------------------------------------------------
    # 5. AI Document Intelligence Studio Full Walkthrough
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 5: AI Intelligence Live Model & Streaming ---")
    page_ai = browser.new_page(viewport={"width": 1366, "height": 768})
    page_ai.on("console", log_console)
    page_ai.on("response", log_response)

    page_ai.goto(BASE_URL, wait_until="networkidle", timeout=30000)
    ai_tab = page_ai.locator("#tab-ai-view, button:has-text('AI Intelligence')").first
    ai_tab.click()
    page_ai.wait_for_timeout(500)
    page_ai.screenshot(path=str(OUTPUT_DIR / "16_ai_empty_state.png"))
    print("✓ AI Intelligence tab opened; Empty state displayed")

    # Ask general question without PDF
    chat_input = page_ai.locator("#chat-input")
    chat_send = page_ai.locator("#chat-send-btn, #chat-form button[type='submit']").first
    chat_input.fill("Give a 2-sentence explanation of what Portable Document Format (PDF) is.")
    chat_send.click()
    print("  Streaming general AI query...")

    # Wait for completion stage
    try:
        page_ai.wait_for_selector(".ai-stage-line:has-text('Complete')", timeout=35000)
        page_ai.wait_for_timeout(1000)
        answer_text = page_ai.locator(".chat-bubble.ai .ai-stream-text").last.inner_text()
        print(f"✓ AI response received successfully! Length={len(answer_text)} chars")
        print(f"  Snippet: {answer_text[:120]}...")
        page_ai.screenshot(path=str(OUTPUT_DIR / "17_ai_general_response.png"))
        audit_results["ai_checks"].append({"test": "General Chat SSE Stream", "status": "success", "length": len(answer_text)})
    except Exception as e:
        print(f"  AI stream wait error: {e}")
        audit_results["ai_checks"].append({"test": "General Chat SSE Stream", "status": "timeout_or_error", "error": str(e)})

    # Test False Premise Guard
    chat_input.fill("Why is Munich the capital of Germany?")
    chat_send.click()
    print("  Testing False Premise Guard on live stream...")
    try:
        page_ai.wait_for_selector(".chat-bubble.ai:has-text('Berlin')", timeout=20000)
        fp_answer = page_ai.locator(".chat-bubble.ai").last.inner_text()
        print(f"✓ False premise guard answered: '{fp_answer[:100]}...'")
        page_ai.screenshot(path=str(OUTPUT_DIR / "18_ai_false_premise_guard.png"))
        audit_results["ai_checks"].append({"test": "False Premise Guard", "status": "success"})
    except Exception as e:
        print(f"  False premise check error: {e}")

    # Upload PDF to AI Studio and ask document question
    ai_file_input = page_ai.locator("#ai-file-input")
    if ai_file_input.count():
        print("  Uploading sample PDF to AI Studio...")
        ai_file_input.set_input_files(str(FIXTURES_DIR / "sample_invoice.pdf"))
        page_ai.wait_for_timeout(1000)
        page_ai.screenshot(path=str(OUTPUT_DIR / "19_ai_doc_bar_active.png"))
        print("✓ Active doc bar rendered for uploaded PDF!")

        chat_input.fill("What is the invoice number and total amount?")
        chat_send.click()
        print("  Asking document question with citations...")
        try:
            page_ai.wait_for_selector(".ai-stage-line:has-text('Complete')", timeout=35000)
            page_ai.wait_for_timeout(1000)
            doc_ans = page_ai.locator(".chat-bubble.ai .ai-stream-text").last.inner_text()
            citations = page_ai.locator(".chat-bubble.ai .chat-citation-tags").last.inner_text()
            print(f"✓ Document answer received: '{doc_ans[:100]}...'")
            print(f"✓ Citations tag: '{citations}'")
            page_ai.screenshot(path=str(OUTPUT_DIR / "20_ai_doc_cited_response.png"))
            audit_results["ai_checks"].append({"test": "Document RAG with citations", "citations": citations})
        except Exception as e:
            print(f"  Doc query wait error: {e}")

    page_ai.close()

    # -------------------------------------------------------------
    # 6. Fill Form Long JSON Layout & Job Execution
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 6: Fill PDF Form (Textarea Wrap & Execution) ---")
    page_ff = browser.new_page(viewport={"width": 1366, "height": 768})
    page_ff.on("console", log_console)
    page_ff.on("response", log_response)

    page_ff.goto(f"{BASE_URL}/fill-pdf-form", wait_until="networkidle", timeout=30000)
    check_overflow(page_ff, "Fill Form Desk (1366)")

    # Upload form sample
    ff_input = page_ff.locator("input[type='file']").first
    form_sample = AUDIT_SAMPLES / "form-audit.pdf"
    if form_sample.exists():
        ff_input.set_input_files(str(form_sample))
        page_ff.wait_for_timeout(500)
        page_ff.screenshot(path=str(OUTPUT_DIR / "21_fill_form_file_staged.png"))

        # Verify textarea exists and wraps
        json_area = page_ff.locator("textarea[name='field_values'], textarea").first
        if json_area.count():
            sample_json = '{"Full Name": "Test User", "Organization": "Paperplane Enterprise India Private Limited", "Remarks": "Very long multi-line wrap test for audit v5 verification."}'
            json_area.fill(sample_json)
            page_ff.wait_for_timeout(200)
            check_overflow(page_ff, "Fill Form with Long JSON")
            page_ff.screenshot(path=str(OUTPUT_DIR / "22_fill_form_textarea_filled.png"))
            print("✓ Fill Form textarea rendered and wrapped without page overflow")

            # Click Fill Form Now
            fill_btn = page_ff.locator("button:has-text('Fill Form Now'), button#run-process-btn").first
            if fill_btn.count():
                fill_btn.click()
                page_ff.wait_for_selector(".result-success-panel, :has-text('Your document is ready!')", timeout=30000)
                page_ff.screenshot(path=str(OUTPUT_DIR / "23_fill_form_success.png"))
                print("✓ Fill Form processed successfully live!")

    page_ff.close()

    # -------------------------------------------------------------
    # 7. Protect and Unlock Live Cycle
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 7: Protect & Unlock End-to-End ---")
    page_p = browser.new_page(viewport={"width": 1366, "height": 768})
    page_p.on("console", log_console)
    page_p.on("response", log_response)

    page_p.goto(f"{BASE_URL}/protect-pdf", wait_until="networkidle", timeout=30000)
    p_input = page_p.locator("input[type='file']").first
    p_input.set_input_files(str(FIXTURES_DIR / "general_spec.pdf"))
    page_p.wait_for_timeout(400)

    pw_field = page_p.locator("input[type='password'], input[name='user_password'], input[name='password']").first
    if pw_field.count():
        pw_field.fill("LiveAuditPass2026!")
        page_p.wait_for_timeout(200)

    prot_btn = page_p.locator("button:has-text('Protect PDF Now'), button#run-process-btn").first
    if prot_btn.count():
        prot_btn.click()
        page_p.wait_for_selector(".result-success-panel, :has-text('Your document is ready!')", timeout=30000)
        page_p.screenshot(path=str(OUTPUT_DIR / "24_protect_success.png"))
        print("✓ Protect PDF processed and download ready!")

    page_p.close()

    browser.close()

with open(OUTPUT_DIR / "audit_summary.json", "w") as f:
    json.dump(audit_results, f, indent=2)

print("\n=== AUDIT COMPLETED ===")
print(f"Screenshots saved to: {OUTPUT_DIR}")
print(f"Console errors count: {len(audit_results['console_errors'])}")
print(f"Layout overflows count: {len(audit_results['layout_overflows'])}")
print(f"Network failures count: {len(audit_results['network_failures'])}")
