from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
from app.config import OPENAI_API_KEY

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
    # Simple placeholder agent — replace with real provider integration
    user_msg = req.message
    if OPENAI_API_KEY:
        try:
            import openai
            openai.api_key = OPENAI_API_KEY
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=300,
            )
            content = resp.choices[0].message.content
            return JSONResponse({"reply": content})
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    # Fallback canned response
    return JSONResponse({"reply": f"Agent placeholder: I heard '{user_msg}'. (Set OPENAI_API_KEY to enable real AI.)"})
