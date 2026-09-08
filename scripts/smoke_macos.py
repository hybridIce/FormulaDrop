import io,json,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
import requests
with tempfile.TemporaryDirectory() as tmp:
 portfile=Path(tmp)/'port.json'
 proc=subprocess.Popen([str(Path(sys.argv[1]).resolve()),'--port-file',str(portfile)])
 try:
  for _ in range(120):
   if proc.poll() is not None:raise RuntimeError('Bundled backend exited')
   try:
    port=json.loads(portfile.read_text())['port'];base=f'http://127.0.0.1:{port}'
    if requests.get(base+'/api/health',timeout=1).json()['status']=='ready':break
   except (OSError,ValueError,requests.RequestException):pass
   time.sleep(.5)
  else:raise RuntimeError('Backend startup timed out')
  with open('static/examples/2.png','rb') as image:r=requests.post(base+'/api/recognize',files={'file':('formula.png',image,'image/png')},timeout=30)
  r.raise_for_status();latex=r.json()['latex'];assert '\\pi' in latex and '0' in latex,latex
  r=requests.post(base+'/api/word',json={'latex':latex},timeout=10);r.raise_for_status()
  with zipfile.ZipFile(io.BytesIO(r.content)) as z:assert b'<m:oMath>' in z.read('word/document.xml')
  print('PASS: macOS bundled OCR and editable Word export',latex)
 finally:
  proc.terminate()
  try:proc.wait(timeout=10)
  except subprocess.TimeoutExpired:proc.kill();proc.wait()
