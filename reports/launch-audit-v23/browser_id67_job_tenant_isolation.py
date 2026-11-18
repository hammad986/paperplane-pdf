from pathlib import Path
from tempfile import TemporaryDirectory
import base64, fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id67-') as temp:
    root=Path(temp)
    pdfs=[]
    for number in (1,2):
        path=root/f'owner-source-{number}.pdf'
        with fitz.open() as document:
            document.new_page().insert_text((72,72),f'ID67 PRIVATE OWNER DOCUMENT {number}')
            document.save(path)
        pdfs.append(base64.b64encode(path.read_bytes()).decode('ascii'))
    app,base,identity=helper.start_server(root/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        owner_token=identity['accounts'][0][1]
        other_token=identity['accounts'][1][1]
        results=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for number in (1,2):
                page=browser.new_page(viewport={'width':1366,'height':900})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/',wait_until='domcontentloaded')
                result=page.evaluate("""async ({ownerToken,otherToken,files})=>{
                  const uploads=new FormData();uploads.append('operation','merge');uploads.append('options','{}');
                  files.forEach((encoded,index)=>{const binary=atob(encoded);const bytes=new Uint8Array(binary.length);for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);uploads.append('files',new File([bytes],`owner-${index+1}.pdf`,{type:'application/pdf'}));});
                  const createdResponse=await fetch('/api/jobs',{method:'POST',headers:{Authorization:`Bearer ${ownerToken}`},body:uploads});
                  const created=await createdResponse.json();
                  if(!createdResponse.ok)return {createdStatus:createdResponse.status,created};
                  let status,ownerStatus;
                  for(let i=0;i<120;i++){const r=await fetch(`/api/jobs/${created.job_id}`,{headers:{Authorization:`Bearer ${ownerToken}`}});ownerStatus=await r.json();if(ownerStatus.status==='completed'||ownerStatus.status==='failed')break;await new Promise(resolve=>setTimeout(resolve,250));}
                  const otherStatus=await fetch(`/api/jobs/${created.job_id}`,{headers:{Authorization:`Bearer ${otherToken}`}});
                  const otherDownload=await fetch(`/api/jobs/${created.job_id}/download`,{headers:{Authorization:`Bearer ${otherToken}`}});
                  const anonymousStatus=await fetch(`/api/jobs/${created.job_id}`);
                  const anonymousDownload=await fetch(`/api/jobs/${created.job_id}/download`);
                  const ownerDownload=await fetch(`/api/jobs/${created.job_id}/download`,{headers:{Authorization:`Bearer ${ownerToken}`}});
                  const bytes=new Uint8Array(await ownerDownload.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
                  return {createdStatus:createdResponse.status,jobId:created.job_id,ownerCompletion:ownerStatus.status,ownerPages:ownerStatus.page_count,otherStatus:otherStatus.status,otherDownload:otherDownload.status,anonymousStatus:anonymousStatus.status,anonymousDownload:anonymousDownload.status,ownerDownload:ownerDownload.status,ownerPdfBase64:btoa(binary),ownerDownloadBytes:bytes.length};
                }""",{'ownerToken':owner_token,'otherToken':other_token,'files':pdfs})
                assert result.get('createdStatus')==202,result
                assert result['ownerCompletion']=='completed' and result['ownerPages']==2,result
                assert result['otherStatus']==404 and result['otherDownload']==404,result
                assert result['anonymousStatus']==404 and result['anonymousDownload']==404,result
                assert result['ownerDownload']==200 and result['ownerDownloadBytes']>500,result
                downloaded=root/f'id67-owner-download-round{number}.pdf'
                downloaded.write_bytes(base64.b64decode(result['ownerPdfBase64']))
                with fitz.open(downloaded) as output:
                    text='\n'.join(item.get_text() for item in output)
                    pages=output.page_count
                assert pages==2 and 'ID67 PRIVATE OWNER DOCUMENT 1' in text and 'ID67 PRIVATE OWNER DOCUMENT 2' in text,(pages,text)
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id67-tenant-isolation-round{number}.png'))
                results.append({'round':number,'created_status':result['createdStatus'],'owner_job_status':result['ownerCompletion'],'owner_pages':pages,'other_user_status':result['otherStatus'],'other_user_download':result['otherDownload'],'anonymous_status':result['anonymousStatus'],'anonymous_download':result['anonymousDownload'],'owner_download_content_checked':True,'page_errors':errors})
                page.close()
            browser.close()
        output={'rounds':results};(OUT/'browser-id67-job-tenant-isolation.json').write_text(json.dumps(output,indent=2),encoding='utf-8');print(json.dumps(output,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
