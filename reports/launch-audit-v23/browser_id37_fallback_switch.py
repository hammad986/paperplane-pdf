from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
import fitz
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(root/'reports/launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-fallback-switch-fixtures-') as fixtures, TemporaryDirectory(prefix='paperplane-fallback-switch-data-') as data:
 d=Path(fixtures); source=d/'one.pdf'; second=d/'two.pdf'
 for path in (source,second):
  with fitz.open() as pdf:
   pdf.new_page().insert_text((72,72),'TEST'); pdf.save(path)
 app,base,_=helper.start_server(Path(data))
 try:
  for _ in range(600):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2): break
   except OSError: time.sleep(.2)
  results=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for rnd in (1,2):
    context=browser.new_context(); page=context.new_page(); errors=[]; posts=[]
    page.on('pageerror',lambda e:errors.append(str(e))); context.on('request',lambda r:posts.append(r.url) if r.method=='POST' and r.url.endswith('/api/jobs') else None)
    page.goto(base+'/merge-pdf',wait_until='domcontentloaded',timeout=60000); page.locator('#file-input').set_input_files([str(source),str(second)])
    page.evaluate("""() => { const runtime=window.PaperplanePdfRuntime; Object.defineProperty(window,'PaperplanePdfRuntime',{configurable:true,value:{...runtime,transformLocalPdf:async()=>{throw new Error('controlled failure')}}}); window.__submitted=false; submitJobWithUploadProgress=async()=>{window.__submitted=true; return await new Promise(()=>{});}; }""")
    page.locator('#run-button').click(); dialog=page.locator('dialog.app-confirm-dialog'); dialog.wait_for(state='visible',timeout=30000); dialog.locator('.app-confirm-accept').click(); page.wait_for_function('window.__submitted === true',timeout=30000)
    assert page.evaluate('state.serverFallbackForCurrentRun && !state.clientSideMode')
    page.evaluate("selectOperation('rotate')")
    assert page.locator('#client-privacy-toggle').is_checked()
    assert page.evaluate('!state.serverFallbackForCurrentRun && state.clientSideMode')
    assert not posts and not errors,(posts,errors)
    results.append({'round':rnd,'pending_fallback_interrupted':True,'new_tool_browser_mode':True,'unexpected_job_posts':len(posts),'page_errors':errors}); context.close()
   browser.close()
  report={'result':'PASS','rounds':results}; (root/'reports/launch-audit-v23/browser-id37-fallback-switch.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report))
 finally:
  app.terminate()
  try: app.wait(timeout=15)
  except Exception: app.kill()
