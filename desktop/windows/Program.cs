using System.Diagnostics;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Text;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace FormulaDropDesktop;

internal static class Program
{
    [STAThread]
    static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        // CI exercises the actual bundled Windows backend without requiring a desktop.
        if (args.Contains("--smoke-test")) { Environment.Exit(SmokeTest.Run()); return; }
        Application.Run(new MainWindow());
    }
}

internal sealed class Backend : IDisposable
{
    public string DirectoryPath { get; } = Path.Combine(Path.GetTempPath(), "FormulaDrop-" + Guid.NewGuid().ToString("N"));
    private Process? process;
    private readonly object logLock = new();
    public async Task<int> StartAsync(CancellationToken cancellation)
    {
        Directory.CreateDirectory(DirectoryPath);
        string root = Path.Combine(AppContext.BaseDirectory, "backend");
        var start = new ProcessStartInfo(Path.Combine(root, "python", "python.exe")) {
            WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardOutput = true, RedirectStandardError = true
        };
        start.ArgumentList.Add(Path.Combine(root, "server.py"));
        start.ArgumentList.Add("--port-file"); start.ArgumentList.Add(Path.Combine(DirectoryPath, "port.json"));
        process = new Process { StartInfo = start };
        void Log(object _, DataReceivedEventArgs e) { if (e.Data != null) lock (logLock) File.AppendAllText(Path.Combine(DirectoryPath, "backend.log"), e.Data + Environment.NewLine); }
        process.OutputDataReceived += Log; process.ErrorDataReceived += Log;
        process.Start(); process.BeginOutputReadLine(); process.BeginErrorReadLine();
        using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(1) };
        for (int i = 0; i < 200; i++) {
            cancellation.ThrowIfCancellationRequested();
            if (process.HasExited) throw new Exception("本地识别服务启动失败。日志：" + DirectoryPath);
            try {
                string portFile = Path.Combine(DirectoryPath, "port.json");
                if (File.Exists(portFile)) {
                    int port = JsonDocument.Parse(await File.ReadAllTextAsync(portFile, cancellation)).RootElement.GetProperty("port").GetInt32();
                    var response = await http.GetAsync($"http://127.0.0.1:{port}/api/health", cancellation);
                    if (response.IsSuccessStatusCode) return port;
                }
            } catch (Exception e) when (e is IOException or JsonException or HttpRequestException or TaskCanceledException) { cancellation.ThrowIfCancellationRequested(); }
            await Task.Delay(200, cancellation);
        }
        throw new Exception("启动超时。日志：" + DirectoryPath);
    }
    public void Dispose() { try { if (process is { HasExited: false }) process.Kill(entireProcessTree: true); } catch { } process?.Dispose(); }
}

internal sealed class MainWindow : Form
{
    private readonly WebView2 web = new() { Dock = DockStyle.Fill, DefaultBackgroundColor = Color.FromArgb(247, 248, 246) };
    private readonly Backend backend = new();
    private readonly CancellationTokenSource shutdown = new();
    private string origin = "";
    private bool capturing;
    public MainWindow()
    {
        Text = "FormulaDrop"; ClientSize = new Size(1080, 760); MinimumSize = new Size(740, 560);
        StartPosition = FormStartPosition.CenterScreen;
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        Controls.Add(new Label { Text = "正在启动 FormulaDrop…", Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter, Font = new Font("Microsoft YaHei UI", 12) });
        Shown += async (_, _) => await InitializeAsync();
        FormClosed += (_, _) => { shutdown.Cancel(); backend.Dispose(); shutdown.Dispose(); };
    }
    private async Task InitializeAsync()
    {
        try {
            string data = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "FormulaDrop", "WebView2");
            var environment = await CoreWebView2Environment.CreateAsync(null, data);
            await web.EnsureCoreWebView2Async(environment);
            web.CoreWebView2.Settings.IsStatusBarEnabled = false;
            web.CoreWebView2.Settings.AreDevToolsEnabled = false;
            web.CoreWebView2.WebMessageReceived += HandleMessage;
            web.CoreWebView2.NewWindowRequested += (_, e) => e.Handled = true;
            web.CoreWebView2.NavigationStarting += (_, e) => { if (!e.Uri.StartsWith(origin + "/", StringComparison.Ordinal) && e.Uri != "about:blank") e.Cancel = true; };
            int port = await backend.StartAsync(shutdown.Token);
            origin = $"http://127.0.0.1:{port}";
            Controls.Clear(); Controls.Add(web);
            web.CoreWebView2.Navigate(origin + "/");
        } catch (OperationCanceledException) { }
        catch (WebView2RuntimeNotFoundException) {
            MessageBox.Show("需要 Microsoft Edge WebView2 Runtime。请从 Microsoft 官网安装后重新打开 App：\nhttps://developer.microsoft.com/microsoft-edge/webview2/", "FormulaDrop"); Close();
        } catch (Exception e) { MessageBox.Show(e.Message, "FormulaDrop 启动失败"); Close(); }
    }
    private void Reply(string id, object? data = null, string? error = null)
    {
        if (IsDisposed || web.CoreWebView2 == null) return;
        string json = JsonSerializer.Serialize(new { id, data, error });
        _ = web.CoreWebView2.ExecuteScriptAsync($"window.formulaNativeReply && window.formulaNativeReply({json})");
    }
    private async void HandleMessage(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        if (!e.Source.StartsWith(origin + "/", StringComparison.Ordinal)) return;
        string id = "";
        try {
            using var document = JsonDocument.Parse(e.WebMessageAsJson);
            var request = document.RootElement;
            id = request.GetProperty("id").GetString()!;
            string action = request.GetProperty("action").GetString()!;
            switch (action) {
                case "copy":
                    var clipboard = new DataObject();
                    clipboard.SetData(DataFormats.UnicodeText, request.GetProperty("text").GetString() ?? "");
                    if (request.TryGetProperty("html", out var html)) clipboard.SetData(DataFormats.Html, ClipboardHtml(html.GetString()!));
                    Clipboard.SetDataObject(clipboard, true); Reply(id); break;
                case "save":
                    byte[] bytes = Convert.FromBase64String(request.GetProperty("base64").GetString()!);
                    if (bytes.Length > 20_000_000) throw new Exception("文档过大");
                    using (var dialog = new SaveFileDialog { FileName = "formula.docx", Filter = "Word 文档 (*.docx)|*.docx", DefaultExt = "docx", AddExtension = true }) {
                        if (dialog.ShowDialog(this) != DialogResult.OK) { Reply(id, error: "已取消保存"); break; }
                        await File.WriteAllBytesAsync(dialog.FileName, bytes); Reply(id);
                    }
                    break;
                case "capture":
                    if (capturing) { Reply(id, error: "请先完成当前截图"); break; }
                    capturing = true;
                    try {
                        Hide(); await Task.Delay(160);
                        using var overlay = new CaptureOverlay();
                        string? encoded = null;
                        if (overlay.ShowDialog() == DialogResult.OK && overlay.Cropped != null) {
                            using var stream = new MemoryStream(); overlay.Cropped.Save(stream, ImageFormat.Png);
                            encoded = Convert.ToBase64String(stream.ToArray());
                        }
                        Show(); Activate(); Reply(id, encoded);
                    } finally { capturing = false; if (!IsDisposed) { Show(); Activate(); } }
                    break;
                default: Reply(id, error: "不支持的操作"); break;
            }
        } catch (Exception ex) { Reply(id, error: "操作未完成：" + ex.Message); }
    }
    // CF_HTML byte offsets must count UTF-8 bytes, including Chinese text.
    private static string ClipboardHtml(string fragment)
    {
        const string template = "Version:0.9\r\nStartHTML:{0:0000000000}\r\nEndHTML:{1:0000000000}\r\nStartFragment:{2:0000000000}\r\nEndFragment:{3:0000000000}\r\n";
        string header = string.Format(template, 0, 0, 0, 0);
        string prefix = "<html><body><!--StartFragment-->";
        string suffix = "<!--EndFragment--></body></html>";
        int start = Encoding.UTF8.GetByteCount(header), fragmentStart = start + Encoding.UTF8.GetByteCount(prefix);
        int fragmentEnd = fragmentStart + Encoding.UTF8.GetByteCount(fragment), end = fragmentEnd + Encoding.UTF8.GetByteCount(suffix);
        return string.Format(template, start, end, fragmentStart, fragmentEnd) + prefix + fragment + suffix;
    }
}

internal sealed class CaptureOverlay : Form
{
    private readonly Bitmap screenshot;
    private Point? anchor;
    private Rectangle selection;
    public Bitmap? Cropped { get; private set; }
    public CaptureOverlay()
    {
        var bounds = SystemInformation.VirtualScreen;
        FormBorderStyle = FormBorderStyle.None; StartPosition = FormStartPosition.Manual;
        Bounds = bounds; TopMost = true; ShowInTaskbar = false; DoubleBuffered = true;
        Cursor = Cursors.Cross; KeyPreview = true;
        screenshot = new Bitmap(bounds.Width, bounds.Height, PixelFormat.Format32bppArgb);
        using (var g = Graphics.FromImage(screenshot)) g.CopyFromScreen(bounds.Location, Point.Empty, bounds.Size);
        KeyDown += (_, e) => { if (e.KeyCode == Keys.Escape) { DialogResult = DialogResult.Cancel; Close(); } };
        MouseDown += (_, e) => { if (e.Button == MouseButtons.Left) { anchor = e.Location; Capture = true; } };
        MouseMove += (_, e) => {
            if (anchor is not Point p) return;
            int x = Math.Clamp(e.X, 0, screenshot.Width), y = Math.Clamp(e.Y, 0, screenshot.Height);
            selection = Rectangle.FromLTRB(Math.Min(p.X, x), Math.Min(p.Y, y), Math.Max(p.X, x), Math.Max(p.Y, y)); Invalidate();
        };
        MouseUp += (_, e) => {
            if (e.Button != MouseButtons.Left || anchor == null) return;
            Capture = false; anchor = null;
            if (selection.Width < 8 || selection.Height < 8) return;
            Cropped = screenshot.Clone(selection, PixelFormat.Format32bppArgb); DialogResult = DialogResult.OK; Close();
        };
    }
    protected override void OnPaint(PaintEventArgs e)
    {
        e.Graphics.DrawImageUnscaled(screenshot, 0, 0);
        using var shade = new SolidBrush(Color.FromArgb(95, Color.Black));
        using var region = new Region(ClientRectangle);
        if (!selection.IsEmpty) region.Exclude(selection);
        e.Graphics.FillRegion(shade, region);
        if (!selection.IsEmpty) { using var pen = new Pen(Color.White, 2) { DashStyle = DashStyle.Dash }; e.Graphics.DrawRectangle(pen, selection); }
        TextRenderer.DrawText(e.Graphics, "拖动框选公式 · Esc 取消", SystemFonts.MessageBoxFont, new Point(24, 24), Color.White, Color.FromArgb(40, 60, 48));
    }
    protected override void Dispose(bool disposing) { if (disposing) { screenshot.Dispose(); Cropped?.Dispose(); } base.Dispose(disposing); }
}

internal static class SmokeTest
{
    public static int Run()
    {
        try {
            using var backend = new Backend();
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
            int port = backend.StartAsync(timeout.Token).GetAwaiter().GetResult();
            using var http = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}"), Timeout = TimeSpan.FromSeconds(30) };
            for (int i = 0; i < 90; i++) {
                var h = JsonDocument.Parse(http.GetStringAsync("/api/health").Result).RootElement;
                if (h.GetProperty("status").GetString() == "ready") break;
                Thread.Sleep(500);
            }
            using var form = new MultipartFormDataContent();
            var image = File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "backend", "static", "examples", "2.png"));
            form.Add(new ByteArrayContent(image), "file", "formula.png");
            var r = http.PostAsync("/api/recognize", form).Result; r.EnsureSuccessStatusCode();
            string latex = JsonDocument.Parse(r.Content.ReadAsStringAsync().Result).RootElement.GetProperty("latex").GetString()!;
            if (!latex.Contains("\\pi") || !latex.Contains("0")) throw new Exception("Unexpected OCR output: " + latex);
            var word = http.PostAsync("/api/word", new StringContent(JsonSerializer.Serialize(new { latex }), Encoding.UTF8, "application/json")).Result;
            word.EnsureSuccessStatusCode();
            using var archive = new System.IO.Compression.ZipArchive(new MemoryStream(word.Content.ReadAsByteArrayAsync().Result));
            using var reader = new StreamReader(archive.GetEntry("word/document.xml")!.Open());
            if (!reader.ReadToEnd().Contains("<m:oMath>")) throw new Exception("Word output is not editable math");
            File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "smoke-result.txt"), "PASS: Windows bundled OCR and editable Word export\n" + latex); return 0;
        } catch (Exception ex) { File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "smoke-result.txt"), ex.ToString()); return 1; }
    }
}
