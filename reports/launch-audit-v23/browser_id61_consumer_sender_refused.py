from pathlib import Path
from tempfile import TemporaryDirectory
import json, os, secrets, socket, subprocess, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

with TemporaryDirectory(prefix="paperplane-id61-mail-") as temp:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = candidate.getsockname()[1]
    env = {
        name: value for name, value in os.environ.items()
        if not name.upper().startswith(("PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_", "AI_", "ADMIN_"))
        and name not in {"TESTING", "SESSION_SECRET_KEY"}
    }
    env.update(
        PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development",
        PAPERPLANE_DATA_DIR=temp, PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(48),
        PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(24), PAPERPLANE_PORT=str(port),
        PAPERPLANE_SECURE_COOKIES="false", SMTP_ENABLED="true",
        SMTP_HOST="smtp.invalid.test", SMTP_FROM_EMAIL="owner@gmail.com",
        SMTP_USER="owner@gmail.com", SMTP_PASSWORD="synthetic-password",
        RESEND_API_KEY="re_synthetic_key", PYTHONPATH=str(ROOT),
    )
    base = f"http://127.0.0.1:{port}"
    app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        else:
            raise RuntimeError("local app did not start")

        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                page = browser.new_page(viewport={"width": 390, "height": 844})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                email = f"id61-{round_no}-{secrets.token_hex(4)}@example.invalid"
                page.goto(base + "/", wait_until="domcontentloaded")
                page.evaluate("window.openAuthModal('', 'register')")
                page.locator("#auth-email").fill(email)
                page.locator("#auth-password").fill("TestingPassword!234")
                page.locator("#auth-confirm-password").fill("TestingPassword!234")
                with page.expect_response(lambda response: response.url.endswith("/api/auth/register")) as event:
                    page.locator("#auth-submit-btn").click()
                response = event.value
                payload = response.json()
                assert response.status == 503, (response.status, payload)
                assert "email delivery is unavailable" in payload.get("detail", "").lower(), payload
                assert page.locator("#auth-otp-pane").is_hidden()
                state = page.evaluate("""() => ({
                    token: localStorage.getItem('paperplane_token'),
                    authCookie: document.cookie.split(';').some(x => x.trim().startsWith('paperplane_token=')),
                    message: document.querySelector('#auth-message')?.textContent || ''
                })""")
                assert state["token"] is None and not state["authCookie"], state
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id61-consumer-sender-round{round_no}.png"))
                rounds.append({"round": round_no, "status": response.status,
                               "detail": payload["detail"], "auth_state": state,
                               "no_otp_pane": True, "page_errors": errors})
                page.close()
            browser.close()
        result = {"scenario": "Gmail From configured with SMTP and Resend credentials; registration must fail closed before dispatch",
                  "rounds": rounds}
        (OUT / "browser-id61-consumer-sender-refused.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        try:
            app.wait(timeout=5)
        except subprocess.TimeoutExpired:
            app.kill()
            app.wait(timeout=5)
