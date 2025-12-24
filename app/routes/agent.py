from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
from app.config import OPENAI_API_KEY
from openai import OpenAI

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

    if OPENAI_API_KEY:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)

            resp = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful AI assistant."},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=300,
            )

            content = resp.choices[0].message.content
            return JSONResponse({"reply": content})

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse({
        "reply": f"Agent placeholder: I heard '{user_msg}'. (Set OPENAI_API_KEY to enable real AI.)"
    })

