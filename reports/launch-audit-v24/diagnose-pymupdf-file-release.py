import sys,tempfile,shutil,gc
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import fitz
import security_forms_engine
root=Path(tempfile.mkdtemp()); path=root/'input.pdf'
doc=fitz.open();doc.new_page();doc.save(path);doc.close()
print('report',security_forms_engine.inspect_pdf_security(path)['page_count'])
try:
 shutil.rmtree(root)
 print('removed immediately')
except Exception as e:
 print('remove error immediately',type(e).__name__,str(e))
 gc.collect()
 try: shutil.rmtree(root);print('removed after gc')
 except Exception as e:print('remove error after gc',type(e).__name__,str(e))
