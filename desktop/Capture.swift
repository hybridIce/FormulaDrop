import Cocoa
import ScreenCaptureKit

@available(macOS 14.0, *)
@MainActor final class RegionCapture {
    private var overlays: [NSWindow] = []
    private var completion: ((Result<String?, Error>) -> Void)?
    private var finished = false

    func start(completion: @escaping (Result<String?, Error>) -> Void) {
        self.completion = completion
        Task { @MainActor in
            do {
                let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
                var frames: [(NSScreen, CGImage)] = []
                for screen in NSScreen.screens {
                    guard let number = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber,
                          let display = content.displays.first(where: { $0.displayID == number.uint32Value }) else { continue }
                    let filter = SCContentFilter(display: display, excludingWindows: [])
                    let config = SCStreamConfiguration()
                    config.width = Int(screen.frame.width * screen.backingScaleFactor)
                    config.height = Int(screen.frame.height * screen.backingScaleFactor)
                    config.showsCursor = false
                    let frame = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
                    frames.append((screen, frame))
                }
                guard !frames.isEmpty else { throw NSError(domain: "FormulaDrop", code: 1, userInfo: [NSLocalizedDescriptionKey: "没有找到可截图的屏幕。"] ) }
                for (screen, image) in frames {
                    let overlay = CaptureWindow(contentRect: screen.frame, styleMask: .borderless, backing: .buffered, defer: false)
                    overlay.level = .screenSaver
                    overlay.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
                    overlay.isReleasedWhenClosed = false
                    let view = CaptureView(frame: NSRect(origin: .zero, size: screen.frame.size), image: image)
                    view.done = { [weak self] cropped in
                        guard let cropped = cropped else { self?.finish(.success(nil)); return }
                        guard let png = NSBitmapImageRep(cgImage: cropped).representation(using: .png, properties: [:]) else {
                            self?.finish(.failure(NSError(domain: "FormulaDrop", code: 2, userInfo: [NSLocalizedDescriptionKey: "截图编码失败。"] ))); return
                        }
                        self?.finish(.success(png.base64EncodedString()))
                    }
                    overlay.contentView = view
                    overlays.append(overlay)
                    overlay.makeKeyAndOrderFront(nil)
                    overlay.makeFirstResponder(view)
                }
                NSApp.activate(ignoringOtherApps: true)
            } catch {
                let failure = error as NSError
                if failure.domain == SCStreamErrorDomain && failure.code == SCStreamError.Code.userDeclined.rawValue {
                    finish(.failure(NSError(domain:"FormulaDrop",code:3,userInfo:[NSLocalizedDescriptionKey:"macOS 拒绝了本次屏幕读取。请在系统设置 → 隐私与安全性 → 录屏与系统录音中允许当前 FormulaDrop，然后完全退出并重新打开 App。"])))
                } else { finish(.failure(error)) }
            }
        }
    }
    private func finish(_ result: Result<String?, Error>) {
        guard !finished else { return }; finished = true
        for window in overlays { window.orderOut(nil); window.close() }
        overlays.removeAll()
        let callback = completion; completion = nil; callback?(result)
    }
}

private final class CaptureWindow: NSWindow {
    override var canBecomeKey: Bool { true }
}

private final class CaptureView: NSView {
    let image: CGImage
    var done: ((CGImage?) -> Void)?
    var anchor: NSPoint?
    var selection: NSRect = .zero
    override var acceptsFirstResponder: Bool { true }
    init(frame: NSRect, image: CGImage) { self.image = image; super.init(frame: frame) }
    required init?(coder: NSCoder) { fatalError("Not supported") }
    override func resetCursorRects() { addCursorRect(bounds, cursor: .crosshair) }
    override func draw(_ dirtyRect: NSRect) {
        NSImage(cgImage: image, size: bounds.size).draw(in: bounds)
        let shade = NSBezierPath(rect: bounds)
        shade.appendRect(selection); shade.windingRule = .evenOdd
        NSColor.black.withAlphaComponent(0.35).setFill(); shade.fill()
        if !selection.isEmpty { NSColor.white.setStroke(); let border = NSBezierPath(rect: selection); border.lineWidth = 1.5; border.stroke() }
        let hint = "拖动框选公式 · Esc 取消" as NSString
        hint.draw(at: NSPoint(x: 24, y: bounds.height - 48), withAttributes: [.foregroundColor: NSColor.white, .font: NSFont.systemFont(ofSize: 16)])
    }
    private func point(_ event: NSEvent) -> NSPoint {
        let p = convert(event.locationInWindow, from: nil)
        return NSPoint(x: max(0, min(bounds.width, p.x)), y: max(0, min(bounds.height, p.y)))
    }
    override func mouseDown(with event: NSEvent) { anchor = point(event); selection = .zero; needsDisplay = true }
    override func mouseDragged(with event: NSEvent) {
        guard let start = anchor else { return }; let end = point(event)
        selection = NSRect(x: min(start.x, end.x), y: min(start.y, end.y), width: abs(start.x-end.x), height: abs(start.y-end.y)); needsDisplay = true
    }
    override func mouseUp(with event: NSEvent) {
        guard anchor != nil else { return }; mouseDragged(with: event); anchor = nil
        guard selection.width >= 8, selection.height >= 8 else { return }
        let sx = CGFloat(image.width) / bounds.width, sy = CGFloat(image.height) / bounds.height
        let rect = CGRect(x: selection.minX * sx, y: (bounds.height-selection.maxY) * sy, width: selection.width * sx, height: selection.height * sy).integral
        done?(image.cropping(to: rect))
    }
    override func keyDown(with event: NSEvent) { if event.keyCode == 53 { done?(nil) } else { super.keyDown(with: event) } }
    override func rightMouseDown(with event: NSEvent) { done?(nil) }
}
