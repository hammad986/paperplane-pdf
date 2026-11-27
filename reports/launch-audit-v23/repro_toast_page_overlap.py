from pathlib import Path
from tempfile import TemporaryDirectory
import base64,json,socket,sys,time,fitz
from playwright.sync_api import sync_playwright
root=Path.cwd(); sys.path.insert(0,str(root/'reports'/'launch-audit-v14')); import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-toast-page-overlap-') as temp:
    pdf=Path(temp)/'toast.pdf'
    d=fitz.open(); p=d.new_page(); p.insert_text((72,72),'TOAST-PAGE-OVERLAP'); d.save(pdf); d.close()
    app,base,_=helper.start_server(Path(temp)/'data')
    try:
        for _ in range(150):
            try:
                with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2): break
            except OSError: time.sleep(.2)
        else: raise RuntimeError('local app failed to start')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':1366,'height':900})
            errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base+'/studio',wait_until='domcontentloaded'); page.wait_for_function('window.loadDocumentIntoStudio')
            data=base64.b64encode(pdf.read_bytes()).decode()
            page.evaluate("async b=>{let a=Uint8Array.from(atob(b),c=>c.charCodeAt(0));let f=new File([a],'toast.pdf',{type:'application/pdf'});await loadDocumentIntoStudio(f);showToast('Restored local-result.pdf on page 1','success',8000)}",data)
            page.wait_for_function("document.querySelector('.toast-notice')?.getClientRects().length")
            page.set_viewport_size({'width':390,'height':844})
            page.wait_for_timeout(400)
            measurement=page.evaluate("""()=>{let t=document.querySelector('.toast-notice'),p=document.querySelector('.studio-page-sheet'),c=document.querySelector('#pdf-canvas'),b=document.querySelector('#studio-toolbar'),d=document.querySelector('#studio-mobile-dock');const box=x=>{let r=x.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}};let a=box(t),q=box(p),x=box(c),z=box(b),m=box(d);return {toast:a,page:q,canvas:x,toolbar:z,dock:m,classes:t.className,topStyle:getComputedStyle(t).top,customTop:t.style.getPropertyValue('--studio-toast-top'),pageOverlap:Math.min(a.right,q.right)-Math.max(a.left,q.left)>0&&Math.min(a.bottom,q.bottom)-Math.max(a.top,q.top)>0,canvasOverlap:Math.min(a.right,x.right)-Math.max(a.left,x.left)>0&&Math.min(a.bottom,x.bottom)-Math.max(a.top,x.top)>0}}""")
            print(json.dumps({'measurement':measurement,'page_errors':errors},indent=2)); browser.close()
    finally:
        app.terminate()
        try: app.wait(timeout=15)
        except: app.kill()
