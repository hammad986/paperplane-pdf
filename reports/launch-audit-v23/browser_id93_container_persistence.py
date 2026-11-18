"""Verify a local Compose-style container replacement keeps account data and login working."""
from pathlib import Path
import json
import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18501"
OUT = Path(__file__).resolve().parent
email = "audit-persist@example.com"
password = "Dummy-Password-Only-2026!"
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1366, "height": 900})
    page = context.new_page()
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    for _ in range(30):
        try:
            health = page.request.get(BASE + "/api/health", timeout=3000)
            if health.status == 200:
                break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("replacement container did not become healthy")
    home = page.goto(BASE + "/", wait_until="domcontentloaded")
    assert home and home.status == 200
    login_response = page.request.post(
        BASE + "/api/auth/login",
        data={"email": email, "password": password},
        headers={"content-type": "application/json"},
    )
    assert login_response.status == 200, login_response.text()
    login_payload = login_response.json()
    assert login_payload.get("status") in {"authenticated", "success"}, login_payload
    me_response = page.request.get(BASE + "/api/auth/me")
    assert me_response.status == 200, me_response.text()
    me = me_response.json()
    assert me.get("email") == email and me.get("authenticated") is True, me
    assert not page_errors, page_errors
    evidence = {
        "replacement_container": True,
        "health": health.json(),
        "home_http_status": home.status,
        "login_http_status": login_response.status,
        "login_status": login_payload.get("status"),
        "authenticated_email_after_replacement": me.get("email"),
        "http_only_session_cookie": any(c["name"] == "paperplane_token" and c["httpOnly"] for c in context.cookies()),
        "page_errors": page_errors,
    }
    assert evidence["http_only_session_cookie"]
    (OUT / "browser-id93-container-persistence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    browser.close()
