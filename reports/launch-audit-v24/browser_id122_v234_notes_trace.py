from __future__ import annotations
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'reports/launch-audit-v24/browser-id122-v234-notes-trace.json'; SOURCE=Path(r'C:\Users\mdham\Downloads\notes.pdf')
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14')); import browser_acceptance_v14 as helper

def main():
 with TemporaryDirectory(prefix='paperplane-id122-trace-') as tmp:
  app,base,_=helper.start_server(Path(tmp)/'data');
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(120):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError: time.sleep(.15)
   with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True); page=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=3); cdp=page.context.new_cdp_session(page); cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
    events=[]; cdp.on('Tracing.dataCollected',lambda e:events.extend(e.get('value',[])))
    page.goto(base+'/studio',wait_until='domcontentloaded'); cdp.send('Tracing.start',{'categories':'devtools.timeline,v8.execute,blink.user_timing','transferMode':'ReportEvents'})
    page.locator('#studio-file-input').set_input_files(str(SOURCE)); page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='69' && document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=120000)
    cdp.send('Tracing.end')
    done=False
    def complete(_e):
     nonlocal done; done=True
    cdp.on('Tracing.tracingComplete',complete)
    for _ in range(100):
     if done: break
     time.sleep(.1)
    heavy=[]
    for e in events:
     dur=e.get('dur',0)/1000
     if dur>=50:
      data=e.get('args',{}).get('data',{})
      heavy.append({'name':e.get('name'),'category':e.get('cat'),'duration_ms':round(dur,1),'function':data.get('functionName') or data.get('name'),'url':data.get('url'),'forced_layout_ms':round(data.get('forcedStyleAndLayoutDuration',0)*1000,1) if data.get('forcedStyleAndLayoutDuration') else None,'stack':data.get('stackTrace')})
    heavy.sort(key=lambda x:x['duration_ms'],reverse=True)
    result={'trace_event_count':len(events),'long_events_over_50ms':len(heavy),'heavy_events':heavy[:80],'source':str(SOURCE),'cpu_throttle':4}
    OUT.write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps({'trace_event_count':len(events),'long_events_over_50ms':len(heavy),'heavy_events':heavy[:25]},indent=2)); browser.close()
  finally: app.terminate(); app.wait(timeout=10)
if __name__=='__main__':main()
