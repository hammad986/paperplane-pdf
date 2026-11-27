from pathlib import Path
import json,re,subprocess,sys,io
from pptx import Presentation
from PIL import Image,ImageOps
source=Path('/tmp/audit-input.pptx'); presentation=Presentation(str(source)); results=[]
for index,slide in enumerate(presentation.slides,1):
 pictures=[shape for shape in slide.shapes if shape.shape_type==13]
 if len(pictures)!=1:
  results.append({'slide':index,'picture_count':len(pictures),'status':'unexpected_picture_count'}); continue
 try:
  image=Image.open(io.BytesIO(pictures[0].image.blob)).convert('L')
  if max(image.size)<1600: image=image.resize((image.width*2,image.height*2))
  buffer=io.BytesIO(); image.save(buffer,format='PNG')
  proc=subprocess.run(['tesseract','stdin','stdout','--psm','6'],input=buffer.getvalue(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=True)
  text=proc.stdout.decode('utf-8','replace')
  expected=f'Page {index} of 69'
  normalized=re.sub(r'\s+',' ',text)
  found=expected.lower() in normalized.lower() or (re.search(rf'page\s*{index}\s*of\s*69',normalized,re.I) is not None)
  results.append({'slide':index,'picture_count':1,'image_dimensions':list(image.size),'expected_marker':expected,'marker_found_by_ocr':bool(found),'text_sample':normalized[:140]})
 except Exception as e: results.append({'slide':index,'status':'ocr_error','error':repr(e)})
report={'pptx':str(source),'slides':len(presentation.slides),'page_markers_ocr_matched':sum(1 for r in results if r.get('marker_found_by_ocr')),'results':results,'all_69_markers':len(results)==69 and all(r.get('marker_found_by_ocr') for r in results)}
Path('/tmp/audit-pptx-ocr.json').write_text(json.dumps(report,indent=2),encoding='utf-8'); print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2));
if not report['all_69_markers']: sys.exit(3)
