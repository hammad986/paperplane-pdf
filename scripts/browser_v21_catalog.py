"""Run catalog fixtures through Chromium HTTP job/upload/download flows."""
import importlib.util, json, base64, socket, time, os
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
checks=load('v21checks',ROOT/'reports/launch-audit-v21/tool_content_audit.py')
helper=load('v21helper',ROOT/'reports/launch-audit-v14/browser_acceptance_v14.py')
with TemporaryDirectory(prefix='paperplane-v21-catalog-') as temp:
 root=Path(temp);app,base,identities=helper.start_server(root/'server')
 try:
  for _ in range(150):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.2)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   page=browser.new_page()
   page.context.add_cookies([{'name':'paperplane_token','value':identities['accounts'][0][1],'url':base}])
   page.goto(base)
   os.environ['PAPERPLANE_DATA_DIR']=str(root/'catalog-data')
   import server
   last=[0]
   def process(op,paths,options,output_dir):
    time.sleep(max(0,3.2-(time.monotonic()-last[0])));last[0]=time.monotonic()
    result=page.evaluate('''async c => {
      const form=new FormData(); form.append('operation',c.op);form.append('options',JSON.stringify(c.options));
      for(const f of c.files)form.append('files',new File([Uint8Array.from(atob(f.data),x=>x.charCodeAt(0))],f.name));
      let r=await fetch('/api/jobs',{method:'POST',body:form});if(!r.ok)throw new Error(await r.text());
      const job=await r.json();let state;
      for(let i=0;i<1200;i++) {await new Promise(r=>setTimeout(r,250));state=await(await fetch(job.status_url)).json();if(state.status==='completed')break;if(state.status==='failed')throw new Error(state.error);}
      if(state.status!=='completed')throw new Error('job timeout');
      r=await fetch(job.download_url);if(!r.ok)throw new Error('download '+r.status);
      const bytes=new Uint8Array(await r.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      return {name:state.output_name,data:btoa(binary)};
    }''',{'op':op,'options':options,'files':[{'name':x.name,'data':base64.b64encode(x.read_bytes()).decode()} for x in paths]})
    output=output_dir/Path(result['name']).name;output.write_bytes(base64.b64decode(result['data']));print(op,'downloaded',flush=True);return output
   server.process=process
   record=checks.round_result(1,server,checks.load_previous_checks(),root)
   (ROOT/'reports/launch-audit-v21/browser-catalog.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
   print([(r['operation'],r['status']) for r in record['results']],flush=True)
   browser.close()
 finally:app.terminate();app.wait(timeout=15)
