"""Check the temporary-upload navigation/reload notice on a live SPA route."""
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/launch-audit-v24/browser-id272-upload-warning-navigation.json'
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14'));import browser_acceptance_v14 as helper

def main():
 with TemporaryDirectory(prefix='paperplane-id272-') as td:
  td=Path(td);src=td/'temporary.pdf'
  with fitz.open() as d:p=d.new_page();p.insert_text((72,90),'ID272 temporary upload');d.save(src)
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
     page=browser.new_page(viewport={'width':1366,'height':900});page.on('pageerror',lambda e:ev['page_errors'].append(str(e)[:200]));page.on('console',lambda m:ev['console_errors'].append(m.text[:200])if m.type=='error'else None)
     page.goto(base+'/merge-pdf',wait_until='domcontentloaded');page.locator('#file-input').set_input_files(str(src));page.wait_for_function('state.files?.length===1')
     row={'selected_before_navigation':page.evaluate('state.files.map(f=>f.name)')}
     page.evaluate("switchWorkspaceView('tool-desk')");page.wait_for_timeout(100)
     row['desk_toast']=page.locator('.toast-notice').inner_text() if page.locator('.toast-notice').count() else ''
     page.evaluate("selectOperation('merge')");page.wait_for_timeout(100)
     row['return_to_tool_toast']=page.locator('.toast-notice').inner_text() if page.locator('.toast-notice').count() else ''
     row['selected_after_spa_return']=page.evaluate('state.files.map(f=>f.name)')
     page.reload(wait_until='domcontentloaded');page.wait_for_timeout(250)
     row['selected_after_reload']=page.evaluate('state.files.map(f=>f.name)')
     row['reload_toast']=page.locator('.toast-notice').inner_text() if page.locator('.toast-notice').count() else ''
     ev['rounds'].append(row);page.close()
    browser.close()
  finally:app.terminate();app.wait(timeout=5)
  warning='some temporary tool uploads may need to be selected again after reload'
  ev['overall']='passed' if len(ev['rounds'])==2 and all(r['selected_before_navigation']==['temporary.pdf'] and warning not in (r['desk_toast']+r['return_to_tool_toast']+r['reload_toast']).lower() and not r['reload_toast'] and r['selected_after_reload']==[] for r in ev['rounds']) and not ev['page_errors'] and not ev['console_errors'] else 'failed'
  OUT.write_text(json.dumps(ev,indent=2),encoding='utf-8');print(json.dumps(ev,indent=2))
  if ev['overall']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
