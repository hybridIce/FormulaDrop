import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var web: WKWebView!
    var backend: Process?
    var startupTimer: Timer?
    var port: Int = 0
    var launchDirectory: URL!
    var logHandle: FileHandle?
    var attempts = 0
    var regionCapture: AnyObject?
    var captureActive = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        let main = NSMenu()
        let appItem = NSMenuItem(); main.addItem(appItem)
        let appMenu = NSMenu(); appItem.submenu = appMenu
        appMenu.addItem(withTitle: "关于 FormulaDrop", action: #selector(about), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "隐藏 FormulaDrop", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "退出 FormulaDrop", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let editItem = NSMenuItem(); main.addItem(editItem)
        let edit = NSMenu(title: "编辑"); editItem.submenu = edit
        edit.addItem(withTitle: "撤销", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "剪切", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "复制", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "粘贴", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        NSApp.mainMenu = main

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1080, height: 760), styleMask: [.titled,.closable,.miniaturizable,.resizable], backing: .buffered, defer: false)
        window.title = "FormulaDrop"
        window.minSize = NSSize(width: 720, height: 540)
        window.setFrameAutosaveName("FormulaDropWindow")
        window.center()
        let config = WKWebViewConfiguration()
        config.userContentController.add(self, name: "formulaNative")
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self; web.uiDelegate = self
        window.contentView = web
        web.loadHTMLString("<body style='background:#f7f8f6;color:#28644f;font:16px -apple-system;display:grid;place-items:center;height:90vh'><div>正在启动 FormulaDrop…</div></body>", baseURL: nil)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        startBackend()
    }
    @objc func about() {
        NSApp.orderFrontStandardAboutPanel(options: [.applicationName:"FormulaDrop", .applicationVersion:Bundle.main.object(forInfoDictionaryKey:"CFBundleShortVersionString") as? String ?? "", .credits:NSAttributedString(string:"本地公式识别 · 截图转 LaTeX / Word / WPS\nPix2Text MFR 1.5 · ONNX Runtime")])
    }
    func startBackend() {
        do {
            launchDirectory = FileManager.default.temporaryDirectory.appendingPathComponent("FormulaDrop-" + UUID().uuidString)
            try FileManager.default.createDirectory(at: launchDirectory, withIntermediateDirectories: true)
            let logURL = launchDirectory.appendingPathComponent("backend.log")
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
            logHandle = try FileHandle(forWritingTo: logURL)
            let process = Process()
            guard let resources = Bundle.main.resourceURL else { throw NSError(domain:"FormulaDrop",code:1) }
            process.executableURL = resources.appendingPathComponent("backend/formuladrop-server")
            process.arguments = ["--port-file",launchDirectory.appendingPathComponent("port.json").path]
            process.currentDirectoryURL = resources.appendingPathComponent("backend")
            process.standardOutput = logHandle; process.standardError = logHandle
            try process.run(); backend = process
            startupTimer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in self?.checkStartup() }
        } catch { showStartupError(error.localizedDescription) }
    }
    func checkStartup() {
        attempts += 1
        if backend?.isRunning == false { showStartupError("本地识别服务未能启动。"); return }
        if attempts > 200 { showStartupError("启动超时，请退出 App 后重试。"); return }
        let file = launchDirectory.appendingPathComponent("port.json")
        guard let data = try? Data(contentsOf: file), let info = (try? JSONSerialization.jsonObject(with:data)) as? [String:Int], let p = info["port"] else { return }
        port = p
        guard let url = URL(string:"http://127.0.0.1:\(p)/api/health") else { return }
        var request = URLRequest(url:url); request.timeoutInterval = 1
        URLSession.shared.dataTask(with:request) { [weak self] data, _, _ in
            guard let self = self, data != nil else { return }
            DispatchQueue.main.async {
                guard self.startupTimer != nil else { return }
                self.startupTimer?.invalidate(); self.startupTimer = nil
                self.web.load(URLRequest(url:URL(string:"http://127.0.0.1:\(p)/")!))
            }
        }.resume()
    }
    func showStartupError(_ message: String) {
        startupTimer?.invalidate(); startupTimer = nil
        let alert = NSAlert(); alert.messageText = "FormulaDrop 启动失败"; alert.informativeText = message + "\n日志：" + (launchDirectory?.appendingPathComponent("backend.log").path ?? "")
        alert.addButton(withTitle:"退出"); alert.runModal(); NSApp.terminate(nil)
    }
    func reply(_ id: String, data: Any? = nil, error: String? = nil) {
        let info: [String:Any] = ["id":id,"data":data ?? NSNull(),"error":error as Any? ?? NSNull()]
        if let data = try? JSONSerialization.data(withJSONObject:info), let json = String(data:data,encoding:.utf8) {
            web.evaluateJavaScript("window.formulaNativeReply && window.formulaNativeReply(\(json))", completionHandler:nil)
        }
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, let origin = message.frameInfo.request.url, origin.host == "127.0.0.1", origin.port == port,
              let body = message.body as? [String:Any], let id = body["id"] as? String, let action = body["action"] as? String else { return }
        switch action {
        case "capture":
            guard !captureActive else { reply(id,error:"请先完成当前截图。"); return }
            guard #available(macOS 14.0, *) else { reply(id,error:"App 内区域截图需要 macOS 14 或更新版本；请使用系统截图后粘贴。"); return }
            // ScreenCaptureKit is the authority for this capture. A separate
            // CGPreflight check can disagree with the current session's grant.
            captureActive = true
            window.orderOut(nil)
            DispatchQueue.main.asyncAfter(deadline:.now() + 0.18) { [weak self] in
                guard let self = self else { return }
                let capture = RegionCapture(); self.regionCapture = capture
                capture.start { [weak self] result in
                    guard let self = self else { return }
                    self.captureActive = false; self.regionCapture = nil
                    NSApp.unhide(nil); self.window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps:true)
                    switch result {
                    case .success(let png): self.reply(id, data: png)
                    case .failure(let error): self.reply(id,error:error.localizedDescription)
                    }
                }
            }
        case "copy":
            let text = body["text"] as? String ?? ""
            let board = NSPasteboard.general; board.clearContents()
            board.setString(text, forType:.string)
            if let html = body["html"] as? String { board.setString(html, forType:.html) }
            reply(id)
        case "save":
            guard let encoded = body["base64"] as? String, let data = Data(base64Encoded:encoded), data.count < 20_000_000 else { reply(id,error:"文档数据无效"); return }
            let panel = NSSavePanel(); panel.nameFieldStringValue = "formula.docx"; panel.allowedFileTypes = ["docx"]; panel.canCreateDirectories = true
            panel.beginSheetModal(for:window) { [weak self] result in
                guard let self = self else { return }
                if result != .OK { self.reply(id,error:"已取消保存"); return }
                do { try data.write(to:panel.url!,options:.atomic); self.reply(id) }
                catch { self.reply(id,error:"保存失败：" + error.localizedDescription) }
            }
        case "open-wps":
            guard let encoded = body["base64"] as? String, let data = Data(base64Encoded:encoded), data.count < 20_000_000 else { reply(id,error:"文档数据无效"); return }
            guard let wps = NSWorkspace.shared.urlForApplication(withBundleIdentifier:"com.kingsoft.wpsoffice.mac") else {
                reply(id,error:"未找到 WPS Office，请用 ↓ .docx 保存后手动打开。"); return
            }
            do {
                let directory = FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask)[0].appendingPathComponent("FormulaDrop/WPS",isDirectory:true)
                try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
                let file = directory.appendingPathComponent("公式-" + UUID().uuidString.prefix(8) + ".docx")
                try data.write(to:file,options:.atomic)
                let config = NSWorkspace.OpenConfiguration()
                NSWorkspace.shared.open([file],withApplicationAt:wps,configuration:config) { [weak self] _, error in
                    DispatchQueue.main.async {
                        if let error = error { self?.reply(id,error:"WPS 未能打开文档：" + error.localizedDescription) }
                        else { self?.reply(id) }
                    }
                }
            } catch { reply(id,error:"生成 WPS 文档失败：" + error.localizedDescription) }
        case "hide":
            NSApp.hide(nil)
            DispatchQueue.main.asyncAfter(deadline:.now() + 0.15) { [weak self] in self?.reply(id) }
        case "show":
            NSApp.unhide(nil); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps:true); reply(id)
        default: reply(id,error:"不支持的操作")
        }
    }
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel(); panel.allowedFileTypes = ["png","jpg","jpeg","webp","bmp"]; panel.allowsMultipleSelection = false
        panel.beginSheetModal(for:window) { response in completionHandler(response == .OK ? panel.urls : nil) }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if url.scheme == "about" || (url.host == "127.0.0.1" && url.port == port) { decisionHandler(.allow) }
        else { decisionHandler(.cancel) }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { !captureActive }
    func applicationWillTerminate(_ notification: Notification) {
        startupTimer?.invalidate()
        if let process = backend, process.isRunning { process.terminate() }
        try? logHandle?.close()
    }
}
@main struct FormulaDropMain {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        withExtendedLifetime(delegate) { app.run() }
    }
}
