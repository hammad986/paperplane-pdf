from __future__ import annotations
import json, socket, sys, tempfile, time
from pathlib import Path
import fitz
from pypdf import PdfReader
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
TARGET='ID37 exact annotation target'
with tempfile.TemporaryDirectory(prefix='paperplane-id37-annotate-') as temporary:
 root=Path(temporary); source=root/'annotate-source.pdf'
 with fitz.open() as doc:
  page=doc.new_page(width=420,height=600); page.insert_text((50,120),TARGET,fontsize=18)
  page.insert_text((50,180),'Unchanged searchable content after markup.',fontsize=12)
  doc.save(source)
 app,base,_identity=helper.start_server(root/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(150):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.2)
  else:raise RuntimeError('Local Paperplane server did not start')
  rounds=[]
  with sync_playwright() as playwright:
   browser=playwright.chromium.launch(channel='chrome',headless=True)
   for n,(annot_type,width) in enumerate((('highlight',1366),('underline',820),('strikeout',390)),1):
    context=browser.new_context(viewport={'width':width,'height':900},accept_downloads=True,service_workers='block')
    page=context.new_page(); errors=[]; job_posts=[]; console_errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('console',lambda message:console_errors.append(message.text) if message.type=='error' else None)
    page.on('request',lambda request:job_posts.append(request.url) if request.method=='POST' and request.url.endswith('/api/jobs') else None)
    response=page.goto(base+'/annotate-pdf',wait_until='domcontentloaded',timeout=20000)
    assert response and response.status==200
    toggle=page.locator('#client-privacy-toggle')
    if not toggle.is_checked(): toggle.check()
    page.locator('#file-input').set_input_files(str(source))
    page.locator('#annot_type').select_option(annot_type)
    page.locator('#page').fill('1')
    page.locator('#text').fill(TARGET)
    page.locator('#run-button').click()
    page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=30000)
    with page.expect_download(timeout=20000) as download_wait: page.locator('#result-download-link').click()
    result=OUT/f'id37-local-annotate-{annot_type}.pdf'; download_wait.value.save_as(result)
    with fitz.open(result) as output:
     assert output.page_count==1
     reader_page=output[0]; reader_page.get_links()
     assert TARGET in reader_page.get_text() and 'Unchanged searchable content after markup.' in reader_page.get_text()
     content_bbox=tuple(round(v,2) for v in reader_page.search_for(TARGET)[0]); page_height=reader_page.rect.height
     reader_annots=list(reader_page.annots() or []); assert len(reader_annots)==1
     assert reader_annots[0].type[1]=={'highlight':'Highlight','underline':'Underline','strikeout':'StrikeOut'}[annot_type]
     assert TARGET in reader_annots[0].info.get('content','')
    reader=PdfReader(str(result)); raw_annots=reader.pages[0].get('/Annots',[])
    assert len(raw_annots)==1,len(raw_annots)
    raw=raw_annots[0].get_object()
    expected_subtype={'highlight':'/Highlight','underline':'/Underline','strikeout':'/StrikeOut'}[annot_type]
    assert str(raw.get('/Subtype'))==expected_subtype,raw
    assert TARGET in str(raw.get('/Contents','')),raw
    if annot_type=='highlight': assert len(raw.get('/QuadPoints',[]))==8,raw
    assert float(raw['/Rect'][0]) <= content_bbox[0]+1 and float(raw['/Rect'][2]) >= content_bbox[2]-1, (raw,content_bbox)
    assert page_height-float(raw['/Rect'][3]) <= content_bbox[3]+1 and page_height-float(raw['/Rect'][1]) >= content_bbox[1]-1, (raw,content_bbox,page_height)
    rect=tuple(round(float(v),2) for v in raw['/Rect'])
    pdfjs_result=page.evaluate("""async data => {
      const bytes=Uint8Array.from(atob(data),ch=>ch.charCodeAt(0));
      const task=window.pdfjsLib.getDocument({data:bytes,isEvalSupported:false});
      try { const pdf=await task.promise; const annotations=await (await pdf.getPage(1)).getAnnotations({intent:'display'});
        const source=await pdf.getPage(1); const viewport=source.getViewport({scale:1});
        async function render(mode){const canvas=document.createElement('canvas');canvas.width=viewport.width;canvas.height=viewport.height;const context=canvas.getContext('2d',{willReadFrequently:true});
          await source.render({canvasContext:context,viewport,annotationMode:mode}).promise;return context.getImageData(0,0,canvas.width,canvas.height).data;}
        const enabled=await render(window.pdfjsLib.AnnotationMode.ENABLE); const disabled=await render(window.pdfjsLib.AnnotationMode.DISABLE);
        let changed=0;for(let i=0;i<enabled.length;i+=4)if(enabled[i]!==disabled[i]||enabled[i+1]!==disabled[i+1]||enabled[i+2]!==disabled[i+2])changed++;
        return {count:annotations.length,subtypes:annotations.map(a=>a.subtype),annotation_pixels_changed:changed};
      } finally { await task.destroy(); }
    }""",__import__('base64').b64encode(result.read_bytes()).decode('ascii'))
    assert pdfjs_result['count']==1 and pdfjs_result['subtypes']==[expected_subtype[1:]],pdfjs_result
    assert pdfjs_result['annotation_pixels_changed']>0,pdfjs_result
    assert not job_posts,job_posts
    assert not errors,errors
    assert not console_errors,console_errors
    rounds.append({'round':n,'type':annot_type,'viewport':width,'status':response.status,'output_bytes':result.stat().st_size,'page_count':1,'annotation_type':expected_subtype[1:],'annotation_rect':rect,'text_bbox':content_bbox,'pdfjs_annotation':pdfjs_result,'pymupdf_annotation':'validated','text_preserved':True,'server_job_posts':0,'page_errors':errors,'console_errors':console_errors})
    context.close()
   # Browser mode must ask before uploading when an annotation type or phrase shape is unsupported locally.
   context=browser.new_context(viewport={'width':390,'height':844},accept_downloads=True,service_workers='block')
   page=context.new_page(); errors=[]; job_posts=[]
   page.on('pageerror',lambda error:errors.append(str(error)))
   page.on('request',lambda request:job_posts.append(request.url) if request.method=='POST' and request.url.endswith('/api/jobs') else None)
   page.goto(base+'/annotate-pdf',wait_until='domcontentloaded',timeout=20000)
   page.locator('#file-input').set_input_files(str(source))
   page.locator('#annot_type').select_option('note'); page.locator('#content').fill('Local-only note fallback check')
   page.locator('#run-button').click(); dialog=page.locator('.app-confirm-dialog'); dialog.wait_for(state='visible',timeout=15000)
   note_prompt=dialog.inner_text(); assert 'Sticky notes and rectangles require Server Processing' in note_prompt,note_prompt
   dialog.locator('.app-confirm-cancel').click(); dialog.wait_for(state='detached',timeout=5000)
   page.locator('#annot_type').select_option('highlight'); page.locator('#text').fill('exact annotation')
   page.locator('#run-button').click(); dialog.wait_for(state='visible',timeout=15000)
   span_prompt=dialog.inner_text(); assert 'spans only part of a block' in span_prompt,span_prompt
   dialog.locator('.app-confirm-cancel').click(); dialog.wait_for(state='detached',timeout=5000)
   assert not job_posts,job_posts; assert not errors,errors
   unsupported={'note_disclosure':note_prompt,'multi_block_text_disclosure':span_prompt,'cancelled_uploads':0,'page_errors':errors}
   context.close(); browser.close()
 finally:
  app.terminate(); app.wait(timeout=10)
report={'operation':'annotate','fixture':'synthetic selectable one-page PDF','rounds':rounds,'unsupported_local_cases':unsupported,'result':'PASS'}
(OUT/'browser-id37-local-annotate.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
