import fitz,json
from pathlib import Path
from playwright.sync_api import sync_playwright
pdf=fitz.open();
for marker in ['ACCOUNT_A_DOC_1','ACCOUNT_A_DOC_2']:
 p=pdf.new_page();p.insert_text((40,60),marker)
buf=pdf.tobytes();pdf.close();errors=[];rounds=[]
with sync_playwright() as p:
 b=p.chromium.launch()
 for n in (1,2):
  page=b.new_page();page.set_default_timeout(12000);page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:8767/merge-pdf',wait_until='domcontentloaded');page.wait_for_function("()=>!document.body.classList.contains('auth-pending')")
  awaitA=page.evaluate("async()=>{if(typeof window.setAuthenticatedWorkspaceUser!=='function') return false; await window.setAuthenticatedWorkspaceUser({authenticated:true,user_id:'synthetic-A'});return true}")
  if not awaitA: raise AssertionError('workspace auth transition helper unavailable')
  if page.locator('#tab-studio-view').is_visible(): page.locator('#tab-studio-view').click()
  page.locator('#studio-file-input').set_input_files({'name':f'account-a-{n}.pdf','mimeType':'application/pdf','buffer':buf});page.wait_for_function("()=>document.querySelector('#studio-page-count')?.textContent.trim()==='2'")
  scopeA=page.evaluate("sessionStorage.getItem('paperplane-local-work-account-id')")
  awaitB=page.evaluate("async()=>{await window.setAuthenticatedWorkspaceUser({authenticated:true,user_id:'synthetic-B'});return true}")
  countB=page.locator('#studio-page-count').inner_text().strip()
  scopeB=page.evaluate("sessionStorage.getItem('paperplane-local-work-account-id')")
  keys=page.evaluate("""async()=>new Promise((resolve,reject)=>{let r=indexedDB.open('paperplane-local-work');r.onsuccess=()=>{let db=r.result;let q=db.transaction('work','readonly').objectStore('work').getAllKeys();q.onsuccess=()=>resolve(q.result.filter(k=>String(k).includes('studio-pdf')));q.onerror=()=>reject(q.error)}})""")
  page.reload(wait_until='domcontentloaded');page.wait_for_function("()=>!document.body.classList.contains('auth-pending')");page.wait_for_timeout(500)
  restored=page.locator('#studio-page-count').inner_text().strip()
  rounds.append({'round':n,'scope_a':scopeA,'scope_b_before_reload':scopeB,'account_b_count_before_reload':countB,'page_count_after_reload':restored,'stored_studio_keys':keys,'no_cross_account_restore':countB=='0' and restored=='0' and any(str(k).startswith('account:synthetic-A:') for k in keys) and not any(str(k).startswith('account:synthetic-B:') for k in keys)})
  page.close()
 b.close()
result={'build':'app.js v191/styles71','synthetic_account_scope_test':True,'rounds':rounds,'browser_errors':errors,'passed':len(rounds)==2 and all(x['no_cross_account_restore'] for x in rounds) and not errors}
Path('reports/launch-audit-v24/browser-id114-account-scope-isolation.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))