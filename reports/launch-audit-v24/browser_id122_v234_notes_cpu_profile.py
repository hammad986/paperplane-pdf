from __future__ import annotations
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'reports/launch-audit-v24/browser-id122-v234-notes-cpu-profile.json'
SOURCE=Path(r'C:\Users\mdham\Downloads\notes.pdf')
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14')); import browser_acceptance_v14 as helper

def main():
 with TemporaryDirectory(prefix='paperplane-id122-cpu-profile-') as tmp:
  app,base,_=helper.start_server(Path(tmp)/'data')
  result={'cpu_throttle':4,'source_bytes':SOURCE.stat().st_size}
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(120):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError: time.sleep(.15)
   with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True); page=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=3)
    cdp=page.context.new_cdp_session(page); cdp.send('Emulation.setCPUThrottlingRate',{'rate':4}); cdp.send('Profiler.enable'); cdp.send('Profiler.setSamplingInterval',{'interval':100}); cdp.send('Profiler.start')
    page.goto(base+'/studio',wait_until='domcontentloaded'); page.locator('#studio-file-input').set_input_files(str(SOURCE)); page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='69' && document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=120000)
    profile=cdp.send('Profiler.stop')['profile']; nodes={n['id']:n for n in profile['nodes']}; samples=profile.get('samples',[])
    hot=[]
    for n in sorted(profile['nodes'],key=lambda x:x.get('hitCount',0),reverse=True)[:80]:
     if n.get('hitCount',0): hot.append({'function':n.get('callFrame',{}).get('functionName'),'url':n.get('callFrame',{}).get('url'),'line':n.get('callFrame',{}).get('lineNumber'),'self_samples':n.get('hitCount',0)})
    result.update({'sample_count':len(samples),'profile_start_ms':profile.get('startTime'),'profile_end_ms':profile.get('endTime'),'hot_functions':hot,'page_count':page.locator('#page-total-indicator').inner_text()})
    browser.close()
   result['result']='captured'; OUT.write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))
  finally: app.terminate(); app.wait(timeout=10)
if __name__=='__main__':main()
