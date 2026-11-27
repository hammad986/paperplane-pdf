"""Measure Scan-to-PDF guidance and progress feedback on actual local PDF exports."""
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from PIL import Image,ImageDraw
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/launch-audit-v24/browser-id277-278-scan-progress.json'
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14'));import browser_acceptance_v14 as helper

def main():
 with TemporaryDirectory(prefix='paperplane-277-278-') as td:
  td=Path(td); imgs=[]
  for n,color in enumerate(('orange','teal'),1):
   p=td/f'page-{n}.jpg';im=Image.new('RGB',(500,700),color);d=ImageDraw.Draw(im);d.text((40,60),f'Page {n} scan fixture',fill='white');im.save(p,quality=90);imgs.append(p)
  app,base,_=helper.start_server(td/'data');ev={'layout_rounds':[],'workflow_rounds':[],'page_errors':[],'console_errors':[]}
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
    for width in (320,390,820,1366):
     page=browser.new_page(viewport={'width':width,'height':900});page.on('pageerror',lambda e:ev['page_errors'].append(str(e)[:200]));page.on('console',lambda m:ev['console_errors'].append(m.text[:200])if m.type=='error'else None)
     page.goto(base+'/scan-to-pdf',wait_until='domcontentloaded');page.wait_for_function("document.querySelectorAll('.seo-content .seo-howto-step').length===3")
     ev['layout_rounds'].append(page.evaluate("""()=>{const s=[...document.querySelectorAll('.seo-content .seo-howto-step')];return {width:innerWidth,steps:s.map(e=>{let h=e.querySelector('h3'),p=e.querySelector('p'),r=e.getBoundingClientRect(),hr=h.getBoundingClientRect(),pr=p.getBoundingClientRect();return {heading:h.innerText,body:p.innerText,card:{width:r.width,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,scrollHeight:e.scrollHeight,clientHeight:e.clientHeight},heading:{scrollWidth:h.scrollWidth,clientWidth:h.clientWidth,scrollHeight:h.scrollHeight,clientHeight:h.clientHeight,overflowX:getComputedStyle(h).overflowX,overflowY:getComputedStyle(h).overflowY},paragraph:{scrollWidth:p.scrollWidth,clientWidth:p.clientWidth,scrollHeight:p.scrollHeight,clientHeight:p.clientHeight,overflowX:getComputedStyle(p).overflowX,overflowY:getComputedStyle(p).overflowY}}})}}"""))
     page.close()
    for route,width in (('/jpg-to-pdf',390),('/jpg-to-pdf',1366),('/scan-to-pdf',390),('/scan-to-pdf',1366)):
     page=browser.new_page(viewport={'width':width,'height':900},accept_downloads=True);page.on('pageerror',lambda e:ev['page_errors'].append(str(e)[:200]));page.on('console',lambda m:ev['console_errors'].append(m.text[:200])if m.type=='error'else None)
     page.goto(base+route,wait_until='domcontentloaded')
     page.evaluate("""()=>{window.__progressMutations=[];const c=document.querySelector('#progress-card'),t=document.querySelector('#progress-status-title');const record=()=>{const r=c.getBoundingClientRect();window.__progressMutations.push({time:performance.now(),hidden:c.hidden,text:t?.innerText,rect:{top:r.top,bottom:r.bottom,height:r.height},visible:!c.hidden&&getComputedStyle(c).display!=='none'&&r.height>0,percent:document.querySelector('#progress-percent')?.innerText})};new MutationObserver(record).observe(c,{attributes:true,childList:true,subtree:true,characterData:true});record()}""")
     page.locator('#file-input').set_input_files([str(x) for x in imgs]);page.wait_for_function('state.files?.length===2');page.locator('#run-button').click();page.locator('#result-download-link:not([hidden])').wait_for(timeout=60000);page.wait_for_timeout(100)
     ev['workflow_rounds'].append({'route':route,'width':width,'result_title':page.locator('#result-title').inner_text(),'progress_visible_after':not page.locator('#progress-card').evaluate('(e)=>e.hidden'),'progress_text_after':page.locator('#progress-status-title').inner_text(),'progress_percent_after':page.locator('#progress-percent').inner_text(),'progress_observations':page.evaluate('window.__progressMutations')})
     page.wait_for_timeout(1000);ev['workflow_rounds'][-1]['progress_hidden_after_hold']=page.locator('#progress-card').evaluate('(e)=>e.hidden')
     with page.expect_download(timeout=30000) as dl:page.locator('#result-download-link').click()
     out=td/f'{route.strip("/")}-{width}.pdf';dl.value.save_as(out)
     with fitz.open(out) as doc:ev['workflow_rounds'][-1]['download']={'name':dl.value.suggested_filename,'pages':doc.page_count,'is_pdf':doc.is_pdf}
     page.close()
    browser.close()
  finally:app.terminate();app.wait(timeout=5)
  layout_ok=all(all(s['card']['scrollWidth']<=s['card']['clientWidth']+1 and s['heading']['scrollWidth']<=s['heading']['clientWidth']+1 and s['heading']['scrollHeight']<=s['heading']['clientHeight']+1 and s['paragraph']['scrollWidth']<=s['paragraph']['clientWidth']+1 and s['paragraph']['scrollHeight']<=s['paragraph']['clientHeight']+1 for s in r['steps']) for r in ev['layout_rounds'])
  ev['layout_pass']=layout_ok
  ev['workflow_pass']=len(ev['workflow_rounds'])==4 and all(r['download']['is_pdf'] and r['download']['pages']==2 and r['progress_visible_after'] and r['progress_text_after']=='Finished!' and r['progress_percent_after']=='100%' and r['progress_hidden_after_hold'] and any(m['text']=='Finished!' and m['visible'] and m['percent']=='100%' for m in r['progress_observations']) for r in ev['workflow_rounds']) and not ev['page_errors'] and not ev['console_errors']
  ev['overall']='passed' if ev['layout_pass'] and ev['workflow_pass'] else 'failed'
  OUT.write_text(json.dumps(ev,indent=2),encoding='utf-8');print(json.dumps(ev,indent=2))
  if ev['overall']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
