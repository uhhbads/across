from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.routes import images, agent
from fastapi.templating import Jinja2Templates
from pathlib import Path
import os

app = FastAPI(title="Aperture - Image Dump")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Mount saved images as static files
images_dir = DATA_DIR / "images"
images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(images_dir)), name="images")

# Templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Include routers
app.include_router(images.router)
app.include_router(agent.router)


@app.get("/")
async def root():
    return RedirectResponse(url="/gallery")
