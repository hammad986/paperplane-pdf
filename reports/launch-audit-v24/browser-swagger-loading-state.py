"""Hold external Swagger assets and verify the page shows a loading state."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent

def main():
    evidence={"loading_visible_before_cdn":False,"blocked_external_requests":[],"page_errors":[],"blocked_asset_console_messages":[],"unexpected_console_errors":[]}
    with TemporaryDirectory(prefix="paperplane-v24-swagger-") as name:
        temp=Path(name); data=temp/"data"; data.mkdir()
        with socket.socket() as s: s.bind(("127.0.0.1",0)); port=s.getsockname()[1]
        env={k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PYTHONPATH":str(ROOT)})
        app=subprocess.Popen([sys.executable,"app.py"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("Local server did not start")
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True); page=browser.new_page(viewport={"width":1280,"height":900})
                page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
                def capture_console(message):
                    if message.type != "error": return
                    if "net::ERR_FAILED" in message.text:
                        evidence["blocked_asset_console_messages"].append(message.text)
                    else:
                        evidence["unexpected_console_errors"].append(message.text)
                page.on("console",capture_console)
                def block_cdn(route):
                    evidence["blocked_external_requests"].append(route.request.url)
                    route.abort()
                page.route("https://cdn.jsdelivr.net/**",block_cdn)
                page.route("https://fastapi.tiangolo.com/**",block_cdn)
                response=page.goto(f"http://127.0.0.1:{port}/spec/swagger",wait_until="domcontentloaded")
                assert response and response.status==200
                loading=page.locator("#swagger-ui-loading")
                loading.wait_for(state="visible",timeout=5000)
                evidence["loading_visible_before_cdn"]=True
                evidence["loading_text"]=loading.inner_text()
                evidence["cache_control"]=response.headers.get("cache-control")
                assert "Loading interactive API documentation" in evidence["loading_text"]
                assert evidence["cache_control"]=="no-store"
                assert evidence["blocked_external_requests"],"Expected at least one third-party Swagger asset to be held"
                assert not evidence["page_errors"],evidence
                assert not evidence["unexpected_console_errors"],evidence
                evidence["result"]="passed"; browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/"browser-swagger-loading-state.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
if __name__=="__main__":main()
