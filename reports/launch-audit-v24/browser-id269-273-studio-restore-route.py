"""Check Studio latest-document restoration and ensure reload stays on Tool Desk."""
import base64,json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/launch-audit-v24/browser-id269-273-studio-restore-route.json'
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14'));import browser_acceptance_v14 as helper

def makepdf(path,marker):
 with fitz.open() as d:
  p=d.new_page();p.insert_text((72,90),marker);d.save(path)

def main():
 with TemporaryDirectory(prefix='paperplane-269-273-') as td:
  td=Path(td);a=td/'older.pdf';b=td/'current.pdf';makepdf(a,'ID269 OLDER DOCUMENT');makepdf(b,'ID269 CURRENT DOCUMENT')
  ba=base64.b64encode(a.read_bytes()).decode();bb=base64.b64encode(b.read_bytes()).decode()
  app,base,_=helper.start_server(td/'data');ev={'rounds':[],'page_errors':[],'console_errors':[]}
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(120):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2):break
    except OSError:
     if app.poll() is not None:raise RuntimeError('server exited')
     time.sleep(.15)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True)
    for _ in range(2):
     page=browser.new_page(viewport={'width':1366,'height':900});page.set_default_timeout(30000);page.on('pageerror',lambda e:ev['page_errors'].append(str(e)[:200]));page.on('console',lambda m:ev['console_errors'].append(m.text[:200])if m.type=='error'else None)
     page.goto(base+'/tool-desk',wait_until='domcontentloaded')
     for name,contents in (('older.pdf',ba),('current.pdf',bb)):
      loaded=page.evaluate("""async({name,b64})=>{const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));return await loadDocumentIntoStudio(new File([bytes],name,{type:'application/pdf'}))}""",{'name':name,'b64':contents})
      if not loaded:raise AssertionError(f'Could not load {name} into Studio')
      page.wait_for_function('(name)=>state.studio.srcFile?.name===name',arg=name)
     ev['rounds'].append({'before_reload':page.evaluate('state.studio.srcFile?.name'),'route_before_reload':page.url.split(base)[-1]})
     page.goto(base+'/tool-desk',wait_until='domcontentloaded');page.wait_for_timeout(800)
     ev['rounds'][-1]['route_after_reload']=page.url.split(base)[-1]
     ev['rounds'][-1]['active_view_after_reload']=page.evaluate('state.activeView')
     ev['rounds'][-1]['studio_auto_loaded']=page.evaluate('Boolean(state.studio.pdfDoc)')
     page.evaluate("switchWorkspaceView('studio',null,false)")
     page.wait_for_function("state.studio.pdfDoc && state.studio.srcFile?.name==='current.pdf'",timeout=30000)
     ev['rounds'][-1]['restored_file']=page.evaluate('state.studio.srcFile?.name')
     ev['rounds'][-1]['restored_page_count']=page.evaluate('state.studio.totalCount')
     page.close()
    browser.close()
  finally:app.terminate();app.wait(timeout=5)
  ev['overall']='passed' if len(ev['rounds'])==2 and all(r['before_reload']=='current.pdf' and r['route_after_reload']=='/tool-desk' and r['active_view_after_reload']=='tool-desk' and not r['studio_auto_loaded'] and r['restored_file']=='current.pdf' and r['restored_page_count']==1 for r in ev['rounds']) and not ev['page_errors'] and not ev['console_errors'] else 'failed'
  OUT.write_text(json.dumps(ev,indent=2),encoding='utf-8');print(json.dumps(ev,indent=2))
  if ev['overall']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
