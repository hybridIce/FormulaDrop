"""FormulaDrop: local formula recognition. Run with launcher.py."""
import asyncio
import io
import logging
import threading
import subprocess
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

import latex2mathml.converter
import mathml2omml
from docx import Document
from docx.oxml import parse_xml
from lxml import etree
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
LIMIT = 12 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 16_000_000
engine = None
state = {"status": "loading", "message": "正在加载本地识别模型…"}
lock = threading.Lock()
capture_lock = threading.Lock()


def load_engine():
    global engine
    try:
        from ocr_engine import FormulaOCR
        engine = FormulaOCR()
        state.update(status="ready", message="本地模型已就绪", engine=engine.name)
    except Exception:
        logging.exception("Model initialization failed")
        state.update(status="error", message="模型加载失败，请查看启动窗口；联网重新运行 setup.command 可重新安装。")


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(asyncio.to_thread(load_engine))
    yield
    await task


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def local_only(request: Request, call_next):
    if request.method == "POST":
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return Response("Origin not allowed", status_code=403)
        try:
            if int(request.headers.get("content-length", "0")) > LIMIT + 65536:
                return Response("图片过大，请使用 12 MB 以内的图片。", status_code=413)
        except ValueError:
            return Response(status_code=400)
    response = await call_next(request)
    if request.url.path in {"/", "/static/app.js", "/static/style.css"}:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index():
    return FileResponse(ROOT / "static/index.html")


@app.get("/api/health")
def health():
    return {"app": "FormulaDrop", **state}


@app.post("/api/capture")
def capture(request: Request):
    # A custom header prevents third-party pages from issuing a simple request.
    # Cross-origin preflight is intentionally not enabled for this local app.
    if request.headers.get("x-formuladrop-capture") != "1":
        raise HTTPException(403, "请通过页面上的截图按钮启动截图。")
    if sys.platform != "darwin":
        raise HTTPException(501, "一键截图目前支持 macOS，其他系统请粘贴或上传截图。")
    if not capture_lock.acquire(blocking=False):
        raise HTTPException(409, "截图已打开，请完成框选或按 Esc 取消。")
    try:
        with tempfile.TemporaryDirectory(prefix="formuladrop-capture-") as directory:
            target = Path(directory) / "formula.png"
            try:
                result = subprocess.run(
                    ["/usr/sbin/screencapture", "-i", "-s", "-x", "-t", "png", str(target)],
                    capture_output=True, timeout=120,
                )
            except subprocess.TimeoutExpired:
                raise HTTPException(408, "截图等待超时，请重新点击截图按钮。")
            except OSError:
                raise HTTPException(503, "无法启动系统截图，请使用系统快捷键截图后粘贴。")
            if not target.exists() or target.stat().st_size == 0:
                if result.stderr.strip():
                    raise HTTPException(403, "系统未能完成截图。请在系统设置 → 隐私与安全性 → 屏幕录制中允许启动此工具的应用（终端或 Codex），然后重启工具。")
                return Response(status_code=204)
            if result.returncode != 0:
                raise HTTPException(503, "系统截图失败，请重试。")
            data = target.read_bytes()
            if len(data) > LIMIT:
                raise HTTPException(413, "截图过大，请重新框选更小的公式区域。")
            return Response(data, media_type="image/png", headers={"Cache-Control": "no-store"})
    finally:
        capture_lock.release()


@app.post("/api/recognize")
def recognize(file: UploadFile = File(...)):
    started = time.perf_counter()
    if engine is None:
        raise HTTPException(503, state["message"])
    if not lock.acquire(blocking=False):
        raise HTTPException(429, "正在识别另一张图片，请稍后再试。")
    try:
        raw = file.file.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise HTTPException(413, "图片不能超过 12 MB。")
        try:
            pic = Image.open(io.BytesIO(raw))
            if pic.width * pic.height > 16_000_000:
                raise HTTPException(413, "图片尺寸过大，请先裁剪到公式区域。")
            if pic.format not in {"PNG", "JPEG", "WEBP", "BMP"}:
                raise HTTPException(415, "请使用 PNG、JPEG、WebP 或 BMP 图片。")
            pic = ImageOps.exif_transpose(pic).convert("RGBA")
            bg = Image.new("RGBA", pic.size, "white")
            bg.alpha_composite(pic)
            pic = bg.convert("RGB")
            gray = pic.convert("L")
            if ImageStat.Stat(gray).stddev[0] < 1:
                raise HTTPException(422, "图片中没有可辨认的内容，请重新截取公式。")
            # Normalize dark screenshots before model preprocessing.
            if ImageStat.Stat(gray).mean[0] < 110:
                pic = ImageOps.invert(pic)
            pic.thumbnail((2400, 1600))
            buffer = io.BytesIO()
            pic.save(buffer, format="PNG")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(422, "无法读取图片，请重新保存为 PNG 或 JPG。")
        result, elapsed = engine(buffer.getvalue())
        if not result.strip():
            raise HTTPException(422, "未识别到公式，请裁剪到单个清晰公式后重试。")
        return {"latex": result, "seconds": round(time.perf_counter()-started, 2), "inference_seconds": round(elapsed, 2), "cached": engine.last_cached, "engine": engine.name}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception:
        logging.exception("Recognition failed")
        raise HTTPException(422, "识别失败，请裁剪到一个清晰的印刷公式后重试。")
    finally:
        file.file.close()
        lock.release()


class Formula(BaseModel):
    latex: str = Field(min_length=1, max_length=12000)


def mathml(latex):
    try:
        return latex2mathml.converter.convert(latex.strip(), display="block")
    except Exception:
        raise HTTPException(422, "公式暂时无法转换，请检查 LaTeX 语法。")


def office_math(latex):
    """Use simple OMML arguments that WPS and Word both preserve on import."""
    mml_ns = "http://www.w3.org/1998/Math/MathML"
    office_ns = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    word_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    source = etree.fromstring(mathml(latex).encode())
    # latex2mathml represents display-style movable limits as ordinary scripts.
    for node in source.iter():
        replacement = {"msub": "munder", "msup": "mover", "msubsup": "munderover"}.get(etree.QName(node).localname)
        if (replacement and len(node) and node[0].get("movablelimits") == "true"
                and not any(p.get("displaystyle") == "false" for p in node.iterancestors())):
            node.tag = f"{{{mml_ns}}}{replacement}"
    converted = mathml2omml.convert(etree.tostring(source, encoding="unicode"))
    root = parse_xml(f'<m:oMathPara xmlns:m="{office_ns}" xmlns:w="{word_ns}">{converted}</m:oMathPara>')
    ns = {"m": office_ns}
    # mathml2omml adds a box around every mrow. WPS loses superscripts and
    # operator text inside these unnecessary wrappers (including max and lim).
    for box in reversed(root.xpath(".//m:box", namespaces=ns)):
        if len(box) != 1 or box[0].tag != f"{{{office_ns}}}e":
            continue
        parent = box.getparent()
        index = parent.index(box)
        for child in list(box[0]):
            parent.insert(index, child)
            index += 1
        parent.remove(box)
    for radical in root.xpath(".//m:rad[not(m:deg)]", namespaces=ns):
        props = etree.Element(f"{{{office_ns}}}radPr")
        etree.SubElement(props, f"{{{office_ns}}}degHide", {f"{{{office_ns}}}val": "1"})
        radical.insert(0, props)
        radical.insert(1, etree.Element(f"{{{office_ns}}}deg"))
    for run in root.xpath(".//m:r", namespaces=ns):
        props = etree.Element(f"{{{word_ns}}}rPr")
        etree.SubElement(props, f"{{{word_ns}}}rFonts", {
            f"{{{word_ns}}}ascii": "Cambria Math", f"{{{word_ns}}}hAnsi": "Cambria Math"})
        run.insert(1 if run.find("m:rPr", ns) is not None else 0, props)
    return root


@app.post("/api/mathml")
def convert_formula(body: Formula):
    return {"mathml": mathml(body.latex)}


@app.post("/api/word")
def export_word(body: Formula):
    try:
        doc = Document()
        doc.add_paragraph()._p.append(office_math(body.latex))
        out = io.BytesIO()
        doc.save(out)
        return Response(out.getvalue(), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": 'attachment; filename="formula.docx"'})
    except HTTPException:
        raise
    except Exception:
        logging.exception("Word conversion failed")
        raise HTTPException(422, "该公式含暂不支持的 Word 转换语法，可复制 LaTeX 到 Word 的公式框中。")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
