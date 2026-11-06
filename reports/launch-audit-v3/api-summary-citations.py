import json,re,requests
from pathlib import Path
BASE='http://127.0.0.1:8501'
FILES=[('69-page',Path('runtime_data_codex_audit/notes_69pages_audit.pdf'),'Summarize polynomial degrees and vector orthogonality.'),('3-page',Path('runtime_data_codex_audit/delete_3pages_audit.pdf'),'Summarize local studio delete test.')]
def page_set(text):
    pages=set()
    for match in re.finditer(r'\[(?:pages?|p\.?)\s*([\d,\s\-–]+)\]',text,re.I):
        for part in match.group(1).split(','):
            part=part.strip()
            if part.isdigit():pages.add(int(part))
            elif re.fullmatch(r'\d+\s*[-–]\s*\d+',part):
                first,last=map(int,re.split(r'\s*[-–]\s*',part));pages.update(range(first,last+1))
    return sorted(pages)
results=[]
for label,path,question in FILES:
    for i in range(1,4):
        with path.open('rb') as f:r=requests.post(BASE+'/api/ai/chat/stream',data={'question':question},files={'file':(path.name,f,'application/pdf')},timeout=30)
        tokens=[];done={}
        for block in r.text.strip().split('\n\n'):
            event=re.search(r'^event:\s*(.+)$',block,re.M); data=re.search(r'^data:\s*(.+)$',block,re.M)
            if not event or not data:continue
            payload=json.loads(data.group(1))
            if event.group(1)=='token':tokens.append(payload.get('text',''))
            elif event.group(1)=='replace':tokens=[payload.get('text','')]
            elif event.group(1)=='done':done=payload
        answer=''.join(tokens); inline=page_set(answer);chips=sorted(set(done.get('citations',[])))
        results.append({'doc':label,'run':i,'status':r.status_code,'inline_pages':inline,'chip_pages':chips,'counts':[len(inline),len(chips)],'match':inline==chips,'mode':done.get('mode')})
print(json.dumps(results,indent=2,ensure_ascii=False))
