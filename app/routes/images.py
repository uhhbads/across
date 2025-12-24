from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, HTTPException, Body
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import uuid
import shutil
import mimetypes
import os
import json
import datetime
from app.config import DATA_DIR

# optional Pillow import for EXIF
try:
    from PIL import Image
    from PIL.ExifTags import TAGS
except Exception:
    Image = None
    TAGS = {}

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
            # build a small preview list of up to 4 images inside the folder
            previews = []
            try:
                for q in sorted(p.iterdir()):
                    if q.is_file():
                        mime = mimetypes.guess_type(q.name)[0] or "application/octet-stream"
                        if mime.startswith("image/"):
                            previews.append({"name": q.name, "url": f"/images/{p.name}/{q.name}"})
                            if len(previews) >= 4:
                                break
            except Exception:
                previews = []
            folders.append({"name": p.name, "previews": previews})
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
    # (No thumbnail generation) -- previews use full images scaled in the client
    # Record upload time and initialize tags metadata
    try:
        tags_file = images_dir / 'tags.json'
        data = {}
        if tags_file.exists():
            try:
                data = json.loads(tags_file.read_text())
            except Exception:
                data = {}
        rel = f"{folder}/{fname}" if folder else fname
        entry = data.get(rel)
        if not isinstance(entry, dict):
            # migrate previous simple list entry to object
            tags = entry if isinstance(entry, list) else []
            data[rel] = {"tags": tags, "uploaded_at": datetime.datetime.utcnow().isoformat() + 'Z'}
        else:
            entry.setdefault('uploaded_at', datetime.datetime.utcnow().isoformat() + 'Z')
            data[rel] = entry
        tags_file.write_text(json.dumps(data, indent=2))
    except Exception:
        pass
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


def _read_exif(path: Path):
    if Image is None:
        return {}
    try:
        with Image.open(path) as img:
            info = img._getexif() or {}
            out = {}
            for tag, val in info.items():
                name = TAGS.get(tag, tag)
                out[name] = str(val)
            return out
    except Exception:
        return {}


@router.get('/api/image_exif')
async def api_image_exif(folder: str = None, filename: str = None):
    if not filename:
        return {"exif": {}}
    path = images_dir / filename if not folder else images_dir / folder / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return {"exif": _read_exif(path)}


@router.post('/api/create_folder')
async def api_create_folder(request: Request, name: str = Form(None)):
    # Robustly accept JSON body or form data
    folder_name = None
    try:
        body = await request.json()
        if isinstance(body, dict):
            folder_name = body.get('name')
    except Exception:
        folder_name = None
    if not folder_name:
        folder_name = name
    if not folder_name:
        return {"ok": False, "error": "missing name"}
    path = images_dir / folder_name.strip()
    path.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "folder": folder_name}


@router.post('/api/delete_folder')
async def api_delete_folder(request: Request, folder: str = Form(None)):
    folder_name = None
    try:
        body = await request.json()
        if isinstance(body, dict):
            folder_name = body.get('folder')
    except Exception:
        folder_name = None
    if not folder_name:
        folder_name = folder
    if not folder_name:
        return {"ok": False, "error": "missing folder"}
    path = images_dir / folder_name
    if not path.exists() or not path.is_dir():
        return {"ok": False, "error": "not found"}
    for p in path.iterdir():
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
    path.rmdir()
    return {"ok": True}


@router.post('/api/delete_image')
async def api_delete_image(request: Request, folder: str = Form(None), filename: str = Form(None)):
    folder_name = None
    file_name = None
    try:
        body = await request.json()
        if isinstance(body, dict):
            folder_name = body.get('folder')
            file_name = body.get('filename')
    except Exception:
        folder_name = None
        file_name = None
    folder_name = folder_name or folder
    file_name = file_name or filename
    if not file_name:
        return {"ok": False, "error": "missing filename"}
    path = images_dir / file_name if not folder_name else images_dir / folder_name / file_name
    if not path.exists() or not path.is_file():
        return {"ok": False, "error": "not found"}
    path.unlink()
    return {"ok": True}


@router.post('/api/rename_image')
async def api_rename_image(request: Request, folder: str = Form(None), old_name: str = Form(None), new_name: str = Form(None)):
    # accept JSON or form
    body = None
    try:
        body = await request.json()
    except Exception:
        body = None
    if body and isinstance(body, dict):
        old = body.get('old_name') or body.get('old') or old_name
        new = body.get('new_name') or body.get('new') or new_name
        folder_name = body.get('folder') or folder
    else:
        old = old_name
        new = new_name
        folder_name = folder

    if not old or not new:
        return {"ok": False, "error": "missing old or new name"}

    src = images_dir / old if not folder_name else images_dir / folder_name / old
    if not src.exists() or not src.is_file():
        return {"ok": False, "error": "source not found"}

    # Preserve extension if new name has none
    new_path = Path(new)
    if not new_path.suffix:
        new = new + src.suffix

    dst = images_dir / new if not folder_name else images_dir / folder_name / new
    if dst.exists():
        return {"ok": False, "error": "destination exists"}

    try:
        src.rename(dst)
        # rename thumbnail if exists
        # (no thumbnails present) nothing else to rename
        return {"ok": True, "new_name": dst.name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post('/debug/echo')
async def debug_echo(request: Request):
    # Return raw body, parsed JSON (if any), form data and headers to help debugging clients
    body_bytes = await request.body()
    content_type = request.headers.get('content-type')
    try:
        json_body = await request.json()
    except Exception:
        json_body = None
    try:
        form = await request.form()
        form_dict = dict(form)
    except Exception:
        form_dict = None
    return {
        'content_type': content_type,
        'raw': body_bytes.decode('utf-8', errors='replace'),
        'json': json_body,
        'form': form_dict,
        'headers': dict(request.headers)
    }
