from pathlib import Path
from tempfile import TemporaryDirectory
import json, os, secrets, socket, subprocess, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"
with TemporaryDirectory(prefix="paperplane-id108-prod-docs-") as tmp:
    data_dir = Path(tmp) / "data"
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = candidate.getsockname()[1]
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_", "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_")) and k not in {"TESTING", "SESSION_SECRET_KEY"}}
    env.update({"PAPERPLANE_SKIP_DOTENV": "1", "PAPERPLANE_ENV": "production", "PAPERPLANE_PUBLIC_URL": "https://paperplane.example.test", "PAPERPLANE_SESSION_SECRET": secrets.token_urlsafe(48), "PAPERPLANE_DATA_DIR": str(data_dir), "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(64), "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(30), "PAPERPLANE_PORT": str(port), "PAPERPLANE_SECURE_COOKIES": "false", "CASHFREE_ENV": "PROD", "TESTING": "True", "PYTHONPATH": str(ROOT)})
    app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1365, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            for path in ("/docs", "/api-docs", "/redoc", "/openapi.json", "/spec/swagger", "/spec/redoc", "/spec/openapi.json"):
                response = page.goto(f"http://127.0.0.1:{port}{path}", wait_until="domcontentloaded")
                results.append({"path": path, "status": response.status if response else None, "final_path": page.url.split(str(port),1)[-1]})
            status = {row["path"]: row["status"] for row in results}
            assert status["/openapi.json"] == 404, status
            assert status["/docs"] == status["/api-docs"] == status["/redoc"] == 200, status
            assert status["/spec/swagger"] == status["/spec/redoc"] == status["/spec/openapi.json"] == 200, status
            assert not errors, errors
            browser.close()
        (OUT / "browser-id108-production-docs.json").write_text(json.dumps({"environment": "production", "routes": results, "page_errors": errors, "interpretation": "FastAPI built-in /openapi.json is disabled; legacy docs aliases redirect to the intentionally public curated developer reference (/spec/*)."}, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
