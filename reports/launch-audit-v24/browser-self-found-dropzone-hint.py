"""Check upload controls and size guidance don't collide at common widths."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/"browser-self-found-dropzone-hint.json"
with TemporaryDirectory(prefix="paperplane-self-dropzone-") as temp:
    data=Path(temp)/"data"; data.mkdir()
    with socket.socket() as sock: sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
    env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PYTHONPATH":str(ROOT)})
    app=subprocess.Popen([sys.executable,"app.py"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    evidence={"widths":[],"page_errors":[],"console_errors":[]}
    try:
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=.2): break
            except OSError: time.sleep(.2)
        else: raise RuntimeError("local server failed to start")
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True)
            page=browser.new_page(viewport={"width":1366,"height":900})
            page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
            page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
            for route in ("/pdf-to-word", "/summarize-pdf", "/mask-aadhaar-card-online"):
                page.goto(f"http://127.0.0.1:{port}{route}",wait_until="domcontentloaded")
                for width in (320,390,600,820,900,1104,1366):
                    page.set_viewport_size({"width":width,"height":900}); page.wait_for_timeout(100)
                    metrics=page.evaluate("""() => { const d=document.querySelector('#dropzone'), o=d?.querySelector('.dropzone-options'), h=d?.querySelector('#file-hint'),q=document.querySelector('#file-list');const r=e=>{if(!e)return null;const b=e.getBoundingClientRect();return {left:b.left,right:b.right,top:b.top,bottom:b.bottom,width:b.width,height:b.height,display:getComputedStyle(e).display,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,text:e.innerText.trim(),background:getComputedStyle(e).backgroundColor}};const a=r(o),b=r(h);return {route:location.pathname,viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,options:a,hint:b,emptyQueue:r(q),overlap:!!(a&&b&&a.bottom>b.top+1),hintClipped:!!(b&&b.scrollWidth>b.clientWidth+1)}; }""")
                    evidence["widths"].append(metrics)
                    if width in (390,1104,1366): page.screenshot(path=str(OUT.parent/f"self-dropzone-{route.strip('/').replace('-', '_')}-{width}.png"))
                    assert not metrics["overlap"] and not metrics["hintClipped"],metrics
                    if metrics["emptyQueue"]:
                        assert metrics["emptyQueue"]["height"] <= 1,metrics["emptyQueue"]
                    assert "Guests up to 50 MB/file" in metrics["hint"]["text"],metrics
                    assert "Merge supports" not in metrics["hint"]["text"] and "500 MB each on paid plans" not in metrics["hint"]["text"],metrics
            evidence["assets"]={"app":page.locator('script[src*="app.js"]').get_attribute("src"),"css":page.locator('link[href*="styles.css"]').get_attribute("href")}
            assert not evidence["page_errors"] and not evidence["console_errors"],evidence
            browser.close()
    finally:
        app.terminate()
        try: app.wait(timeout=5)
        except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
evidence["result"]="passed"
OUT.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
print(json.dumps(evidence,indent=2))
