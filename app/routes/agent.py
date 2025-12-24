from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
from app.config import OPENAI_API_KEY
import os

# Try to import the OpenAI client; if unavailable we'll fallback to a placeholder reply
try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except Exception:
    OpenAI = None
    _OPENAI_AVAILABLE = False

router = APIRouter()
BASE_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class ChatRequest(BaseModel):
    message: str


@router.get("/chat", response_class=HTMLResponse)
async def chat_ui(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


@router.post("/agent/chat")
async def chat_endpoint(req: ChatRequest):
    user_msg = req.message
    # Only attempt real OpenAI call when client is available and key provided
    if OPENAI_API_KEY and _OPENAI_AVAILABLE:
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful AI assistant."},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=300,
            )

            # Normalize different response shapes
            try:
                content = resp.choices[0].message.content
            except Exception:
                # some versions return a different structure
                content = getattr(resp.choices[0].message, 'content', None) or str(resp)

            return JSONResponse({"reply": content})

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Fallback placeholder reply when OpenAI isn't configured
    return JSONResponse({
        "reply": f"Agent placeholder: I heard '{user_msg}'. (Set OPENAI_API_KEY and install 'openai' to enable real AI.)"
    })

