from playwright.sync_api import sync_playwright
from pathlib import Path
import json,time
PDF=str(Path('runtime_data_codex_audit/notes_69pages_audit.pdf').resolve())
with sync_playwright() as p:
 b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':1440,'height':1000});page.goto('http://127.0.0.1:8501',wait_until='domcontentloaded');
 def snap(label):
  print(label,page.evaluate("({marker:sessionStorage.getItem('paperplane-last-local-document'),chat:document.querySelectorAll('#chat-messages .chat-bubble.user').length,activeView:document.querySelector('#view-ai-studio')?.hidden,docbar:document.querySelector('#ai-active-doc-bar')?.hidden,sendDisabled:document.querySelector('#chat-send-btn')?.disabled,view:document.querySelector('#ai-doc-name')?.innerText,script:[...document.scripts].map(s=>s.src).find(x=>x.includes('app.js'))})"))
 snap('loaded')
 page.evaluate("switchWorkspaceView('ai')")
 snap('ai')
 page.locator('#ai-file-input').set_input_files(PDF)
 snap('upload')
 page.locator('#chat-input').fill('Summarize polynomial degrees and vector orthogonality.')
 snap('filled')
 page.locator('#chat-send-btn').click()
 snap('clicked')
 page.wait_for_timeout(100)
 snap('100ms')
 page.wait_for_timeout(2500)
 snap('complete')
 page.reload(wait_until='domcontentloaded')
 snap('reload-domcontent')
 page.wait_for_timeout(3500)
 snap('reload+3.5s')
 print('toast=',page.locator('.toast-notice').inner_text() if page.locator('.toast-notice').count() else None)
 b.close()
