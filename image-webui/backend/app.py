import os
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import logging # Keep this for direct logging calls if needed
from pathlib import Path
import uvicorn

from .api import folders, images, tags, settings as api_settings
from . import models as db_models
from . import globals
from .config import Config, get_config
from .utils import setup_logging # This import should now work
from .tasks import start_folder_watchers, stop_folder_watchers
from .globals import AppState

# Call setup_logging as early as possible
# Determine log level from config or default
config_for_log = get_config() if Config else None
log_level_from_config = "INFO"
if config_for_log:
    # Get log_level from config using the Config class methods
    log_level_from_config = Config.get('general', 'log_level', fallback="INFO") or "INFO"
setup_logging(log_level_from_config)


logger = logging.getLogger("image-webui") # Get logger after setup

# Import and load configuration
config_available = True
try:
    # config_obj is the instance from the backward-compatible get_config()
    # We should primarily use the Config class for new accesses.
    config_obj = get_config() 
except Exception as e:
    logger.error(f"Failed to load configuration via get_config(): {e}")
    config_available = False
    config_obj = None # Ensure it's defined

if config_obj: # Check if config_obj is not None
    # Use the Config class directly instead of trying to access potentially missing attributes
    log_level_str = Config.get('general', 'log_level', fallback="INFO")
    
    # Make sure log_level_str is not None before calling upper()
    if log_level_str:
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)
        logging.getLogger().setLevel(log_level)
    else:
        logging.getLogger().setLevel(logging.INFO)
    
    config_path = str(Path(__file__).parent.parent / "config.ini")
    logger.info(f"Configuration loaded from {config_path}")
else:
    logger.warning("config_obj is None, using default INFO log level.")
    logging.getLogger().setLevel(logging.INFO)

# Create the FastAPI application
app = FastAPI(
    title="Image Tagger WebUI",
    description="A web interface for tagging and searching images with AI-generated descriptions",
    version="1.0.0"
)

# CORS Middleware
# Use Config class methods for accessing configuration values
if config_available and Config.getboolean('security', 'enable_cors'):
    cors_origins = Config.get('security', 'cors_origins', fallback="*")
    origins_list = cors_origins.split(',') if cors_origins else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Setup database
db_path_str = "sqlite:///data/image_tagger.db" # Default value
if config_available:
    # Try to get from Config class first (recommended approach)
    db_path_from_config = Config.get('database', 'path')
    if db_path_from_config:
        db_path_str = db_path_from_config
    # Fallback to config_obj for backward compatibility
    elif config_obj:
        if hasattr(config_obj, 'database') and isinstance(config_obj.database, dict) and 'path' in config_obj.database:
            db_path_str = config_obj.database['path']
        elif hasattr(config_obj, 'db_path') and config_obj.db_path:
            db_path_str = config_obj.db_path
        
# Environment variable takes precedence
if 'DB_PATH' in os.environ:
    db_path_str = os.environ["DB_PATH"]

engine = db_models.get_db_engine(db_path_str)
db_models.init_db(engine)

# Mount static files
static_dir = Path(__file__).parent.parent / "frontend" / "static"
if not static_dir.exists():
    static_dir.mkdir(parents=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Create a thumbnails directory
thumbnail_dir_path_str = "data/thumbnails" # Default value
if config_available:
    # Use Config class directly
    thumbnail_path_from_config = Config.get('storage', 'thumbnail_dir')
    if thumbnail_path_from_config:
        thumbnail_dir_path_str = thumbnail_path_from_config
    # Fallback to config_obj if needed
    elif config_obj and hasattr(config_obj, 'get'):
        try:
            # Use lambda to accommodate different method signatures
            if callable(config_obj.get) and hasattr(config_obj.get, '__code__') and config_obj.get.__code__.co_argcount >= 3:
                thumbnail_dir_path_str = config_obj.get('storage', 'thumbnail_dir', "data/thumbnails")
            else:
                # Fallback if get method has different signature
                thumbnail_dir_path_str = "data/thumbnails"
        except Exception as e: 
            logger.warning(f"Could not get 'thumbnail_dir' from config: {e}, using default.")
        
thumbnail_dir = Path(thumbnail_dir_path_str)

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
app.include_router(tags.router, prefix="/api", tags=["tags"])
app.include_router(api_settings.router, prefix="/api", tags=["settings"])

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

@app.get("/settings")
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

# Start folder watchers
observer = None

@app.on_event("startup")
def startup_event():
    logger.info("Starting folder watchers...")
    
    # Get Ollama settings from config or environment
    ollama_server_val = "http://127.0.0.1:11434"
    ollama_model_val = "qwen2.5vl:latest"

    if config_available and config_obj:
        ollama_server_val = getattr(config_obj, 'ollama_server', ollama_server_val)
        ollama_model_val = getattr(config_obj, 'ollama_model', ollama_model_val)
    else:
        ollama_server_val = os.environ.get("OLLAMA_SERVER", ollama_server_val)
        ollama_model_val = os.environ.get("OLLAMA_MODEL", ollama_model_val)
    
    db_session_startup = None
    try:
        db_session_startup = db_models.SessionLocal()
        globals.observer = start_folder_watchers(
            db_session_startup,
            ollama_server_val,
            ollama_model_val
        )
        if globals.observer:
            logger.info("Folder watchers started")
        else:
            logger.info("Folder watchers disabled")
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        if db_session_startup:
            db_session_startup.close() # Ensure session is closed on error
        # Don't raise the exception if folder watchers are disabled
        if os.environ.get('DISABLE_FOLDER_WATCHERS') != '1':
            raise # Re-raise exception to halt startup if critical
    # Note: db_session_startup should ideally be closed when the observer stops,
    # or each task spawned by the observer should manage its own session.
    # For simplicity here, it's created and passed. If start_folder_watchers
    # is long-running and uses this session, it's kept open.

@app.on_event("shutdown")
def shutdown_event():
    if globals.observer:
        logger.info("Stopping folder watchers...")
        globals.observer.stop()
        globals.observer.join()
        logger.info("Folder watchers stopped")

# Run the app if executed directly
if __name__ == "__main__":
    # Get host and port from config or environment
    host_val = "127.0.0.1"
    port_val = 8000

    if config_available and config_obj:
        host_val = getattr(config_obj, 'host', host_val)
        port_val = getattr(config_obj, 'port', port_val) # Assuming port is int in config
        if isinstance(port_val, str): port_val = int(port_val)
    else:
        host_val = os.environ.get("HOST", host_val)
        port_val = int(os.environ.get("PORT", str(port_val)))
    
    uvicorn.run(
        "backend.app:app", # Changed to backend.app:app for consistency with CMD in Dockerfile
        host=host_val,
        port=port_val,
        reload=True
    )
