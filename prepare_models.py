"""Fetch the pinned Pix2Text model with checksums; no network needed if installed."""
import hashlib
import json
import time
from pathlib import Path
import requests
from ocr_engine import FormulaOCR, MODEL_DIR

manifest=json.loads((Path(__file__).parent/'model-manifest.json').read_text())
MODEL_DIR.mkdir(parents=True,exist_ok=True)
for name, expected in manifest['sha256'].items():
    target=MODEL_DIR/name
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==expected:
        continue
    for attempt in range(3):
        temp=target.with_suffix('.download')
        try:
            print(f'下载本地模型：{name}（{attempt+1}/3）',flush=True)
            url=f"https://huggingface.co/{manifest['repository']}/resolve/{manifest['revision']}/{name}"
            with requests.get(url,stream=True,timeout=(20,90)) as response:
                response.raise_for_status()
                with temp.open('wb') as f:
                    for chunk in response.iter_content(1024*1024):f.write(chunk)
            if hashlib.sha256(temp.read_bytes()).hexdigest()!=expected:
                raise ValueError('模型校验失败，请重试下载')
            temp.replace(target)
            break
        except Exception:
            temp.unlink(missing_ok=True)
            if attempt==2:raise
            time.sleep(2)
FormulaOCR()
print('新版本地模型验证通过，可离线运行。')
