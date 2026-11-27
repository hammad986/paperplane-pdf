"""Browser-check the larger-optimized-candidate fallback with a controlled size probe."""
from __future__ import annotations
import json, os, socket, threading, time, sys
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, uvicorn
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

def main():
    with TemporaryDirectory(prefix='paperplane-v24-compress-larger-candidate-') as td:
        temp=Path(td); data=temp/'data'; data.mkdir()
        os.environ.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development',
            'PAPERPLANE_DATA_DIR':str(data),'PAPERPLANE_ADMIN_KEY':'controlled-compression-test-key',
            'PAPERPLANE_ADMIN_CODE':'controlled-compression-test-code','PAPERPLANE_SECURE_COOKIES':'false'})
        from pathlib import Path as PathClass
        import persistence, converters
        from server import app
        persistence.init_db()
        source=temp/'already-compact-source.pdf'
        with fitz.open() as pdf:
            page=pdf.new_page(); page.insert_text((72,90),'COMPRESSION ORIGINAL MUST BE PRESERVED')
            pdf.save(source,garbage=4,deflate=True)
        source_bytes=source.read_bytes(); real_stat=PathClass.stat
        forced_candidates=[]
        def report_larger_candidate(self,*args,**kwargs):
            result=real_stat(self,*args,**kwargs)
            if '_pass_' in self.name and self.suffix.lower()=='.pdf':
                values=list(result); values[6]=max(values[6],source.stat().st_size+1)
                forced_candidates.append({'name':self.name,'reported_bytes':values[6],'actual_bytes':result.st_size})
                return os.stat_result(values)
            return result
        PathClass.stat=report_larger_candidate
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0)); port=probe.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning',access_log=False))
        worker=threading.Thread(target=server.run,daemon=True); worker.start()
        evidence={'page_errors':[],'console_errors':[],'forced_candidate_size_reports':forced_candidates,
            'source_bytes':len(source_bytes)}
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.2): break
                except OSError: time.sleep(.1)
            else: raise RuntimeError('local app did not start')
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='chrome',headless=True)
                page=browser.new_page(viewport={'width':1366,'height':900},accept_downloads=True)
                page.on('pageerror',lambda err:evidence['page_errors'].append(str(err)))
                page.on('console',lambda msg:evidence['console_errors'].append(msg.text) if msg.type=='error' else None)
                response=page.goto(base+'/compress-pdf',wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(source))
                page.wait_for_function('state.files?.length === 1')
                page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(timeout=60000)
                note=page.locator('#result-meta').inner_text() if page.locator('#result-meta').count() else ''
                with page.expect_download(timeout=30000) as pending:
                    page.locator('#result-download-link').click()
                download=pending.value; output=temp/download.suggested_filename; download.save_as(output)
                output_bytes=output.read_bytes()
                with fitz.open(output) as result:
                    output_text='\n'.join(p.get_text() for p in result)
                    valid=result.is_pdf and len(result)==1 and 'COMPRESSION ORIGINAL MUST BE PRESERVED' in output_text
                evidence.update({'http_status':response.status if response else None,'download_name':download.suggested_filename,
                    'output_bytes':len(output_bytes),'byte_identical_to_source':output_bytes==source_bytes,
                    'valid_content_checked_pdf':valid,'result_note':note,'forced_candidate_count':len(forced_candidates)})
                browser.close()
        finally:
            server.should_exit=True; worker.join(timeout=5); PathClass.stat=real_stat
        evidence['result']=(evidence['http_status']==200 and evidence['forced_candidate_count']>0
            and evidence['byte_identical_to_source'] and evidence['valid_content_checked_pdf']
            and 'original pdf is smaller' in evidence['result_note'].lower()
            and not evidence['page_errors'] and not evidence['console_errors'])
        (OUT/'browser-compression-larger-candidate-preserves-original.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        print(json.dumps(evidence,indent=2))
        if not evidence['result']: raise SystemExit(1)
if __name__=='__main__': main()
