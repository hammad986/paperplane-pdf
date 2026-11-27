from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib, json, socket, sqlite3, subprocess, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id103-') as temp:
    data_dir=Path(temp)/'data'
    app,base,identity=helper.start_server(data_dir)
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        database=data_dir/'paperplane.sqlite3'
        token=identity['admin']
        token_hash=hashlib.sha256(token.encode()).hexdigest()

        def age_session(created_at):
            expires_at=created_at+4*60*60
            connection=sqlite3.connect(database, timeout=10)
            try:
                changed=connection.execute(
                    'UPDATE admin_sessions SET created_at=?, expires_at=? WHERE token_hash=?',
                    (created_at, expires_at, token_hash),
                ).rowcount
                connection.commit()
            finally:
                connection.close()
            assert changed == 1, 'The synthetic admin session was not found in the isolated database.'
            return expires_at

        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for number in (1,2):
                age_session(time.time()-75*60)
                context=browser.new_context(viewport={'width':1440,'height':960})
                context.add_init_script(f"sessionStorage.setItem('pp_admin_session',{json.dumps(token)})")
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                response=page.goto(base+'/admin',wait_until='domcontentloaded');assert response.status==200
                page.locator('#dashboard-view').wait_for(state='visible',timeout=15000)
                aged_status=page.evaluate("""async()=>{
                  const response=await fetch('/api/admin/dashboard',{headers:{'X-Admin-Session':sessionStorage.getItem('pp_admin_session')}});
                  return response.status;
                }""")
                assert aged_status==200,aged_status
                expires_before=age_session(time.time()-(4*60*60-5))
                boundary_status=page.evaluate("""async()=>{
                  const response=await fetch('/api/admin/dashboard',{headers:{'X-Admin-Session':sessionStorage.getItem('pp_admin_session')}});
                  return response.status;
                }""")
                assert boundary_status==200,{'status':boundary_status,'expires_at':expires_before}
                age_session(time.time()-4*60*60)
                expired_status=page.evaluate("""async()=>{
                  const response=await fetch('/api/admin/dashboard',{headers:{'X-Admin-Session':sessionStorage.getItem('pp_admin_session')}});
                  return response.status;
                }""")
                assert expired_status==401,expired_status
                page.reload(wait_until='domcontentloaded')
                page.locator('#step1-screen').wait_for(state='visible',timeout=15000)
                assert not page.locator('#dashboard-view').is_visible()
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id103-admin-session-round{number}.png'),full_page=True)
                rounds.append({'round':number,'server_session_age_minutes':75,'status_at_75m':aged_status,
                               'status_five_seconds_before_four_hours':boundary_status,
                               'status_at_four_hour_expiry':expired_status,
                               'expired_session_returns_to_admin_login':True,'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':rounds,'method':'The disposable SQLite session row was backdated; API requests used the real backend wall clock and the visible Admin Console.'}
        (OUT/'browser-id103-admin-session-75m.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        if app.poll() is None:
            if sys.platform == 'win32':
                subprocess.run(['taskkill','/PID',str(app.pid),'/T','/F'],capture_output=True,text=True)
            app.terminate()
        try:
            app.wait(timeout=5)
        except Exception:
            if app.poll() is None:
                app.kill();app.wait(timeout=5)
