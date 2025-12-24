from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, HTTPException
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
async def gallery(request: Request, folder: str = None):
    # If folder provided, show images in that folder; otherwise show folders and root images
    context = {"request": request}
    if folder:
        folder_path = images_dir / folder
        if not folder_path.exists() or not folder_path.is_dir():
            raise HTTPException(status_code=404, detail="Folder not found")
        files = []
        for p in folder_path.iterdir():
            if p.is_file():
                mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
                if mime.startswith("image/"):
                    files.append({"name": p.name, "url": f"/images/{folder}/{p.name}"})
        files.sort(key=lambda x: x["name"], reverse=True)
        context.update({"images": files, "folder": folder})
        return templates.TemplateResponse("index.html", context)

    # root gallery: list folders and root images
    folders = []
    images = []
    for p in images_dir.iterdir():
        if p.is_dir():
            folders.append({"name": p.name})
        elif p.is_file():
            mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if mime.startswith("image/"):
                images.append({"name": p.name, "url": f"/images/{p.name}"})
    folders.sort(key=lambda x: x["name"])
    images.sort(key=lambda x: x["name"], reverse=True)
    context.update({"folders": folders, "images": images})
    return templates.TemplateResponse("index.html", context)


@router.get("/upload", response_class=HTMLResponse)
async def upload_form(request: Request, folder: str = None):
    # pass folder to template so upload goes to that folder
    return templates.TemplateResponse("upload.html", {"request": request, "folder": folder})


@router.post("/upload")
async def upload_image(file: UploadFile = File(...), title: str = Form(None), folder: str = Form(None)):
    ext = Path(file.filename).suffix or ""
    fname = f"{uuid.uuid4().hex}{ext}"
    dest_dir = images_dir
    if folder:
        dest_dir = images_dir / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / fname
    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    if folder:
        return RedirectResponse(url=f"/gallery?folder={folder}", status_code=303)
    return RedirectResponse(url="/gallery", status_code=303)


@router.post("/gallery/create_folder")
async def create_folder(name: str = Form(...)):
    safe = name.strip()
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid folder name")
    path = images_dir / safe
    path.mkdir(parents=True, exist_ok=True)
    return RedirectResponse(url="/gallery", status_code=303)


@router.post("/gallery/{folder}/delete")
async def delete_folder(folder: str):
    path = images_dir / folder
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    # remove all files and dir
    for p in path.iterdir():
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
    path.rmdir()
    return RedirectResponse(url="/gallery", status_code=303)


@router.post("/gallery/{folder}/rename")
async def rename_folder(folder: str, new_name: str = Form(...)):
    src = images_dir / folder
    dst = images_dir / new_name.strip()
    if not src.exists() or not src.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    if dst.exists():
        raise HTTPException(status_code=400, detail="Destination already exists")
    src.rename(dst)
    return RedirectResponse(url="/gallery", status_code=303)


@router.post("/gallery/{folder}/delete_image")
async def delete_image(folder: str, filename: str = Form(...)):
    path = images_dir / folder / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    path.unlink()
    return RedirectResponse(url=f"/gallery?folder={folder}", status_code=303)
