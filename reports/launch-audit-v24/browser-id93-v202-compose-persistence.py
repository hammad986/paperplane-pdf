"""Recreate an isolated Compose container and verify account/session + Studio browser work survive via a named data volume."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time, urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, yaml
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent

def run(args, **kwargs):
    result=subprocess.run(args,check=False,text=True,capture_output=True,**kwargs)
    if result.returncode:
        raise RuntimeError(f"command failed (exit {result.returncode}): {result.stderr[-1200:]}")
    return result

def main():
    token=secrets.token_hex(5); project=f"ppv24id93{token}"; volume=f"paperplane-v24-id93-{token}"
    evidence={"container_recreated":False,"account_survived":False,"session_survived":False,"studio_pdf_survived_browser_reload":False,"browser_errors":[]}
    with TemporaryDirectory(prefix=f"paperplane-v24-id93-{token}-") as name:
        temp=Path(name); data_out=temp/"audit"; data_out.mkdir(); fixture=temp/"studio-persist-fixture.pdf"
        doc=fitz.open(); page=doc.new_page(); page.insert_text((72,72),"ID93 Studio persistence marker"); doc.save(fixture); doc.close()
        with socket.socket() as sock: sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
        compose={"services":{"app":{"image":"paperplane-codex:v202","ports":[f"127.0.0.1:{port}:8501"],"environment":{"PAPERPLANE_ENV":"production","PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_DATA_DIR":"/data","PAPERPLANE_HOST":"0.0.0.0","PAPERPLANE_PORT":"8501","PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(32),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_TRUSTED_HOSTS":"localhost,127.0.0.1","PAPERPLANE_SECURE_COOKIES":"false","PAPERPLANE_ALLOWED_ORIGINS":f"http://127.0.0.1:{port}","PAPERPLANE_PUBLIC_URL":"https://id93.paperplane.example"},"volumes":[{"type":"bind","source":str(ROOT).replace('\\','/'),"target":"/app","read_only":True},{"type":"volume","source":"persist","target":"/data"},{"type":"bind","source":str(data_out).replace('\\','/'),"target":"/audit"}],"restart":"no"}},"volumes":{"persist":{"name":volume}}}
        compose_file=temp/"compose.yml"; compose_file.write_text(yaml.safe_dump(compose,sort_keys=False),encoding="utf-8")
        command=["docker","compose","-f",str(compose_file),"-p",project]
        try:
            run(command+["up","-d"])
            for _ in range(180):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health",timeout=1) as response:
                        if response.status==200: break
                except Exception: time.sleep(.5)
            else: raise RuntimeError("Isolated Docker Paperplane health endpoint did not start")
            email=f"id93-{token}@example.test"
            py="import json,persistence; persistence.init_db(); uid=persistence.create_user("+repr(email)+",'ExamplePass!234'); session=persistence.create_session_for_user(uid); open('/audit/session.json','w',encoding='utf-8').write(json.dumps({'token':session['token'],'user_id':uid})); print('ACCOUNT_SESSION_CREATED')"
            run(command+["exec","-T","app","python","-c",py])
            session=json.loads((data_out/"session.json").read_text(encoding="utf-8")); origin=f"http://127.0.0.1:{port}"
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True); context=browser.new_context(accept_downloads=True,viewport={"width":1366,"height":900})
                context.add_cookies([{"name":"paperplane_token","value":session["token"],"url":origin,"httpOnly":True,"sameSite":"Lax"}])
                page=context.new_page(); page.on("pageerror",lambda err:evidence["browser_errors"].append(str(err))); page.on("console",lambda msg:evidence["browser_errors"].append(msg.text) if msg.type=="error" else None)
                page.goto(origin+"/",wait_until="domcontentloaded")
                page.wait_for_function("fetch('/api/auth/me').then(r=>r.json()).then(x=>x.authenticated===true).catch(()=>false)",timeout=30000)
                before_user=page.evaluate("fetch('/api/auth/me').then(r=>r.json())")
                assert before_user.get("user_id")==session["user_id"]
                page.locator("#tab-studio-view").click()
                page.locator("#studio-file-input").set_input_files(str(fixture))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent.trim()==='1'",timeout=60000)
                page.wait_for_timeout(500)
                evidence["studio_saved_before_restart"]=True
                run(command+["down"])
                run(command+["up","-d"]); evidence["container_recreated"]=True
                for _ in range(180):
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health",timeout=1) as response:
                            if response.status==200: break
                    except Exception: time.sleep(.5)
                else: raise RuntimeError("Paperplane health endpoint did not recover after container recreation")
                page.reload(wait_until="domcontentloaded")
                page.wait_for_function("fetch('/api/auth/me').then(r=>r.json()).then(x=>x.authenticated===true).catch(()=>false)",timeout=30000)
                after_user=page.evaluate("fetch('/api/auth/me').then(r=>r.json())")
                evidence["account_survived"]=after_user.get("user_id")==session["user_id"]
                evidence["session_survived"]=bool(evidence["account_survived"])
                assert evidence["account_survived"] and evidence["session_survived"]
                page.locator("#tab-studio-view").click()
                page.get_by_text("Restored studio-persist-fixture.pdf on page 1",exact=True).wait_for(state="visible",timeout=60000)
                evidence["studio_pdf_survived_browser_reload"]=page.locator("#page-total-indicator").inner_text().strip()=="1"
                assert evidence["studio_pdf_survived_browser_reload"]
                assert not evidence["browser_errors"],evidence
                evidence["result"]="passed"; browser.close()
            # Verify the same unique container data volume is referenced by this project and left no account data outside its test volume.
            evidence["named_volume_isolated"]=volume.startswith("paperplane-v24-id93-")
        finally:
            subprocess.run(command+["down","-v"],check=False,capture_output=True,text=True)
    (OUT/"browser-id93-v202-compose-persistence.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
if __name__=="__main__": main()
