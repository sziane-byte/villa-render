"""
Villa Compliance — PDF render/crop service (file-upload, low-memory design) v2.1
Flow:
  POST /upload   (multipart file)         -> stores PDF, returns {job_id, page_count, thumbs[]}
  POST /pages    {job_id, indices, dpi}   -> high-res PNGs for those pages
  POST /text     {job_id, indices}        -> embedded text layer for those pages
  POST /crop     {job_id, page, bbox,dpi} -> one high-res region
  GET  /health
  GET  /job/{job_id}                      -> {exists, page_count}
n8n uploads the raw PDF ONCE (no base64 in n8n memory). The service keeps the file
on local disk keyed by job_id, so later calls only send the job_id + page numbers.
"""
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List
import fitz  # PyMuPDF
import base64
import os
import time
import uuid

app = FastAPI(title="villa-render", version="2.1")

STORE_DIR = "/tmp/villa_jobs"
JOB_TTL = 3600
os.makedirs(STORE_DIR, exist_ok=True)


class PagesIn(BaseModel):
    job_id: str
    indices: List[int] = []
    dpi: int = 250


class TextIn(BaseModel):
    job_id: str
    indices: List[int] = []


class CropIn(BaseModel):
    job_id: str
    page: int
    bbox: List[float]
    dpi: int = 320


def _path(job_id: str) -> str:
    safe = "".join(c for c in job_id if c.isalnum())
    return os.path.join(STORE_DIR, safe + ".pdf")


def _open_job(job_id: str) -> fitz.Document:
    p = _path(job_id)
    if not os.path.exists(p):
        raise HTTPException(404, "job not found or expired")
    return fitz.open(p)


def _png(page: "fitz.Page", dpi: int, clip: Optional["fitz.Rect"] = None) -> str:
    m = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=m, clip=clip)
    return base64.b64encode(pix.tobytes("png")).decode()


def _cleanup():
    now = time.time()
    try:
        for f in os.listdir(STORE_DIR):
            fp = os.path.join(STORE_DIR, f)
            if os.path.isfile(fp) and now - os.path.getmtime(fp) > JOB_TTL:
                os.remove(fp)
    except Exception:
        pass


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/job/{job_id}")
def job_info(job_id: str):
    p = _path(job_id)
    if not os.path.exists(p):
        return {"exists": False}
    doc = fitz.open(p)
    n = len(doc)
    doc.close()
    return {"exists": True, "page_count": n}


@app.post("/upload")
async def upload(file: UploadFile = File(...), thumb_dpi: int = 90, max_pages: int = 60):
    _cleanup()
    job_id = uuid.uuid4().hex
    p = _path(job_id)
    with open(p, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    doc = fitz.open(p)
    n = min(len(doc), max_pages)
    thumbs = [{"index": i + 1, "thumb_png_b64": _png(doc[i], thumb_dpi)} for i in range(n)]
    doc.close()
    return {"job_id": job_id, "page_count": n, "thumbs": thumbs}


@app.post("/pages")
def pages(inp: PagesIn):
    doc = _open_job(inp.job_id)
    want = [i for i in inp.indices if 1 <= i <= len(doc)]
    if not want:
        want = list(range(1, len(doc) + 1))
    out = [{"index": idx, "full_png_b64": _png(doc[idx - 1], inp.dpi)} for idx in want]
    doc.close()
    return {"pages": out}


@app.post("/text")
def text(inp: TextIn):
    doc = _open_job(inp.job_id)
    want = [i for i in inp.indices if 1 <= i <= len(doc)]
    if not want:
        want = list(range(1, len(doc) + 1))
    out = [{"index": idx, "text": doc[idx - 1].get_text("text") or ""} for idx in want]
    doc.close()
    return {"pages": out}


@app.post("/crop")
def crop(inp: CropIn):
    doc = _open_job(inp.job_id)
    if not (1 <= inp.page <= len(doc)):
        doc.close()
        raise HTTPException(400, "page out of range")
    page = doc[inp.page - 1]
    r = page.rect
    x0, y0, x1, y1 = inp.bbox
    clip = fitz.Rect(r.width * x0, r.height * y0, r.width * x1, r.height * y1)
    png = _png(page, inp.dpi, clip=clip)
    doc.close()
    return {"page": inp.page, "crop_png_b64": png}
