Aperture — Image-dump + AI-agent boilerplate

Quick start

1. Create and activate a virtualenv (Windows):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and set `OPENAI_API_KEY` if using AI features.

3. Run the app:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

4. Open http://127.0.0.1:8000/

What this scaffold includes

- A minimal FastAPI app with image upload and gallery
- Jinja2 templates and static files
- An `/agent/chat` endpoint that proxies to OpenAI if configured, otherwise returns a placeholder reply
- Simple file-based image storage under `data/images`

Next steps

- Add authentication, database, and thumbnails
- Plug a production AI agent provider and websocket chat UI
