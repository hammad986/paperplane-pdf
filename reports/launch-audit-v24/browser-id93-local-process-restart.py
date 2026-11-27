"""Check that local account state and browser-saved Studio work survive app restart."""
import json,socket,sys,time,subprocess,os,secrets
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
def start_server(data,port):
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
    env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(64),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(30),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PYTHONPATH":str(ROOT)})
    seed="""import json,secrets
from persistence import init_db,create_user,create_session,create_admin_session,set_user_tier
from server import PRIMARY_ADMIN_EMAIL
init_db(); accounts=[]
for tier in ('student_pro','free'):
 email=f'audit-{secrets.token_hex(4)}@example.invalid'; password=secrets.token_urlsafe(24)
 user_id=create_user(email,password);set_user_tier(user_id,tier);accounts.append((email,create_session(email,password)['token']))
print(json.dumps({'accounts':accounts,'admin':create_admin_session(PRIMARY_ADMIN_EMAIL)}))"""
    seeded=subprocess.run([sys.executable,"-c",seed],cwd=ROOT,env=env,text=True,capture_output=True,check=True)
    proc=subprocess.Popen([sys.executable,"app.py"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return proc,f"http://127.0.0.1:{port}",json.loads(seeded.stdout)
with TemporaryDirectory(prefix="paperplane-id93-restart-") as td:
    root=Path(td);data=root/"persistent-local-data";fixture=root/"restart-studio.pdf"
    with fitz.open() as d:
        page=d.new_page();page.insert_text((72,72),"ID93 RESTART SURVIVAL MARKER")
        page.set_rotation(0);d.save(fixture)
    with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    app,base,identity=start_server(data,port)
    def wait_ready(process):
        for _ in range(150):
            if process.poll() is not None: raise RuntimeError(f"app exited {process.returncode}")
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=.2):return
            except OSError:time.sleep(.1)
        raise RuntimeError("app did not become ready")
    try:
        wait_ready(app)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True);context=browser.new_context(viewport={"width":1366,"height":900})
            context.add_cookies([{"name":"paperplane_token","value":identity["accounts"][1][1],"url":base,"httpOnly":True}])
            page=context.new_page();errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(base+"/studio",wait_until="domcontentloaded")
            page.wait_for_function("!document.body.classList.contains('auth-pending')",timeout=15000)
            page.locator("#studio-file-input").set_input_files(str(fixture))
            page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=30000)
            before=page.evaluate("""async()=>{const db=await new Promise((r,j)=>{const q=indexedDB.open('paperplane-local-work');q.onsuccess=()=>r(q.result);q.onerror=()=>j(q.error)});const values=await new Promise((r,j)=>{const q=db.transaction('work').objectStore('work').getAllKeys();q.onsuccess=()=>r(q.result);q.onerror=()=>j(q.error)});db.close();return {userId:state.user?.user_id,filename:state.studio.srcFile?.name,pages:state.studio.totalCount,canvas:document.querySelector('#pdf-canvas')?.dataset.rendered==='true',studioKey:values.some(k=>String(k).endsWith(':studio-pdf'))}}""")
            assert before["userId"] and before["filename"]==fixture.name and before["pages"]==1 and before["canvas"] and before["studioKey"],before
            app.terminate();app.wait(timeout=8)
            app,base2,second_identity=start_server(data,port);assert base2==base
            wait_ready(app)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function("!document.body.classList.contains('auth-pending')",timeout=15000)
            page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=30000)
            after=page.evaluate("""async()=>{const p=await state.studio.pdfDoc.getPage(1);const t=await p.getTextContent();return {userId:state.user?.user_id,filename:state.studio.srcFile?.name,pages:state.studio.totalCount,canvas:document.querySelector('#pdf-canvas')?.dataset.rendered==='true',pageText:t.items.map(i=>i.str).join(' ')}}""")
            assert after["userId"]==before["userId"] and after["filename"]==fixture.name and after["pages"]==1 and after["canvas"] and "ID93 RESTART SURVIVAL MARKER" in after["pageText"],after
            assert not errors,errors
            evidence={"local_same_data_directory_process_restart":True,"original_account_id_survived":True,"studio_pdf_survived_browser_reload_and_server_restart":True,"before_restart":before,"after_restart":after,"page_errors":errors,"result":"passed","limitation":"isolated local restart only; does not prove the deployed host retains or mounts the same persistent volume across redeploy"}
            (OUT/"browser-id93-local-process-restart.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
            print(json.dumps(evidence,indent=2));browser.close()
    finally:
        if app.poll() is None:app.terminate()
        app.wait(timeout=8)
