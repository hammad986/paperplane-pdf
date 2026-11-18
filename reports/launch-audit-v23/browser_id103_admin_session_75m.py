from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id103-') as temp:
    app,base,identity=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for number in (1,2):
                context=browser.new_context(viewport={'width':1440,'height':960})
                token=identity['admin']
                context.add_init_script(f"sessionStorage.setItem('pp_admin_session',{json.dumps(token)})")
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                response=page.goto(base+'/admin',wait_until='domcontentloaded');assert response.status==200
                page.locator('#dashboard-view').wait_for(state='visible',timeout=15000)
                before=page.locator('#dashboard-view').is_visible()
                result=page.evaluate("""async()=>{const realNow=Date.now;const later=realNow()+75*60*1000;Date.now=()=>later;try{const r=await fetch('/api/admin/dashboard',{headers:{'X-Admin-Session':sessionStorage.getItem('pp_admin_session')}});return {status:r.status,body:await r.json()}}finally{Date.now=realNow}}""")
                assert result['status']==200,result
                assert page.locator('#dashboard-view').is_visible() and before
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id103-admin-session-round{number}.png'),full_page=True)
                rounds.append({'round':number,'admin_loaded':True,'browser_clock_advanced_minutes':75,'protected_dashboard_status':result['status'],'session_still_in_dashboard':True,'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':rounds,'limit':'browser clock is advanced; server clock remains real, so this checks the client does not expire the session at 75 minutes, not a live elapsed-time session test'}
        (OUT/'browser-id103-admin-session-75m.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
