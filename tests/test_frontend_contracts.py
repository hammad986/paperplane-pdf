from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
ADMIN = (ROOT / "web" / "assets" / "admin.js").read_text(encoding="utf-8")
EDITOR = (ROOT / "web" / "assets" / "editor.js").read_text(encoding="utf-8")
PAGE_ORGANIZER = (ROOT / "web" / "assets" / "page_organizer.js").read_text(encoding="utf-8")


def test_topbar_auth_and_settings_dashboard_contract():
    assert 'id="topbar-signin-btn"' in INDEX
    assert 'id="topbar-register-btn"' in INDEX
    assert 'id="topbar-user-profile-btn"' in INDEX
    assert 'class="settings-layout"' in INDEX
    assert 'id="settings-tab-btn-privacy"' in INDEX
    assert 'id="settings-client-privacy-toggle"' in INDEX
    assert "width: min(94vw, 1020px)" in STYLES
    assert "height: 78vh" in STYLES
    assert "body.light-mode .settings-modal-card" in STYLES
    assert "overflow: hidden" in STYLES
    assert 'settings-tab-btn" data-tab="appearance"' in INDEX
    assert '<span>Theme</span>' not in INDEX
    assert '<span>Tier</span>' not in INDEX
    assert '<span>Lock</span>' not in INDEX


def test_ai_desk_workflows_are_on_screen_contracts():
    assert 'id="result-content"' in INDEX
    assert 'id="question"' in APP
    assert "runDeskAiWorkflow" in APP
    assert "submitAsyncAiJob" in APP
    assert "/api/ai/chat" in APP
    assert "/api/ai/summarize/pdf" in APP
    assert "/api/ai/extract" in APP
    assert "/api/jobs" in APP
    assert "Open in Full AI Interactive Studio" in APP
    assert "Download PDF" in INDEX


def test_summary_markdown_renderer_handles_four_to_six_hash_headings():
    assert "const heading = /^(#{1,6})\\s+(.+)$/" in APP
    assert "Math.min(heading[1].length + 1, 6)" in APP


def test_form_control_contrast_contract():
    assert "select option" in STYLES
    assert "color: #142023 !important" in STYLES
    assert "body.dark-mode select option" in STYLES
    assert ".option-field input::placeholder" in STYLES
    assert "o.style.display = fields ? '' : 'none'" in APP


def test_success_toasts_reposition_around_visible_result_actions():
    assert "toast-result-aware-success" in APP
    assert "window.addEventListener('scroll', scheduleResultToastPosition" in APP
    assert "belowTop + toastRect.height <= bottomBoundary" in APP
    assert "aboveTop + toastRect.height <= window.innerHeight - 8" in APP
    assert ".toast-notice.toast-result-aware-success" in STYLES
    assert "animation: none" in STYLES


def test_settings_privacy_switch_keeps_44px_hit_target_in_flex_row():
    assert ".settings-privacy-toggle-row > label.toggle-switch-sm" in STYLES
    assert "flex: 0 0 44px" in STYLES
    assert "width: 44px" in STYLES
    assert "height: 44px" in STYLES
    assert "inset: 13px 6px" in STYLES


def test_admin_plan_breakdown_uses_public_paid_plan_name():
    assert 'cyber_cafe: "All-In-One Pro & Developer"' in ADMIN
    assert 'escapeHtml(planDisplayName(tier))' in ADMIN
    assert 'escapeHtml(planDisplayName((ord.tier || "pro").toLowerCase()))' in ADMIN
    assert 'cyber_cafe: "Cyber Cafe"' not in ADMIN
    assert 'admin.js?v=22' in (ROOT / "server.py").read_text(encoding="utf-8")


def test_recurring_plan_periods_use_consistent_spacing():
    assert INDEX.count('<span class="tier-price-period">/ 30 days</span>') == 2
    assert '<span class="tier-price-period">/30 days</span>' not in INDEX


def test_phone_tool_layout_compacts_flow_before_fixed_workspace_navigation():
    assert "@media (max-width: 600px)" in STYLES
    assert ".dynamic-workspace { padding-block-start: 12px !important; }" in STYLES
    assert ".tool-desk-container { gap: 8px; }" in STYLES
    assert ".tool-desk-nav-bar { margin-block-end: 4px; }" in STYLES
    assert "#tool-description { display: none; }" in STYLES
    assert ".dropzone { padding-block: 12px; }" in STYLES
    assert ".options-panel { padding: 10px 12px; gap: 8px; }" in STYLES
    assert "body:not(.studio-active):not(.ai-active) #run-button" in STYLES
    assert "position: static" in STYLES


def test_mobile_tool_selection_scrolls_primary_action_clear_of_fixed_navigation():
    assert "function clearMobileNavigationFromToolAction()" in APP
    assert "actionRect.bottom - navigationRect.top + 8" in APP
    assert "window.setTimeout(clearMobileNavigationFromToolAction, 260)" in APP


def test_studio_annotations_are_saved_restored_and_cleared_with_their_pdf():
    assert "window.persistPaperplaneStudioEdits" in EDITOR
    assert "restoreSerialized(objects)" in EDITOR
    assert "writeLocalWork('studio-edits'" in APP
    assert "readLocalWork('studio-edits')" in APP
    assert "removeLocalWork('studio-pdf', 'studio-position', 'studio-edits')" in APP
    assert "studioEditRecordMatchesFile(saved.edits, file)" in APP
    assert "'/assets/editor.js?v=17'" in (ROOT / "web" / "assets" / "service-worker.js").read_text(encoding="utf-8")


def test_studio_organizer_page_number_stays_inside_narrow_tile():
    assert ".thumb-header {" in STYLES
    assert "grid-template-columns: minmax(20px, 1fr) 18px auto;" in STYLES
    assert ".thumb-page-num" in STYLES and "white-space: nowrap;" in STYLES
    assert 'href="/assets/styles.css?v=98"' in INDEX


def test_studio_page_sizes_do_not_fall_back_to_a4_and_use_pdfjs_page_view():
    assert "width: Number.isFinite(meta.width) && meta.width > 0 ? meta.width : null" in PAGE_ORGANIZER
    assert "height: Number.isFinite(meta.height) && meta.height > 0 ? meta.height : null" in PAGE_ORGANIZER
    assert "page.getViewport({ scale: 1.0 })" in PAGE_ORGANIZER
    assert "sizeLabel.textContent = `${Math.round(baseVp.width)}×${Math.round(baseVp.height)}pt`" in PAGE_ORGANIZER
    assert "page_organizer.js?v=23" in INDEX
    assert "'/assets/page_organizer.js?v=23'" in (ROOT / "web" / "assets" / "service-worker.js").read_text(encoding="utf-8")


def test_global_footer_is_revealed_when_a_short_page_has_no_scroll_range():
    assert "let refreshFooterReveal = () => {};" in APP
    assert "const footerInViewport = Boolean(footerRect && footerRect.top < window.innerHeight && footerRect.bottom > 0);" in APP
    assert "document.documentElement.scrollHeight > document.documentElement.clientHeight + 12" in APP
    assert "hasScrolled || (!hasScrollRange && footerInViewport)" in APP
    assert "refreshFooterReveal();" in APP


def test_service_worker_shell_tracks_current_app_bundle_version():
    service_worker = (ROOT / "web" / "assets" / "service-worker.js").read_text(encoding="utf-8")
    app_bundle = re.search(r'<script src="(/assets/app\.js\?v=\d+)"', INDEX)
    assert app_bundle
    assert f"'{app_bundle.group(1)}'" in service_worker
    assert re.search(r"const CACHE_NAME = 'paperplane-shell-v\d+';", service_worker)


def test_successful_processing_scrolls_result_actions_into_view_on_all_screens():
    result_handler = APP.split("const result = $('#result');", 1)[1].split("if (!silent)", 1)[0]
    assert "requestAnimationFrame(() => result.scrollIntoView({ block: mobileResultViewport ? 'end' : 'center', behavior: 'smooth' }));" in result_handler
    assert "window.matchMedia('(max-width: 900px)').matches" in result_handler
    assert "scrollIntoView({ block: mobileResultViewport ? 'end' : 'center'" in result_handler
    assert "#result { scroll-margin-bottom: calc(82px + env(safe-area-inset-bottom, 0px)); }" in (ROOT / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    assert ".ai-result-actions > * { min-height: 44px; box-sizing: border-box; }" in (ROOT / "web" / "assets" / "styles.css").read_text(encoding="utf-8")


def test_local_pdf_exports_keep_the_finished_progress_state_visible_briefly():
    assert "updateProgress(4, 100, 'Finished!')" in APP
    assert "localProgressDisplayToken === requestToken" in APP
    assert "}, 900);" in APP
    assert "completionVisible" in APP


def test_download_and_native_apps_waitlist_have_distinct_route_states():
    assert 'id="apps-waitlist-content"' in INDEX
    assert 'id="web-download-content"' in INDEX
    assert "Open the PDF workspace" in INDEX
    assert "download: updateHistory || window.location.pathname === '/download'" in APP
    assert "const showWebDownloads = updateHistory || window.location.pathname === '/download';" in APP
    assert "appContent.hidden = showWebDownloads" in APP
    assert "webContent.hidden = !showWebDownloads" in APP


def test_ai_chat_deduplicates_inline_and_standalone_page_citations():
    assert "textNode.innerHTML = renderMarkdown(answerText);" in APP
    assert "const inlineCitationPages = new Set(" in APP
    assert "textNode.querySelectorAll('[data-ai-page]')" in APP
    assert "responseCitations\n            .filter(page => !inlineCitationPages.has(page))" in APP


def test_mobile_header_keeps_the_pwa_install_prompt_reachable():
    assert ".topbar-right > :not(#topbar-auth-guest):not(#topbar-auth-user):not(#install-app-btn)" in STYLES
    assert "#install-app-btn { min-height: 44px" in STYLES


def test_progress_labels_do_not_claim_server_upload_for_local_processing():
    assert 'id="step-1">1. Prepare Files</span>' in INDEX
    assert 'id="step-2">2. Process Pages</span>' in INDEX
    assert 'id="step-3">3. Prepare Output</span>' in INDEX
    assert "Stream Upload" not in INDEX
    assert "Stream Optimization" not in INDEX


def test_secondary_buttons_and_conversion_options_contract():
    assert ".btn-secondary-action" in STYLES
    assert "body.dark-mode .btn-demo-upgrade" in STYLES
    assert "powerpoint_to_pdf" in APP
    assert "Export Resolution" in APP
    assert "PDF/A Conformance" in APP


def test_ai_chat_contrast_and_modal_control_contract():
    assert ".chat-bubble.user" in STYLES
    assert "background: var(--accent) !important" in STYLES
    assert "color: #ffffff !important" in STYLES
    assert ".ai-chat-input" in STYLES
    assert "background: var(--bg-panel-alt) !important" in STYLES
    assert ".ai-chat-input::placeholder" in STYLES
    assert ".modal-header-icon" in STYLES
    assert ".btn-cancel" in STYLES
    assert ".modal-close" in STYLES
    assert "<span>Form</span>" not in INDEX
    assert "<span>Draw</span>" not in INDEX
    assert 'style="font-size: 20px;">Resize</span>' not in INDEX
    assert 'style="font-size: 20px;">Import</span>' not in INDEX
    assert 'style="font-size: 20px;">Optimize</span>' not in INDEX
    assert 'style="font-size: 20px;">Repair</span>' not in INDEX
    assert INDEX.count('class="modal-header-icon"') >= 7
    assert INDEX.count('class="modal-close"') >= 12


def test_active_file_resolution_chain_contract():
    security_forms = (ROOT / "web" / "assets" / "security_forms.js").read_text(encoding="utf-8")
    assert "window.PaperplaneEditor && window.PaperplaneEditor.editorState?.sourceFile" in security_forms
    assert "|| this.currentFile" in security_forms
    assert "|| (window.state && window.state.files && window.state.files[0])" in security_forms


def test_cashfree_checkout_contract():
    assert 'https://sdk.cashfree.com/js/v3/cashfree.js' not in INDEX
    assert "loadExternalSdk('https://sdk.cashfree.com/js/v3/cashfree.js'" in APP
    for tier in ("exam", "student", "cybercafe"):
        assert f'id="{tier}-cashfree-checkout-btn"' in INDEX
    assert 'id="pro-cashfree-checkout-btn"' not in INDEX
    assert 'id="dev-cashfree-checkout-btn"' not in INDEX
    assert 'id="pro-stripe-checkout-btn"' not in INDEX
    assert 'id="dev-stripe-checkout-btn"' not in INDEX
    assert 'window.Cashfree' in APP
    assert 'paymentSessionId: res.payment_session_id' in APP
    assert 'redirectTarget: \'_self\'' in APP
    assert 'handleCashfreeReturn' in APP
    assert "Checkout cancelled or payment not completed. No plan change was made." in APP
    assert "!['return', 'success'].includes(billingReturn)" in APP
    assert '₹250' not in INDEX
    assert '₹750' not in INDEX
    assert 'Netbanking' in INDEX


def test_email_otp_and_confirm_password_frontend_contract():
    assert 'id="auth-confirm-password"' in INDEX
    assert 'id="confirm-password-toggle-btn"' in INDEX
    assert 'id="auth-otp-pane"' in INDEX
    assert 'id="auth-otp-code"' in INDEX
    assert 'id="btn-resend-otp"' in INDEX
    assert 'id="auth-otp-back-btn"' in INDEX
    assert 'startOtpCountdown' in APP
    assert 'showOtpView' in APP
    assert '/api/auth/verify-signup-otp' in APP
    assert '/api/auth/verify-login-otp' in APP
    assert '/api/auth/resend-otp' in APP
    assert '.auth-otp-input' in STYLES
    # Verify OTP is strictly never prefilled in UI
    assert "$('#auth-otp-code').value = '';" in APP
    assert "devOtp ||" not in APP


def test_google_social_auth_frontend_contract():
    assert 'id="google-auth-btn"' in INDEX
    assert 'class="btn-google-social"' in INDEX
    assert 'Continue with Google' in INDEX
    assert '.btn-google-social' in STYLES
    assert 'googleAuthConfig' in APP
    assert 'initGoogleAuth' in APP
    assert 'google-gis-fallback' not in INDEX


def test_waitlist_input_styling_and_no_clipping_contract():
    assert 'class="editor-select waitlist-select"' in INDEX
    assert 'class="editor-input waitlist-email-input"' in INDEX
    assert '.waitlist-select' in STYLES
    assert '.waitlist-email-input' in STYLES
    assert 'height: 44px !important' in STYLES
    assert 'min-height: 44px !important' in STYLES
    assert 'line-height: 1.6' in STYLES


def test_ai_workspace_scroll_compress_options_and_auth_hydration_contracts():
    assert "#app-shell.ai-active .main-area" in STYLES
    assert "overflow-y: auto !important;" in STYLES
    assert "#app-shell.ai-active .app-global-footer" in STYLES
    assert ".option-field select {\n  white-space: nowrap;" in STYLES
    assert "function syncCompressCustomFields()" not in APP  # scoped inside renderOptions
    assert "syncCompressCustomFields();" in APP
    assert "if (qualityField) qualityField.hidden = !isCustom;" in APP
    assert "Promise.allSettled([" in APP
    assert ".auth-pending #user-avatar, .auth-restoring #user-avatar { visibility: hidden; }" in STYLES

