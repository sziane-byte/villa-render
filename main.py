"""
Villa Compliance — PDF render/crop service
Deploy on Azure Container Apps (scales to zero).

Endpoints:
  POST /render  -> rasterize every page to high-DPI PNG, return base64 + thumbnails
  POST /crop    -> return one high-DPI region of one page (for hard-to-read fields)
  GET  /health  -> liveness

No cloud storage dependency: images are returned as base64 so n8n can pass them
straight to Gemini's inline_data. This keeps the service stateless and free-tier friendly.
For very large sets you can switch to Azure Blob; see README.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import fitz  # PyMuPDF
import base64
import io

app = FastAPI(title="villa-render", version="1.0")

# ---------- models ----------
class RenderIn(BaseModel):
    pdf_base64: str            # the PDF bytes, base64
    dpi: int = 250             # full-page DPI for extraction
    thumb_dpi: int = 90        # low DPI for the classifier
    max_pages: int = 60

class CropIn(BaseModel):
    pdf_base64: str
    page: int                  # 1-indexed
    bbox: List[float]          # [x0,y0,x1,y1] normalized 0..1
    dpi: int = 320

# ---------- helpers ----------
def _open(pdf_base64: str) -> fitz.Document:
    try:
        data = base64.b64decode(pdf_base64)
        return fitz.open(stream=data, filetype="pdf")
    except Exception as e:
        raise HTTPException(400, f"bad pdf_base64: {e}")

def _png(page: fitz.Page, dpi: int, clip: Optional[fitz.Rect] = None) -> str:
    m = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=m, clip=clip)
    return base64.b64encode(pix.tobytes("png")).decode()

# ---------- routes ----------
@app.get("/health")
def health():
    return {"ok": True}

@app.post("/render")
def render(inp: RenderIn):
    doc = _open(inp.pdf_base64)
    n = min(len(doc), inp.max_pages)
    pages = []
    for i in range(n):
        page = doc[i]
        pages.append({
            "index": i + 1,
            "width_pt": round(page.rect.width, 1),
            "height_pt": round(page.rect.height, 1),
            "full_png_b64": _png(page, inp.dpi),
            "thumb_png_b64": _png(page, inp.thumb_dpi),
        })
    doc.close()
    return {"page_count": n, "pages": pages}

@app.post("/render_thumbs")
def render_thumbs(inp: RenderIn):
    """Lighter call: thumbnails only, for the classifier step."""
    doc = _open(inp.pdf_base64)
    n = min(len(doc), inp.max_pages)
    thumbs = [{"index": i + 1, "thumb_png_b64": _png(doc[i], inp.thumb_dpi)} for i in range(n)]
    doc.close()
    return {"page_count": n, "thumbs": thumbs}

@app.post("/render_pages")
def render_pages(inp: RenderIn, indices: str = ""):
    """Return full-res PNGs for only the requested 1-indexed pages, e.g. indices=5,6,12."""
    doc = _open(inp.pdf_base64)
    want = [int(x) for x in indices.split(",") if x.strip().isdigit()]
    out = []
    for idx in want:
        if 1 <= idx <= len(doc):
            out.append({"index": idx, "full_png_b64": _png(doc[idx - 1], inp.dpi)})
    doc.close()
    return {"pages": out}

@app.post("/crop")
def crop(inp: CropIn):
    doc = _open(inp.pdf_base64)
    if not (1 <= inp.page <= len(doc)):
        raise HTTPException(400, "page out of range")
    page = doc[inp.page - 1]
    r = page.rect
    x0, y0, x1, y1 = inp.bbox
    clip = fitz.Rect(r.width * x0, r.height * y0, r.width * x1, r.height * y1)
    png = _png(page, inp.dpi, clip=clip)
    doc.close()
    return {"page": inp.page, "crop_png_b64": png}
