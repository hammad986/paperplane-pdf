"""Use a controlled server clock to browser-check the four-hour admin session TTL."""
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"reports"/"launch-audit-v24"
with TemporaryDirectory(prefix="paperplane-id103-") as tmp:
    temp=Path(tmp);data=temp/"data";clock_file=temp/"clock-offset.txt";clock_file.write_text("0",encoding="ascii")
    with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
    env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PYTHONPATH":str(ROOT),"PYTHONIOENCODING":"utf-8","PAPERPLANE_AUDIT_CLOCK_FILE":str(clock_file)})
    seed="import json; from persistence import init_db,create_admin_session; from server import PRIMARY_ADMIN_EMAIL; init_db(); print(json.dumps({'token':create_admin_session(PRIMARY_ADMIN_EMAIL)}))"
    identity=json.loads(subprocess.run([sys.executable,"-c",seed],cwd=ROOT,env=env,capture_output=True,text=True,check=True,timeout=30).stdout)
    runner=("import os,time,uvicorn,persistence,server; real_time=time.time; clock_file=os.environ['PAPERPLANE_AUDIT_CLOCK_FILE']; "
            "persistence.time=type('ControlledTime',(),{'time':staticmethod(lambda:real_time()+float(open(clock_file,encoding='ascii').read()))})(); "
            "uvicorn.run(server.app,host='127.0.0.1',port=int(os.environ['PAPERPLANE_PORT']),log_level='error')")
    app=subprocess.Popen([sys.executable,"-c",runner],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=.2):break
            except OSError:time.sleep(.2)
        base=f"http://127.0.0.1:{port}"
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True);page=browser.new_page(viewport={"width":1366,"height":900});responses=[];errors=[]
            page.add_init_script(f"sessionStorage.setItem('pp_admin_session',{json.dumps(identity['token'])})")
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.on("response",lambda response:responses.append({"url":response.url,"status":response.status}) if "/api/admin/dashboard" in response.url else None)
            response=page.goto(base+"/admin",wait_until="domcontentloaded");assert response and response.status==200
            page.wait_for_function("document.querySelector('#dashboard-view')?.style.display==='block'",timeout=10000)
            initial=next((item["status"] for item in reversed(responses) if item["status"] in (200,401)),None)
            assert initial==200,responses
            clock_file.write_text(str(75*60),encoding="ascii")
            after_75_start=len(responses)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function("document.querySelector('#dashboard-view')?.style.display==='block'",timeout=10000)
            after_75=next((item["status"] for item in responses[after_75_start:] if item["status"] in (200,401)),None)
            assert after_75==200,responses[after_75_start:]
            clock_file.write_text(str(4*60*60),encoding="ascii")
            expiry_start=len(responses)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function("document.querySelector('#step1-screen')?.style.display!=='none'",timeout=10000)
            expired=next((item["status"] for item in responses[expiry_start:] if item["status"] in (200,401)),None)
            assert expired==401,responses[expiry_start:]
            assert not errors,errors
            evidence={"initial_dashboard_status":initial,"dashboard_after_simulated_75_minutes":after_75,"dashboard_at_four_hour_expiry":expired,"controlled_clock_offsets_seconds":[0,75*60,4*60*60],"page_errors":errors,"production_endpoints_contacted":False,"result":"passed"}
            (OUT/"browser-id103-admin-session-75min.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
            print(json.dumps(evidence,indent=2));browser.close()
    finally:
        app.terminate()
        try:app.wait(timeout=5)
        except subprocess.TimeoutExpired:app.kill();app.wait(timeout=5)
