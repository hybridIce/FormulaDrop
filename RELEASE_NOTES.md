# 1.0.4

- 修正 Word / WPS 文档中的上标丢失、max 等运算符消失，以及平方根多余次数占位。
- WPS 按钮改为“在 WPS 打开”：直接打开可编辑公式文档，可在 WPS 内复制到目标文档。网页版本下载 `.docx`，不再把不兼容的 MathML 网页剪贴板当作 WPS 原生公式。
- Mac 截图直接使用 ScreenCaptureKit 的实际读取结果，避免预检查误判权限；构建支持复用签名证书。
- 保留 LaTeX 编辑、实时预览、独立 Word 按钮和 Windows 鼠标框选截图。

macOS 上已验证 WPS 12.1 的分式、根式、上下标与矩阵显示及公式编辑状态。Windows 原生界面需另行验证；自动构建会检查内置 OCR 与 Office 文档导出。

Mac App 内截图需要 macOS 14 或更新版本。未公证或临时签名的构建可能需要在系统设置中允许打开及录屏。Windows 需要 Windows 10/11 x64 和 Microsoft Edge WebView2 Runtime。

项目代码 MIT 许可，第三方组件保留各自许可。
