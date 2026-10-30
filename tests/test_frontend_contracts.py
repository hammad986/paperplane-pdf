from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "web" / "assets" / "styles.css").read_text(encoding="utf-8")


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
    assert "/api/ai/chat" in APP
    assert "/api/ai/summarize" in APP
    assert "/api/ai/extract" in APP
    assert "/api/ai/translate" in APP
    assert "Open in Full AI Interactive Studio" in APP
    assert "Download PDF" in INDEX


def test_form_control_contrast_contract():
    assert "select option" in STYLES
    assert "color: #142023 !important" in STYLES
    assert "body.dark-mode select option" in STYLES
    assert ".option-field input::placeholder" in STYLES
    assert "o.style.display = fields ? '' : 'none'" in APP


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
    assert 'https://sdk.cashfree.com/js/v3/cashfree.js' in INDEX
    assert 'id="pro-cashfree-checkout-btn"' in INDEX
    assert 'id="dev-cashfree-checkout-btn"' in INDEX
    assert 'id="pro-stripe-checkout-btn"' not in INDEX
    assert 'id="dev-stripe-checkout-btn"' not in INDEX
    assert 'window.Cashfree' in APP
    assert 'paymentSessionId: res.payment_session_id' in APP
    assert 'redirectTarget: \'_self\'' in APP
    assert 'handleCashfreeReturn' in APP
    assert '₹250' in INDEX
    assert '₹750' in INDEX
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


