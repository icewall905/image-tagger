import os
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import uvicorn

from .api import folders, images, tags, settings as api_settings, thumbnails
from . import models as db_models
from . import globals
from .config import Config, get_config
from .utils import setup_application_logging, log_error_with_context
from .tasks import start_folder_watchers, stop_folder_watchers
from .globals import AppState
from .security import get_security_middleware

# Initialize enhanced logging early
try:
    log_level = Config.get('general', 'log_level', fallback="INFO")
    log_file = Config.get('general', 'log_file', fallback="data/image-tagger.log")
    enable_structured = Config.getboolean('general', 'enable_structured_logging', fallback=False)
    
    setup_application_logging(
        config_log_level=log_level,
        config_log_file=log_file,
        enable_structured=enable_structured
    )
except Exception as e:
    # Fallback to basic logging if enhanced setup fails
    logging.basicConfig(level=logging.INFO)
    logging.error(f"Failed to setup enhanced logging: {e}")

logger = logging.getLogger("image-webui")

# Import and load configuration
config_available = True
try:
    config_obj = get_config()
    logger.info("Configuration loaded successfully")
except Exception as e:
    logger.error(f"Failed to load configuration: {e}")
    config_available = False
    config_obj = None

# Create the FastAPI application
app = FastAPI(
    title="Image Tagger WebUI",
    description="A web interface for tagging and searching images with AI-generated descriptions",
    version="1.0.0"
)

# Add security middleware if enabled
try:
    if config_available and Config.getboolean('security', 'enable_security_headers', fallback=True):
        rate_limit = Config.getint('security', 'rate_limit_per_minute', fallback=60)
        security_middleware = get_security_middleware(rate_limit)
        app.middleware("http")(security_middleware)
        logger.info(f"Security middleware enabled with rate limit: {rate_limit}/minute")
    else:
        logger.info("Security middleware disabled")
except Exception as e:
    logger.warning(f"Failed to setup security middleware: {e}")

# CORS Middleware
try:
    if config_available and Config.getboolean('security', 'enable_cors', fallback=True):
        cors_origins = Config.get('security', 'cors_origins', fallback="*")
        origins_list = cors_origins.split(',') if cors_origins else ["*"]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        logger.info(f"CORS enabled with origins: {origins_list}")
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        logger.info("CORS enabled with default settings")
except Exception as e:
    logger.warning(f"Failed to setup CORS middleware: {e}")

# Setup database
try:
    db_path_str = "sqlite:///data/image_tagger.db"
    if config_available:
        db_path_from_config = Config.get('database', 'path')
        if db_path_from_config:
            db_path_str = db_path_from_config
    
    # Environment variable takes precedence
    if 'DB_PATH' in os.environ:
        db_path_str = os.environ["DB_PATH"]
    
    engine = db_models.get_db_engine(db_path_str)
    db_models.init_db(engine)
    logger.info(f"Database initialized: {db_path_str}")
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    raise

# Mount static files
try:
    static_dir = Path(__file__).parent.parent / "frontend" / "static"
    if not static_dir.exists():
        static_dir.mkdir(parents=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"Static files mounted: {static_dir}")
except Exception as e:
    logger.error(f"Failed to mount static files: {e}")

# Create and mount thumbnails directory
try:
    thumbnail_dir_path_str = "data/thumbnails"
    if config_available:
        thumbnail_path_from_config = Config.get('storage', 'thumbnail_dir')
        if thumbnail_path_from_config:
            thumbnail_dir_path_str = thumbnail_path_from_config
    
    thumbnail_dir = Path(thumbnail_dir_path_str)
    if not thumbnail_dir.exists():
        thumbnail_dir.mkdir(parents=True)
    
    app.mount("/thumbnails", StaticFiles(directory=str(thumbnail_dir)), name="thumbnails")
    logger.info(f"Thumbnails directory mounted: {thumbnail_dir}")
except Exception as e:
    logger.error(f"Failed to setup thumbnails directory: {e}")

# Setup templates
try:
    templates_dir = Path(__file__).parent.parent / "frontend" / "templates"
    if not templates_dir.exists():
        templates_dir.mkdir(parents=True)
    templates = Jinja2Templates(directory=str(templates_dir))
    logger.info(f"Templates directory: {templates_dir}")
except Exception as e:
    logger.error(f"Failed to setup templates: {e}")

# Include API routers
try:
    app.include_router(folders.router, prefix="/api", tags=["folders"])
    app.include_router(images.router, prefix="/api", tags=["images"])
    app.include_router(tags.router, prefix="/api", tags=["tags"])
    app.include_router(api_settings.router, prefix="/api", tags=["settings"])
    app.include_router(thumbnails.router, prefix="/api", tags=["thumbnails"])
    logger.info("API routers included successfully")
except Exception as e:
    logger.error(f"Failed to include API routers: {e}")

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

# Initialize global app state
globals.app_state = AppState()

@app.on_event("startup")
def startup_event():
    """Application startup event"""
    try:
        logger.info("Starting Image Tagger WebUI...")
        
        # Get Ollama settings from config or environment
        ollama_server_val = "http://127.0.0.1:11434"
        ollama_model_val = "qwen2.5vl:latest"

        if config_available:
            server_from_config = Config.get('ollama', 'server', fallback=ollama_server_val)
            model_from_config = Config.get('ollama', 'model', fallback=ollama_model_val)
            
            if server_from_config:
                ollama_server_val = str(server_from_config)
            if model_from_config:
                ollama_model_val = str(model_from_config)
            
            logger.info(f"Using Ollama server: {ollama_server_val}")
            logger.info(f"Using Ollama model: {ollama_model_val}")
        else:
            ollama_server_val = os.environ.get("OLLAMA_SERVER", ollama_server_val)
            ollama_model_val = os.environ.get("OLLAMA_MODEL", ollama_model_val)
            logger.info(f"Using Ollama server from environment: {ollama_server_val}")
        
        # Start folder watchers
        try:
            globals.observer = start_folder_watchers(
                None,  # No session needed - watchers create their own
                ollama_server_val,
                ollama_model_val
            )
            if globals.observer:
                logger.info("Folder watchers started successfully")
            else:
                logger.info("Folder watchers disabled")
        except Exception as e:
            logger.error(f"Failed to start folder watchers: {e}")
            if os.environ.get('DISABLE_FOLDER_WATCHERS') != '1':
                raise
        
        logger.info("Image Tagger WebUI started successfully")
        
    except Exception as e:
        log_error_with_context(e, {"event": "startup"})
        logger.error(f"Failed to start application: {e}")
        raise

@app.on_event("shutdown")
def shutdown_event():
    """Application shutdown event"""
    try:
        logger.info("Shutting down Image Tagger WebUI...")
        
        # Stop folder watchers
        if hasattr(globals, 'observer') and globals.observer:
            try:
                stop_folder_watchers(globals.observer)
                logger.info("Folder watchers stopped")
            except Exception as e:
                logger.error(f"Error stopping folder watchers: {e}")
        
        logger.info("Image Tagger WebUI shutdown complete")
        
    except Exception as e:
        log_error_with_context(e, {"event": "shutdown"})
        logger.error(f"Error during shutdown: {e}")

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    logger.warning(f"HTTP {exc.status_code}: {exc.detail} for {request.url.path}")
    return {"error": exc.detail, "status_code": exc.status_code}

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    log_error_with_context(exc, {"request_path": request.url.path})
    return {"error": "Internal server error", "status_code": 500}

# Run the app if executed directly
if __name__ == "__main__":
    # Get host and port from config or environment
    host_val = "127.0.0.1"
    port_val = 8491

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
