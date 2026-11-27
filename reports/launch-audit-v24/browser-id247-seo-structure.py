import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
ROUTES=['/privacy','/terms','/developers','/apps','/download','/compress-pdf-to-100kb','/compress-pdf-to-200kb','/convert-pdf','/pdf-security','/reset-password']
def main():
 errors=[]; pages=[]
 with TemporaryDirectory(prefix='paperplane-id247-') as td:
  app,base,_=helper.start_server(Path(td)/'data')
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(150):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError: time.sleep(.2)
   else: raise RuntimeError('local server did not start')
   with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page()
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
    for route in ROUTES:
     resp=page.goto(base+route,wait_until='domcontentloaded')
     h1=page.locator('h1:visible').all_inner_texts()
     title=page.title()
     pages.append({'path':route,'status':resp.status,'title':title,'h1':h1,'body_text':(page.locator('#view-download').inner_text() if route in ('/apps','/download') else page.locator('body').inner_text())[:1200], 'reset_form_visible':page.locator('#reset-password-modal').is_visible() and page.locator('#reset-new-password').is_visible() if route=='/reset-password' else None})
    transitions=[]
    for width in (390,1366):
     page.set_viewport_size({'width':width,'height':900})
     page.goto(base+'/apps',wait_until='domcontentloaded')
     page.wait_for_function("!document.querySelector('#apps-waitlist-content').hidden && document.querySelector('#web-download-content').hidden")
     page.evaluate("switchWorkspaceView('download')")
     page.wait_for_url('**/download')
     transitions.append({'width':width,'from_apps_to_download':page.locator('#web-download-content').is_visible() and page.locator('#download-view-heading').inner_text()=='Downloads','title':page.title(),'overflow':page.evaluate('document.documentElement.scrollWidth>innerWidth')})
     page.locator('#web-download-content a[href=\"/apps\"]').click()
     page.wait_for_url('**/apps')
     transitions[-1]['back_to_apps_waitlist']=page.locator('#apps-waitlist-content').is_visible() and not page.locator('#web-download-content').is_visible()
     transitions[-1]['apps_title']=page.title()
    route_errors=list(errors)
    not_found_response=page.goto(base+'/this-route-should-not-exist-id247',wait_until='domcontentloaded')
    not_found={'status':not_found_response.status,'visible_h1':page.locator('h1:visible').all_inner_texts()}
    not_found['expected_console_errors']=errors[len(route_errors):]
    resp=page.goto(base+'/sitemap.xml',wait_until='domcontentloaded')
    sitemap=page.locator('body').inner_text()
    expected=[base+p for p in ROUTES]
    included={p:p in sitemap for p in expected}
    browser.close()
  finally:
   app.terminate();app.wait(timeout=5)
 out={'pages':pages,'sitemap_status':resp.status,'sitemap_routes':included,'transitions':transitions,'not_found':not_found,'browser_errors':route_errors}
 route_checks={p['path']:{'not_generic_tool_desk':not (p['title']=='Tool Desk | Paperplane' or p['h1']==['Tool Desk']), 'h1_count':len(p['h1'])} for p in pages}
 out['specific_criteria']={'legacy_kb_convert_security_routes_not_generic':all(route_checks[x]['not_generic_tool_desk'] for x in ROUTES[5:9]),'download_and_apps_distinct':pages[3]['h1']!=pages[4]['h1'] and pages[3]['title']!=pages[4]['title'] and 'Join the Native Apps Waitlist' not in pages[4]['body_text'] and 'Open the PDF workspace' in pages[4]['body_text'] and 'Join the Native Apps Waitlist' in pages[3]['body_text'] and all(x['from_apps_to_download'] and x['back_to_apps_waitlist'] and not x['overflow'] for x in transitions),'reset_password_route_specific':route_checks['/reset-password']['not_generic_tool_desk'] and pages[-1]['reset_form_visible']}
 out['route_checks']=route_checks
 out['passed']=all(p['status']==200 and p['h1'] for p in pages) and resp.status==200 and all(included.values()) and all(out['specific_criteria'].values()) and not_found['status']==404 and not_found['visible_h1']==['404'] and not route_errors
 (ROOT/'reports/launch-audit-v24/browser-id247-seo-structure.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
 print(json.dumps(out,indent=2))
 if not out['passed']: raise SystemExit(1)
if __name__=='__main__': main()



