import os
import logging
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import threading
import uvicorn

from .models import get_db_engine, get_db_session, init_db
from .api import folders, images, search
from .api import thumbnails  # Add thumbnail router
from .tasks import start_folder_watchers
from . import globals

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("image-webui")

# Create the FastAPI application
app = FastAPI(
    title="Image Tagger WebUI",
    description="A web interface for tagging and searching images with AI-generated descriptions",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup database
db_path = os.environ.get("DB_PATH", "sqlite:///image_tagger.db")
engine = get_db_engine(db_path)
init_db(engine)
db_session = get_db_session(engine)

# Mount static files
static_dir = Path(__file__).parent.parent / "frontend" / "static"
if not static_dir.exists():
    static_dir.mkdir(parents=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Create a thumbnails directory
thumbnail_dir = Path("data/thumbnails")
if not thumbnail_dir.exists():
    thumbnail_dir.mkdir(parents=True)
app.mount("/thumbnails", StaticFiles(directory=str(thumbnail_dir)), name="thumbnails")

# Setup templates
templates_dir = Path(__file__).parent.parent / "frontend" / "templates"
if not templates_dir.exists():
    templates_dir.mkdir(parents=True)
templates = Jinja2Templates(directory=str(templates_dir))

# Include API routers
app.include_router(folders.router, prefix="/api", tags=["folders"])
app.include_router(images.router, prefix="/api", tags=["images"])
app.include_router(search.router, prefix="/api", tags=["search"])
app.include_router(thumbnails.router, tags=["thumbnails"])

# Add db_session dependency
@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    request.state.db = db_session
    response = await call_next(request)
    return response

# Define dependency to get db from request
def get_db_from_request(request: Request):
    return request.state.db

# Override the get_db function in the routers
folders.get_db = get_db_from_request
images.get_db = get_db_from_request
search.get_db = get_db_from_request
thumbnails.get_db = get_db_from_request

# Define routes
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/folders")
async def folders_page(request: Request):
    return templates.TemplateResponse("folders.html", {"request": request})

@app.get("/gallery")
async def gallery_page(request: Request):
    return templates.TemplateResponse("gallery.html", {"request": request})

@app.get("/search")
async def search_page(request: Request):
    return templates.TemplateResponse("search.html", {"request": request})

# Start folder watchers
observer = None

@app.on_event("startup")
def startup_event():
    logger.info("Starting folder watchers...")
    globals.observer = start_folder_watchers(
        db_session,
        os.environ.get("OLLAMA_SERVER", "http://127.0.0.1:11434"),
        os.environ.get("OLLAMA_MODEL", "llama3.2-vision")
    )
    logger.info("Folder watchers started")

@app.on_event("shutdown")
def shutdown_event():
    if globals.observer:
        logger.info("Stopping folder watchers...")
        globals.observer.stop()
        globals.observer.join()
        logger.info("Folder watchers stopped")

# Run the app if executed directly
if __name__ == "__main__":
    uvicorn.run(
        "app:app", 
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 8000)),
        reload=True
    )
