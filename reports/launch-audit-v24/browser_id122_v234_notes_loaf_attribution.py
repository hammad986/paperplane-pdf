from __future__ import annotations
import json,os,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; VERSION=os.environ.get('PAPERPLANE_PERF_VERSION','v234'); OUT=ROOT/'reports/launch-audit-v24'/f'browser-id122-{VERSION}-notes-loaf-attribution.json'; SOURCE=Path(r'C:\Users\mdham\Downloads\notes.pdf')
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14')); import browser_acceptance_v14 as helper

def main():
 with TemporaryDirectory(prefix='paperplane-id122-loaf-') as tmp:
  app,base,_=helper.start_server(Path(tmp)/'data'); result={'cpu_throttle':4,'source_bytes':SOURCE.stat().st_size}
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(120):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError: time.sleep(.15)
   with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True); page=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=3); cdp=page.context.new_cdp_session(page); cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
    page.add_init_script("window.__loafs=[];window.__loafSupported=PerformanceObserver.supportedEntryTypes.includes('long-animation-frame');if(window.__loafSupported)new PerformanceObserver(l=>l.getEntries().forEach(e=>window.__loafs.push({duration:e.duration,startTime:e.startTime,scripts:(e.scripts||[]).map(s=>({name:s.sourceFunctionName,invoker:s.invoker,source:s.sourceURL,line:s.sourceCharPosition,duration:s.duration,executionStart:s.executionStart}))}))).observe({type:'long-animation-frame',buffered:true});")
    page.goto(base+'/studio',wait_until='domcontentloaded'); page.locator('#studio-file-input').set_input_files(str(SOURCE)); page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='69' && document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=120000); page.wait_for_timeout(200)
    result.update({'loaf_supported':page.evaluate('window.__loafSupported'),'frames':page.evaluate('window.__loafs'),'page_count':page.locator('#page-total-indicator').inner_text()})
    browser.close()
   result['frames_over_250ms']=[f for f in result['frames'] if f['duration']>250]
   result['result']='captured' if result['loaf_supported'] else 'unsupported'
   OUT.write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps({'result':result['result'],'frame_count':len(result['frames']),'frames_over_250ms':result['frames_over_250ms']},indent=2))
  finally: app.terminate(); app.wait(timeout=10)
if __name__=='__main__':main()
