import fitz,tempfile,gc
from pathlib import Path
p=Path(tempfile.mktemp(suffix='.pdf'))
p.write_bytes(b'%PDF-1.7\nnot a parseable PDF')
try:
    fitz.open(str(p))
except Exception as e:
    print(type(e).__name__, str(e))
for label in ('immediate','gc'):
    try:
        if label=='gc': gc.collect()
        p.unlink()
        print('removed', label)
        break
    except Exception as e:
        print('remove failed',label,type(e).__name__,str(e))
