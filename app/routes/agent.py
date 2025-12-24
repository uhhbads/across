from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
import re
import json
import shutil
from pathlib import Path
from app.config import OPENAI_API_KEY, BASE_DIR as PROJECT_ROOT

# Try to import the OpenAI client; if unavailable we'll fallback to a placeholder reply
try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except Exception:
    OpenAI = None
    _OPENAI_AVAILABLE = False

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# images root
IMAGES_ROOT = Path(os.getenv('DATA_DIR', PROJECT_ROOT / 'data')) / 'images'
IMAGES_ROOT.mkdir(parents=True, exist_ok=True)


class ChatRequest(BaseModel):
    message: str


@router.get("/chat", response_class=HTMLResponse)
async def chat_ui(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


def extract_json(text: str):
    # Try to extract the first JSON object or array from the text
    if not text:
        return None
    # look for first { ... }
    m = re.search(r"(\{.*\})", text, re.S)
    if not m:
        m = re.search(r"(\[.*\])", text, re.S)
    if not m:
        return None
    s = m.group(1)
    try:
        return json.loads(s)
    except Exception:
        # try to fix common issues: single quotes -> double quotes
        try:
            fixed = s.replace("'", '"')
            return json.loads(fixed)
        except Exception:
            return None


def find_images_by_query(query: str):
    # naive search: split query into tokens and match filenames containing all tokens
    tokens = [t.lower() for t in re.findall(r"\w+", query)]
    matches = []
    for p in IMAGES_ROOT.rglob('*'):
        if p.is_file():
            name = p.name.lower()
            if all(tok in name for tok in tokens):
                # return path relative to IMAGES_ROOT
                rel = p.relative_to(IMAGES_ROOT)
                matches.append(str(rel).replace('\\', '/'))
    return matches


def _sanitize_folder_name(name: str):
    if not name:
        return None
    s = str(name).replace('\\', '/').strip()
    # disallow traversal
    parts = [p for p in s.split('/') if p and p != '.']
    if any(p == '..' for p in parts):
        return None
    return '/'.join(parts)


def perform_action(action: dict):
    # action is expected to have keys: intent, query, target_folder, filename, tags, etc.
    intent = action.get('intent')
    result = {"ok": False, "message": "unknown action"}
    # If action defines a source_folder and target_folder, move all files from source -> target
    src_folder = action.get('source_folder') or action.get('source')
    target = action.get('target_folder') or action.get('target')
    if src_folder and target:
        sf = _sanitize_folder_name(src_folder)
        tf = _sanitize_folder_name(target)
        if not sf or not tf:
            return {"ok": False, "message": "invalid folder name"}
        src_dir = IMAGES_ROOT / sf
        if not src_dir.exists() or not src_dir.is_dir():
            return {"ok": False, "message": f"source folder not found: {sf}"}
        dst_dir = IMAGES_ROOT / tf
        dst_dir.mkdir(parents=True, exist_ok=True)
        moved = 0
        for p in src_dir.iterdir():
            if p.is_file():
                try:
                    shutil.move(str(p), str(dst_dir / p.name))
                    moved += 1
                except Exception:
                    pass
        return {"ok": True, "moved": moved, "target": f"/{tf}", "source": f"/{sf}"}

    if intent == 'move_image' or intent == 'move':
        query = action.get('query', '')
        target = action.get('target_folder')
        if not target:
            return {"ok": False, "message": "missing target_folder"}
        matches = find_images_by_query(query)
        moved = 0
        for rel in matches:
            src = IMAGES_ROOT / rel
            dst_dir = IMAGES_ROOT / target.strip('/').lstrip('/')
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / src.name
            try:
                shutil.move(str(src), str(dst))
                moved += 1
            except Exception:
                pass
        return {"ok": True, "moved": moved, "target": target}

    if intent == 'rename_image' or intent == 'rename':
        folder = action.get('folder')
        old = action.get('old_name') or action.get('filename')
        new = action.get('new_name')
        if not old or not new:
            return {"ok": False, "message": "missing names"}
        src = IMAGES_ROOT / old if not folder else IMAGES_ROOT / folder.strip('/') / old
        dst = IMAGES_ROOT / new if not folder else IMAGES_ROOT / folder.strip('/') / new
        try:
            src.rename(dst)
            return {"ok": True, "new_name": str(dst.relative_to(IMAGES_ROOT))}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    if intent == 'delete_image' or intent == 'delete':
        query = action.get('query', '')
        matches = find_images_by_query(query)
        deleted = 0
        for rel in matches:
            p = IMAGES_ROOT / rel
            try:
                p.unlink()
                deleted += 1
            except Exception:
                pass
        return {"ok": True, "deleted": deleted}

    if intent == 'tag' or intent == 'tag_image':
        # store tags in a tags.json in IMAGES_ROOT
        tags_file = IMAGES_ROOT / 'tags.json'
        data = {}
        if tags_file.exists():
            try:
                data = json.loads(tags_file.read_text())
            except Exception:
                data = {}
        query = action.get('query', '')
        tags = action.get('tags') or action.get('labels') or []
        matches = find_images_by_query(query)
        for rel in matches:
            data.setdefault(rel, [])
            for t in tags:
                if t not in data[rel]:
                    data[rel].append(t)
        try:
            tags_file.write_text(json.dumps(data, indent=2))
        except Exception:
            pass
        return {"ok": True, "tagged": len(matches), "tags": tags}

    if intent == 'summarize' or intent == 'summary':
        query = action.get('query', '')
        matches = find_images_by_query(query)
        return {"ok": True, "count": len(matches), "samples": matches[:10]}

    # delete/remove folder
    if intent in ('delete_folder', 'remove_folder', 'rmdir'):
        folder = action.get('folder') or action.get('source_folder') or action.get('target_folder')
        if not folder:
            return {"ok": False, "message": "missing folder"}
        sf = _sanitize_folder_name(folder)
        if not sf:
            return {"ok": False, "message": "invalid folder name"}
        target_dir = IMAGES_ROOT / sf
        if not target_dir.exists() or not target_dir.is_dir():
            return {"ok": False, "message": f"folder not found: {sf}"}
        recursive = bool(action.get('recursive', False))
        if recursive:
            # count files for reporting
            count = sum(1 for _ in target_dir.rglob('*') if _.is_file())
            try:
                shutil.rmtree(target_dir)
                return {"ok": True, "deleted_files": count, "folder": f"/{sf}"}
            except Exception as e:
                return {"ok": False, "message": str(e)}
        else:
            try:
                target_dir.rmdir()
                return {"ok": True, "deleted_files": 0, "folder": f"/{sf}"}
            except Exception as e:
                return {"ok": False, "message": "folder not empty or cannot remove: " + str(e)}

    return result



@router.post("/agent/chat")
async def chat_endpoint(req: ChatRequest):
    user_msg = req.message
    # Only attempt real OpenAI call when client is available and key provided
    if OPENAI_API_KEY and _OPENAI_AVAILABLE:
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            system_prompt = (
                "You are an assistant that ONLY outputs a single JSON object describing an action to take. "
                "Do NOT output any additional explanation.\n"
                "Schema examples:\n"
                "{\"intent\": \"move_image\", \"query\": \"screenshots december\", \"target_folder\": \"/school\"}\n"
                "{\"intent\": \"rename_image\", \"old_name\": \"IMG_0001.png\", \"new_name\": \"receipt_dec1.png\"}\n"
                "{\"source_folder\": \"Japan/Raw\", \"target_folder\": \"Japan/Edited\"}\n"
                "{\"intent\": \"delete_folder\", \"folder\": \"OldTrips/2018\", \"recursive\": true}\n"
                "Allowed intents: move_image/move, rename_image/rename, tag/tag_image, delete_image/delete, summarize/summary. You may also specify \"source_folder\" and \"target_folder\" to move entire folders, or intent \"delete_folder\" to remove a folder."
            )
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=400,
            )

            # Normalize response
            try:
                content = resp.choices[0].message.content
            except Exception:
                content = getattr(resp.choices[0].message, 'content', None) or str(resp)

            # try to extract JSON action from model reply
            action_json = extract_json(content)
            if action_json is None:
                # return model text as fallback
                return JSONResponse({"reply": content, "action_result": {"ok": False, "message": "No JSON action found"}})

            # perform the action
            action_result = perform_action(action_json)

            # human readable message
            human = None
            if action_result.get('ok'):
                # folder-source move readable message
                if action_result.get('source') and action_result.get('target'):
                    human = f"✅ Moved {action_result.get('moved',0)} images from {action_result.get('source')} to {action_result.get('target')}"
                # folder delete readable message
                elif action_result.get('folder') and 'deleted_files' in action_result:
                    df = action_result.get('deleted_files', 0)
                    if df:
                        human = f"✅ Removed folder {action_result.get('folder')} and deleted {df} files"
                    else:
                        human = f"✅ Removed empty folder {action_result.get('folder')}"
                else:
                    # fall through to existing per-intent messages
                    if action_json.get('intent') in ('move_image', 'move'):
                        human = f"✅ Moved {action_result.get('moved',0)} images to {action_result.get('target')}"
                    elif action_json.get('intent') in ('rename_image','rename'):
                        human = f"✅ Renamed image to {action_result.get('new_name')}"
                    elif action_json.get('intent') in ('delete_image','delete'):
                        human = f"✅ Deleted {action_result.get('deleted',0)} images"
                    elif action_json.get('intent') in ('tag','tag_image'):
                        human = f"✅ Tagged {action_result.get('tagged',0)} images with {action_result.get('tags')}"
                    elif action_json.get('intent') in ('summarize','summary'):
                        human = f"📊 Found {action_result.get('count',0)} images"
                    else:
                        human = "✅ Action completed"
            else:
                human = f"❌ Action failed: {action_result.get('message') or action_result}"

            return JSONResponse({"reply": human, "action_result": action_result, "raw_action": action_json})

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Fallback placeholder reply when OpenAI isn't configured
    return JSONResponse({
        "reply": f"Agent placeholder: I heard '{user_msg}'. (Set OPENAI_API_KEY and install 'openai' to enable real AI.)"
    })

