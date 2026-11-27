from __future__ import annotations
import base64, json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports'/'launch-audit-v24'/'browser-id223-protect-studio-handoff.json'
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

def read_pdf(path,password=None):
    with fitz.open(path) as pdf:
        if pdf.needs_pass: assert password and pdf.authenticate(password)>0
        return pdf.page_count,'\n'.join(page.get_text() for page in pdf)

def main():
    evidence={'rounds':[],'page_errors':[],'unexpected_console_errors':[],'live_or_payment_provider_contacted':False}
    with TemporaryDirectory(prefix='paperplane-v24-id223-') as tmp:
        temp=Path(tmp); source=temp/'protect-source.pdf'
        with fitz.open() as pdf:
            for i in (1,2): pdf.new_page().insert_text((72,72),f'PROTECT STUDIO HANDOFF PAGE {i}')
            pdf.save(source)
        app,base,_=helper.start_server(temp/'data')
        try:
            port=int(base.rsplit(':',1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError('local server did not start')
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='chrome',headless=True)
                for round_no in (1,2):
                    ctx=browser.new_context(viewport={'width':1366,'height':900},accept_downloads=True)
                    ctx.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode','server')")
                    page=ctx.new_page()
                    page.on('pageerror',lambda e:evidence['page_errors'].append(str(e)))
                    page.on('console',lambda m:evidence['unexpected_console_errors'].append(m.text) if m.type=='error' else None)
                    response=page.goto(base+'/protect-pdf',wait_until='domcontentloaded')
                    page.locator('#file-input').set_input_files(str(source))
                    page.wait_for_function('state.files?.length===1')
                    page.locator('#password').fill('Protect-Studio-Only!24')
                    page.locator('#run-button').click()
                    page.locator('#result-view-studio-btn:not([hidden])').wait_for(state='visible',timeout=60000)
                    snapshot={'round':round_no,'route_status':response.status if response else None,'protect_result_visible':True}
                    if round_no==2:
                        with page.expect_download(timeout=30000) as download_info:
                            page.locator('#result-download-link').click()
                        downloaded=temp/f'protect-download-{round_no}.pdf'
                        download_info.value.save_as(downloaded)
                        pages,text=read_pdf(downloaded,'Protect-Studio-Only!24')
                        assert pages==2 and all(f'PROTECT STUDIO HANDOFF PAGE {n}' in text for n in (1,2))
                        snapshot.update(download_name=download_info.value.suggested_filename,download_encrypted_content_checked=True,download_pages=pages)
                    page.locator('#result-view-studio-btn').click()
                    page.wait_for_function("location.pathname==='/studio' && !!window.state?.studio?.pdfDoc",timeout=45000)
                    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent!=='0'",timeout=30000)
                    payload=page.evaluate("""async()=>{const file=window.PaperplaneEditor?.editorState?.sourceFile;if(!file)return null;const bytes=new Uint8Array(await file.arrayBuffer());let bin='';for(let i=0;i<bytes.length;i+=0x8000)bin+=String.fromCharCode(...bytes.subarray(i,i+0x8000));return {name:file.name,data:btoa(bin),indicator:document.querySelector('#page-total-indicator')?.textContent}}""")
                    assert payload and payload['name'].lower().endswith('.pdf'),payload
                    studio_pdf=temp/f'studio-{round_no}.pdf';studio_pdf.write_bytes(base64.b64decode(payload['data']))
                    pages,text=read_pdf(studio_pdf,'Protect-Studio-Only!24')
                    assert pages==2 and all(f'PROTECT STUDIO HANDOFF PAGE {n}' in text for n in (1,2)),{'pages':pages,'text':text}
                    snapshot.update(studio_route=page.url.endswith('/studio'),studio_page_indicator=payload['indicator'],studio_encrypted_content_checked=True,studio_pages=pages,source_name=payload['name'])
                    evidence['rounds'].append(snapshot)
                    assert not evidence['page_errors'],evidence
                    assert not evidence['unexpected_console_errors'],evidence
                    ctx.close()
                browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except Exception: app.kill(); app.wait(timeout=5)
    evidence['passed']=len(evidence['rounds'])==2 and all(r.get('studio_encrypted_content_checked') for r in evidence['rounds']) and not evidence['page_errors'] and not evidence['unexpected_console_errors']
    OUT.write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence,indent=2))
    if not evidence['passed']: raise SystemExit(1)
if __name__=='__main__':main()
