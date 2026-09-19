#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
test "$(uname -m)" = arm64
python -m PyInstaller --noconfirm --clean --onedir --name formuladrop-server --paths "$PWD" --add-data "$PWD/static:static" --add-data "$PWD/models:models" --collect-data latex2mathml --collect-data docx --collect-data mathml2omml --exclude-module matplotlib --exclude-module scipy --exclude-module pandas --exclude-module tkinter --exclude-module IPython desktop/server.py
bundle=dist/FormulaDrop.app
mkdir -p "$bundle/Contents/MacOS" "$bundle/Contents/Resources"
swiftc desktop/App.swift desktop/Capture.swift -o "$bundle/Contents/MacOS/FormulaDrop" -framework Cocoa -framework WebKit -framework ScreenCaptureKit
cp desktop/macos/Info.plist "$bundle/Contents/Info.plist"
ditto dist/formuladrop-server "$bundle/Contents/Resources/backend"
cp LICENSE THIRD_PARTY.md "$bundle/Contents/Resources/"
python - <<'PY'
from PIL import Image
from pathlib import Path
p=Path('build/AppIcon.iconset');p.mkdir(parents=True,exist_ok=True)
im=Image.open('desktop/windows/AppIcon.ico').convert('RGBA')
for size in [16,32,128,256,512]:
 for scale in [1,2]:
  im.resize((size*scale,size*scale),Image.Resampling.LANCZOS).save(p/f'icon_{size}x{size}{"@2x" if scale==2 else ""}.png')
PY
iconutil -c icns build/AppIcon.iconset -o "$bundle/Contents/Resources/AppIcon.icns"
# Reuse the same certificate across local updates. Never weaken the designated
# requirement to the bundle identifier alone; it would accept unrelated code.
# Unsigned public builds can still use ad-hoc signing, but may need a new grant.
codesign --force --deep --sign "${FORMULADROP_SIGNING_IDENTITY:--}" "$bundle"
codesign --verify --deep --strict "$bundle"
python scripts/smoke_macos.py "$bundle/Contents/Resources/backend/formuladrop-server"
ditto -c -k --sequesterRsrc --keepParent "$bundle" dist/FormulaDrop-macOS-arm64.zip
