from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, Any
import os
import re
import json
import shutil
from pathlib import Path
from app.config import OPENAI_API_KEY, BASE_DIR as PROJECT_ROOT
import uuid
import datetime

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
LOG_FILE = IMAGES_ROOT / '.ai_action_log.jsonl'
TRASH_DIR = IMAGES_ROOT / '.trash'
TRASH_DIR.mkdir(parents=True, exist_ok=True)


class ChatRequest(BaseModel):
    message: Optional[str] = ""
    confirm: Optional[bool] = False
    action: Optional[Any] = None


def summarize_action(action: dict):
    # Non-destructive preview of what the action would do
    intent = action.get('intent')
    # folder move preview
    src_folder = action.get('source_folder') or action.get('source')
    target = action.get('target_folder') or action.get('target')
    if src_folder and target:
        sf = _sanitize_folder_name(src_folder)
        if not sf:
            return {"ok": False, "message": "invalid source folder"}
        src_dir = IMAGES_ROOT / sf
        if not src_dir.exists() or not src_dir.is_dir():
            return {"ok": False, "message": f"source folder not found: {sf}"}
        count = sum(1 for _ in src_dir.iterdir() if _.is_file())
        return {"ok": True, "preview": {"move_count": count, "source": f"/{sf}", "target": f"/{_sanitize_folder_name(target)}"}}

    if intent == 'move_image' or intent == 'move':
        query = action.get('query', '')
        matches = find_images_by_query(query)
        return {"ok": True, "preview": {"move_count": len(matches), "sample": matches[:10]}}

    if intent in ('delete_folder', 'remove_folder', 'rmdir'):
        folder = action.get('folder') or action.get('source_folder')
        sf = _sanitize_folder_name(folder)
        if not sf:
            return {"ok": False, "message": "invalid folder"}
        target_dir = IMAGES_ROOT / sf
        if not target_dir.exists():
            return {"ok": False, "message": "folder not found"}
        count = sum(1 for _ in target_dir.rglob('*') if _.is_file())
        return {"ok": True, "preview": {"deleted_files": count, "folder": f"/{sf}"}}

    # default: for rename/delete by query, show matches
    if intent in ('delete_image', 'delete', 'rename_image', 'rename'):
        query = action.get('query', '')
        if query:
            matches = find_images_by_query(query)
            return {"ok": True, "preview": {"matched": len(matches), "sample": matches[:10]}}
    return {"ok": True, "preview": {}}


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
    # helper to append action log
    def _log(entry: dict):
        entry.setdefault('ts', datetime.datetime.utcnow().isoformat() + 'Z')
        try:
            with LOG_FILE.open('a', encoding='utf8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception:
            pass
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
        moved_items = []
        for p in src_dir.iterdir():
            if p.is_file():
                try:
                    dstp = dst_dir / p.name
                    shutil.move(str(p), str(dstp))
                    moved += 1
                    moved_items.append({"src": str(p.relative_to(IMAGES_ROOT)), "dst": str(dstp.relative_to(IMAGES_ROOT))})
                except Exception:
                    pass
        res = {"ok": True, "moved": moved, "target": f"/{tf}", "source": f"/{sf}", "items": moved_items}
        _log({"id": str(uuid.uuid4()), "action": action, "result": res, "inverse": {"type": "move", "items": [{"src": i["dst"], "dst": i["src"]} for i in moved_items]}})
        return res

    if intent == 'move_image' or intent == 'move':
        query = action.get('query', '')
        target = action.get('target_folder')
        if not target:
            return {"ok": False, "message": "missing target_folder"}
        matches = find_images_by_query(query)
        moved = 0
        moved_items = []
        for rel in matches:
            src = IMAGES_ROOT / rel
            dst_dir = IMAGES_ROOT / target.strip('/').lstrip('/')
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / src.name
            try:
                shutil.move(str(src), str(dst))
                moved += 1
                moved_items.append({"src": str(src.relative_to(IMAGES_ROOT)), "dst": str(dst.relative_to(IMAGES_ROOT))})
            except Exception:
                pass
        res = {"ok": True, "moved": moved, "target": target, "items": moved_items}
        _log({"id": str(uuid.uuid4()), "action": action, "result": res, "inverse": {"type": "move", "items": [{"src": i["dst"], "dst": i["src"]} for i in moved_items]}})
        return res

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
            res = {"ok": True, "new_name": str(dst.relative_to(IMAGES_ROOT))}
            _log({"id": str(uuid.uuid4()), "action": action, "result": res, "inverse": {"type": "rename", "old": str(dst.relative_to(IMAGES_ROOT)), "new": str(src.relative_to(IMAGES_ROOT))}})
            return res
        except Exception as e:
            return {"ok": False, "message": str(e)}

    if intent == 'delete_image' or intent == 'delete':
        query = action.get('query', '')
        matches = find_images_by_query(query)
        deleted = 0
        moved_to_trash = []
        trash_bucket = TRASH_DIR / (datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S') + '_' + str(uuid.uuid4()))
        trash_bucket.mkdir(parents=True, exist_ok=True)
        for rel in matches:
            p = IMAGES_ROOT / rel
            try:
                dst = trash_bucket / p.name
                shutil.move(str(p), str(dst))
                deleted += 1
                moved_to_trash.append({"src": str(rel), "trash": str(dst.relative_to(IMAGES_ROOT))})
            except Exception:
                pass
        res = {"ok": True, "deleted": deleted, "trash_bucket": str(trash_bucket.relative_to(IMAGES_ROOT)), "items": moved_to_trash}
        _log({"id": str(uuid.uuid4()), "action": action, "result": res, "inverse": {"type": "restore_trash", "bucket": str(trash_bucket.relative_to(IMAGES_ROOT)), "items": moved_to_trash}})
        return res

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
        res = {"ok": True, "tagged": len(matches), "tags": tags}
        _log({"id": str(uuid.uuid4()), "action": action, "result": res, "inverse": {"type": "tags", "previous": {}}})
        return res

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
            # move folder into trash for possible restore
            trash_bucket = TRASH_DIR / (datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S') + '_' + str(uuid.uuid4()))
            try:
                shutil.move(str(target_dir), str(trash_bucket))
                count = sum(1 for _ in trash_bucket.rglob('*') if _.is_file())
                res = {"ok": True, "deleted_files": count, "folder": f"/{sf}", "trash_bucket": str(trash_bucket.relative_to(IMAGES_ROOT))}
                _log({"id": str(uuid.uuid4()), "action": action, "result": res, "inverse": {"type": "restore_trash_folder", "bucket": str(trash_bucket.relative_to(IMAGES_ROOT))}})
                return res
            except Exception as e:
                return {"ok": False, "message": str(e)}
        else:
            try:
                target_dir.rmdir()
                res = {"ok": True, "deleted_files": 0, "folder": f"/{sf}"}
                _log({"id": str(uuid.uuid4()), "action": action, "result": res, "inverse": {"type": "remove_folder_empty", "folder": f"/{sf}"}})
                return res
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
                return JSONResponse({"reply": content, "action_result": {"ok": False, "message": "No JSON action found"}})

            # If client asked to confirm/execute (sent confirm + action), perform that
            if req.confirm and req.action:
                # execute provided action
                executed = perform_action(req.action)
                # build human message
                if executed.get('ok'):
                    human = None
                    if executed.get('source') and executed.get('target'):
                        human = f"✅ Moved {executed.get('moved',0)} images from {executed.get('source')} to {executed.get('target')}"
                    elif executed.get('folder') and 'deleted_files' in executed:
                        df = executed.get('deleted_files', 0)
                        human = f"✅ Removed folder {executed.get('folder')} (deleted {df} files)" if df else f"✅ Removed empty folder {executed.get('folder')}"
                    else:
                        human = f"✅ Action executed"
                else:
                    human = f"❌ Action failed: {executed.get('message') or executed}"
                return JSONResponse({"reply": human, "action_result": executed, "raw_action": req.action})

            # Otherwise, return a preview (do NOT execute)
            preview = summarize_action(action_json)
            return JSONResponse({"reply": "Preview generated. Confirm to execute.", "raw_action": action_json, "preview": preview, "requires_confirmation": True})

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Fallback placeholder reply when OpenAI isn't configured
    return JSONResponse({
        "reply": f"Agent placeholder: I heard '{user_msg}'. (Set OPENAI_API_KEY and install 'openai' to enable real AI.)"
    })


@router.post('/agent/undo')
async def agent_undo():
    # read log lines
    if not LOG_FILE.exists():
        return JSONResponse({"ok": False, "message": "no action log found"})
    try:
        with LOG_FILE.open('r', encoding='utf8') as f:
            lines = [json.loads(l) for l in f.read().splitlines() if l.strip()]
    except Exception as e:
        return JSONResponse({"ok": False, "message": f"failed to read log: {e}"})

    # find last actionable entry with inverse and not yet undone
    candidate = None
    for entry in reversed(lines):
        if 'inverse' in entry:
            # check if undone
            orig_id = entry.get('id')
            already = any((l.get('type') == 'undo' and l.get('undo_of') == orig_id) or (l.get('undo_of') == orig_id) for l in lines)
            if not already:
                candidate = entry
                break
    if not candidate:
        return JSONResponse({"ok": False, "message": "no undoable actions found"})

    inv = candidate.get('inverse')
    undo_result = {"ok": False, "message": "unknown inverse"}
    try:
        itype = inv.get('type')
        if itype == 'move':
            restored = 0
            for it in inv.get('items', []):
                src = IMAGES_ROOT / it['src']
                dst = IMAGES_ROOT / it['dst']
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.exists():
                    shutil.move(str(src), str(dst))
                    restored += 1
            undo_result = {"ok": True, "restored": restored}

        elif itype == 'rename':
            old = Path(inv.get('old'))
            new = Path(inv.get('new'))
            src = IMAGES_ROOT / old
            dst = IMAGES_ROOT / new
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                shutil.move(str(src), str(dst))
                undo_result = {"ok": True, "restored": str(dst.relative_to(IMAGES_ROOT))}
            else:
                undo_result = {"ok": False, "message": "file not found"}

        elif itype in ('restore_trash', 'restore_trash_folder'):
            bucket = inv.get('bucket')
            bucket_path = IMAGES_ROOT / bucket
            restored = 0
            if bucket_path.exists():
                # if items provided, restore individually
                for it in inv.get('items', []):
                    trashp = IMAGES_ROOT / it.get('trash')
                    orig = IMAGES_ROOT / it.get('src')
                    orig.parent.mkdir(parents=True, exist_ok=True)
                    if trashp.exists():
                        shutil.move(str(trashp), str(orig))
                        restored += 1
                # if folder restore, move bucket to original location if possible
                if itype == 'restore_trash_folder':
                    # attempt move bucket back to original folder name from candidate.action.folder
                    orig_folder = candidate.get('action', {}).get('folder')
                    if orig_folder:
                        sf = _sanitize_folder_name(orig_folder)
                        if sf:
                            dest = IMAGES_ROOT / sf
                            if not dest.exists():
                                shutil.move(str(bucket_path), str(dest))
                                undo_result = {"ok": True, "restored_folder": f"/{sf}"}
                            else:
                                undo_result = {"ok": False, "message": "destination exists"}
                        else:
                            undo_result = {"ok": False, "message": "invalid original folder"}
                    else:
                        undo_result = {"ok": False, "message": "no original folder info"}
                else:
                    # cleanup empty bucket
                    try:
                        if bucket_path.exists() and not any(bucket_path.iterdir()):
                            bucket_path.rmdir()
                    except Exception:
                        pass
                    undo_result = {"ok": True, "restored": restored}
            else:
                undo_result = {"ok": False, "message": "trash bucket not found"}

        else:
            undo_result = {"ok": False, "message": f"unsupported inverse type {itype}"}

    except Exception as e:
        undo_result = {"ok": False, "message": str(e)}

    # append undo log
    try:
        with LOG_FILE.open('a', encoding='utf8') as f:
            f.write(json.dumps({"id": str(uuid.uuid4()), "type": "undo", "undo_of": candidate.get('id'), "result": undo_result, "ts": datetime.datetime.utcnow().isoformat() + 'Z'}, ensure_ascii=False) + '\n')
    except Exception:
        pass

    return JSONResponse(undo_result)

