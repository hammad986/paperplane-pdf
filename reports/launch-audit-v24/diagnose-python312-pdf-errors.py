import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import fitz
from fastapi.testclient import TestClient
import server
client=TestClient(server.app)
doc=fitz.open(); doc.new_page(); valid=b'% leading comment\r\n'+doc.tobytes(); doc.close()
for name,data in [('valid.pdf',valid),('corrupt.pdf',b'%PDF-1.7\nnot a parseable PDF')]:
 r=client.post('/api/studio/security/inspect',files={'file':(name,data,'application/pdf')})
 print(name,r.status_code,r.text[:500])
