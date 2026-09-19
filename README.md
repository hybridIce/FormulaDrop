# FormulaDrop

免费的本地公式截图识别 App。鼠标拖动框选，识别为 LaTeX、MathML，或导出可编辑公式的 Word 文档。模型随下载包提供，日常识别无需联网、无需 API Key。

## 下载

[下载 macOS / Windows 版本](https://github.com/hybridIce/FormulaDrop/releases/latest)

- **macOS Apple Silicon（arm64）**：解压后将 FormulaDrop.app 拖到“应用程序”。截图需授予屏幕录制权限。应用未经过 Apple 公证，首次打开可能需要在系统设置的“隐私与安全性”中允许。
- **Windows 10/11 x64**：解压完整文件夹，运行 FormulaDrop.exe。需要 [Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)；如有 DLL 加载错误，安装 [Microsoft Visual C++ x64 Runtime](https://aka.ms/vs/17/release/vc_redist.x64.exe)。Python、.NET 和模型已内置。

点击“截图”，拖动选择公式，松开鼠标即可识别；Esc 取消。也支持上传或粘贴图片。使用“复制”选择 LaTeX / MathML，或直接导出 Word 文档。首次启动会预热模型，复杂、模糊、手写公式可能识别错误，请核对结果。

识别结果可以直接修改，预览与导出同步更新。**在 WPS 打开**会生成原生可编辑公式文档；在 WPS 中全选、复制，再粘贴到目标文档。网页版本会下载 `.docx`。WPS 对网页 MathML 剪贴板的支持不完整，因此此按钮不再直接复制网页富文本。1.0.4 修正了导出时丢失上标、运算符及根号显示异常的问题。

## 效果图

![FormulaDrop 主界面](screenshots/formuladrop-main.png)

![公式编辑与 WPS 导出](screenshots/formuladrop-wps.png)

## 从源码运行

需要 Python 3.10。

```sh
python -m venv .venv
# 激活虚拟环境后：
pip install -r requirements.txt
python prepare_models.py
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

打开 http://127.0.0.1:8765 。Mac 与 Windows 桌面 App 都可点击“截图”拖动框选；Windows 网页版需粘贴或上传截图。Mac App 内截图需要 macOS 14 或更新版本。

Windows 的完整构建、打包与 OCR / Word 验证流程见 `.github/workflows/windows.yml`。原生前端分别位于 `desktop/App.swift` 和 `desktop/windows/`。Windows 验证不包含人工操作、多显示器或不同缩放比例的截图测试。

macOS 构建使用 `scripts/build_macos.sh`。设置 `FORMULADROP_SIGNING_IDENTITY` 可在更新时复用已有签名证书；不设置则使用临时签名，更新后可能需要重新授予屏幕录制权限。保持相同 App 名称并不能保证系统将不同签名的版本视作同一个应用。

## 模型与许可

使用 [Pix2Text MFR 1.5](https://huggingface.co/breezedeus/pix2text-mfr-1.5) 与 ONNX Runtime。模型版本记录在 `model-manifest.json`，不将模型权重提交到 Git。

项目代码采用 MIT 许可。第三方组件保留各自许可，见 [THIRD_PARTY.md](THIRD_PARTY.md)。
