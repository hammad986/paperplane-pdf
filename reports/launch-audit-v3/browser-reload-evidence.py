from playwright.sync_api import sync_playwright
from pathlib import Path
import json,time
PDF=str(Path('runtime_data_codex_audit/notes_69pages_audit.pdf').resolve())
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 page=b.new_page(viewport={'width':1440,'height':1000})
 dialogs=[]
 page.on('dialog',lambda d:(dialogs.append({'type':d.type,'message':d.message}),d.accept()))
 page.goto('http://127.0.0.1:8501',wait_until='domcontentloaded',timeout=15000)
 page.evaluate("switchWorkspaceView('ai')")
 page.locator('#ai-file-input').set_input_files(PDF)
 page.locator('#chat-input').fill('Summarize polynomial degrees and vector orthogonality.')
 page.locator('#chat-send-btn').click()
 page.locator('.ai-stage-line').last.wait_for(timeout=30000)
 page.get_by_text('Complete',exact=True).last.wait_for(timeout=30000)
 before=page.evaluate("({marker:sessionStorage.getItem('paperplane-last-local-document'),userBubbles:document.querySelectorAll('#chat-messages .chat-bubble.user').length,script:[...document.scripts].map(s=>s.src).find(x=>x.includes('app.js'))})")
 t=time.monotonic()
 page.reload(wait_until='domcontentloaded',timeout=20000)
 samples=[]
 for delay in [100,300,700,1200,2000,3500]:
  page.wait_for_timeout(delay)
  samples.append({'elapsed_ms':round((time.monotonic()-t)*1000),'toast':page.locator('.toast-notice').inner_text() if page.locator('.toast-notice').count() else None,'marker':page.evaluate("sessionStorage.getItem('paperplane-last-local-document')"),'userBubbles':page.locator('#chat-messages .chat-bubble.user').count()})
 print(json.dumps({'before':before,'afterReload':samples,'dialogs':dialogs},ensure_ascii=False,indent=2))
 b.close()
