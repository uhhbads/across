from fastapi import APIRouter, Request, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import uuid
import shutil
import mimetypes
import os
from app.config import DATA_DIR

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

images_dir = Path(DATA_DIR) / "images"
images_dir.mkdir(parents=True, exist_ok=True)


@router.get("/gallery", response_class=HTMLResponse)
async def gallery(request: Request):
    files = []
    for p in images_dir.iterdir():
        if p.is_file():
            mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if mime.startswith("image/"):
                files.append({"name": p.name, "url": f"/images/{p.name}"})
    files.sort(key=lambda x: x["name"], reverse=True)
    return templates.TemplateResponse("index.html", {"request": request, "images": files})


@router.get("/upload", response_class=HTMLResponse)
async def upload_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@router.post("/upload")
async def upload_image(file: UploadFile = File(...), title: str = Form(None)):
    ext = Path(file.filename).suffix or ""
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = images_dir / fname
    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return RedirectResponse(url="/gallery", status_code=303)
