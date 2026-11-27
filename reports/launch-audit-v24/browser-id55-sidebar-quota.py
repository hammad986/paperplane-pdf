"""Measure guest quota box sizing in Chrome around the tablet breakpoint."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/"browser-id55-sidebar-quota.json"
with TemporaryDirectory(prefix="paperplane-v24-id55-") as temp:
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
        else: raise RuntimeError("local app failed to start")
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True)
            page=browser.new_page(viewport={"width":1104,"height":900})
            page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
            page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
            page.goto(f"http://127.0.0.1:{port}/",wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            for width in (1104,1024,901,900,820,390):
                page.set_viewport_size({"width":width,"height":900}); page.wait_for_timeout(120)
                metrics=page.evaluate("""() => { const q=document.querySelector('#quota-container'), row=q?.querySelector('.quota-label-row'), children=[...row.children], r=e=>{const x=e.getBoundingClientRect();return {x:x.x,right:x.right,width:x.width,height:x.height,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,text:e.innerText,whiteSpace:getComputedStyle(e).whiteSpace}};return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,sidebar:r(document.querySelector('.sidebar')),container:r(q),row:r(row),children:children.map(r),quotaText:document.querySelector('#quota-text')?.innerText}; }""")
                evidence["widths"].append(metrics)
                page.screenshot(path=str(OUT.parent/f"id55-quota-{width}.png"))
                if width in (901,1024,1104,1180):
                    paid=page.evaluate("""() => {const q=document.querySelector('#quota-text'); q.textContent='No daily operation cap'; const row=q.closest('.quota-label-row'); const label=row.children[0],r=e=>{const b=e.getBoundingClientRect();return {left:b.left,right:b.right,width:b.width,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,height:b.height,text:e.innerText,whiteSpace:getComputedStyle(e).whiteSpace}};return {viewport:innerWidth,row:r(row),label:r(label),quota:r(q),rowScrollWidth:row.scrollWidth,rowClientWidth:row.clientWidth,overlap:label.getBoundingClientRect().right>q.getBoundingClientRect().left};}""")
                    evidence.setdefault("paid_text_simulation",[]).append(paid)
                    page.screenshot(path=str(OUT.parent/f"id55-quota-paid-{width}.png"))
                    assert not paid["overlap"] and paid["quota"]["scrollWidth"] <= paid["quota"]["clientWidth"] + 1, paid
            evidence["result"]="passed"; browser.close()
    finally:
        app.terminate()
        try: app.wait(timeout=5)
        except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
OUT.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
print(json.dumps(evidence,indent=2))
