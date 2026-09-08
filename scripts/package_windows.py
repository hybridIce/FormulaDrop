"""Assemble Windows x64 portable app using a Windows dotnet publish and wheels.
Can assemble on other hosts, but --smoke-test must run on Windows before release.
"""
import argparse
import hashlib
import shutil
import zipfile
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--publish',type=Path,required=True)
parser.add_argument('--wheels',type=Path,required=True)
parser.add_argument('--python-zip',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
args.output.mkdir(parents=True,exist_ok=True)
shutil.copytree(args.publish,args.output,dirs_exist_ok=True)
backend=args.output/'backend';runtime=backend/'python';runtime.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(args.python_zip) as archive:archive.extractall(runtime)
site=runtime/'Lib/site-packages';site.mkdir(parents=True,exist_ok=True)
for wheel in sorted(args.wheels.glob('*.whl')):
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            if member.is_dir():continue
            parts=Path(member.filename).parts
            if any(part=='..' for part in parts):raise ValueError('Unsafe wheel path')
            if parts[0].endswith('.data'):
                if parts[1] not in {'purelib','platlib'}:continue
                target=site.joinpath(*parts[2:])
            else:target=site/member.filename
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.read(member))
(runtime/'python310._pth').write_text('python310.zip\n.\nLib/site-packages\n..\nimport site\n')
for name in ['app.py','ocr_engine.py']:
    shutil.copy2(root/name,backend/name)
shutil.copy2(root/'desktop/server.py',backend/'server.py')
for name in ['models','static']:
    shutil.copytree(root/name,backend/name,dirs_exist_ok=True)
for name in ['LICENSE','THIRD_PARTY.md']:
    if (root/name).exists():shutil.copy2(root/name,args.output/name)
(args.output/'README.txt').write_text('FormulaDrop for Windows x64\n\n解压整个文件夹后双击 FormulaDrop.exe，不要只移动 exe。\n截图后可直接拖动框选，Esc 取消。\n内置 .NET、Python 和公式模型，日常识别离线运行。\n需 Windows 10/11 x64 与 Microsoft Edge WebView2 Runtime。\n若出现 DLL 加载失败，请安装 Microsoft Visual C++ 2015–2022 x64 Redistributable。\n模型：Pix2Text MFR 1.5；识别结果请核对。\n',encoding='utf-8')
# Avoid distributing build-machine source paths in debug symbols.
for p in args.output.glob('*.pdb'):p.unlink()
print('Packaged',args.output)
