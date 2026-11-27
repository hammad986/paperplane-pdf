from pathlib import Path
import json, re, sys, fitz
ROOT=Path('.').resolve(); SOURCE=ROOT/'reports/launch-audit-v24/fixtures/arxiv-1706.03762v7.pdf'
sys.path.insert(0,str(ROOT)); import ai_engine
source_blocks=[]
with fitz.open(SOURCE) as doc:
    for page in doc:
        for block in page.get_text('blocks'):
            if len(block)>=7 and block[6]==0 and len(block[4].strip())>=2:
                source_blocks.append({'page':page.number+1,'rect':[round(x,2) for x in block[:4]],'text':block[4].strip()})
def provider(batch, language, deadline=None):
    return {sid: (f'Traducido {sid}' if len(re.findall(r'\w+', text, flags=re.UNICODE))>2 else 'es') for sid,text in batch}
ai_engine._translate_text_batch=provider
original=fitz.Page.insert_htmlbox; failures=[]
def instrument(page, rect, html, *args, **kwargs):
    spare=original(page,rect,html,*args,**kwargs)
    if spare[0] < 0:
        index=page.number
        item=source_blocks[index] if index<len(source_blocks) else None
        failures.append({'overlay_page_index':index,'result_spare':spare[0],'rect':[round(rect.x0,2),round(rect.y0,2),round(rect.x1,2),round(rect.y1,2)],'html':html,'source_block':item})
    return spare
fitz.Page.insert_htmlbox=instrument
report={}
try:
    ai_engine.translate_pdf_layout(SOURCE,ROOT/'reports/launch-audit-v24/tmp-id1-fit-debug.pdf',target_language='Spanish',report=report)
finally:
    fitz.Page.insert_htmlbox=original
out={'block_count':len(source_blocks),'translated':report.get('blocks_translated'),'preserved':report.get('blocks_preserved'),'failures':failures}
(ROOT/'reports/launch-audit-v24/id1-fit-failure-diagnostic.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
