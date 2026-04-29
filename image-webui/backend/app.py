import os
import threading
from fastapi import FastAPI, HTTPException, Request, Depends, APIRouter
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import uvicorn

from .api import folders, images, search, settings as api_settings, thumbnails
from . import models as db_models
from . import globals
from .config import Config, get_config
from .utils import setup_application_logging, log_error_with_context
from .tasks import start_folder_watchers, stop_folder_watchers, ScheduleChecker, _schedule_stop_event, scan_library_on_startup
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

# Configuration is auto-loaded when config module is imported (Config.initialize())
config_available = True
try:
    # Verify config is accessible
    Config.get('general', 'host', fallback='0.0.0.0')
    logger.info("Configuration loaded successfully")
except Exception as e:
    logger.error(f"Failed to load configuration: {e}")
    config_available = False

# Lifespan manager for startup and shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    try:
        logger.info("Starting Image Tagger WebUI...")

        # --- Startup validation ---
        # Validate database path is writable
        db_path_str = Config.get('database', 'path', fallback='sqlite:///data/image_tagger.db')
        if db_path_str.startswith('sqlite:///'):
            db_file = Path(db_path_str[10:])
            db_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                db_file.touch(exist_ok=True)
                logger.info(f"Database path validated: {db_file}")
            except Exception as e:
                logger.error(f"Database path not writable: {db_file} — {e}")

        # Validate thumbnail directory
        thumb_dir = Config.get('storage', 'thumbnail_dir', fallback='data/thumbnails')
        thumb_path = Path(thumb_dir)
        thumb_path.mkdir(parents=True, exist_ok=True)
        try:
            test_file = thumb_path / '.write_test'
            test_file.touch()
            test_file.unlink()
            logger.info(f"Thumbnail directory validated: {thumb_path}")
        except Exception as e:
            logger.error(f"Thumbnail directory not writable: {thumb_path} — {e}")

        # Check if any folders are configured
        try:
            db_check = db_models.SessionLocal()
            folder_count = db_check.query(db_models.Folder).filter_by(active=True).count()
            db_check.close()
            if folder_count == 0:
                logger.warning("No active folders configured. Add folders via the Folders page or API.")
            else:
                logger.info(f"Found {folder_count} active folder(s) to monitor")
        except Exception:
            logger.warning("Could not check folder count — DB may not be ready yet")

        # Print bound address
        host_val = Config.get('general', 'host', fallback='0.0.0.0')
        port_val = Config.get('general', 'port', fallback='8491')
        logger.info(f"Server will listen on http://{host_val}:{port_val}")
        if host_val in ('127.0.0.1', 'localhost'):
            logger.warning("WARNING: Binding to localhost only — remote machines will NOT be able to connect!")
        # --- End startup validation ---

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
        
        # Start folder watchers (in background thread to avoid blocking startup
        # on large directories — observer.schedule() with recursive=True can
        # take minutes on 400k+ image trees)
        def _start_watchers():
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
                    # Re-raise in the thread so it's visible, but don't kill the app
                    logger.error("Set DISABLE_FOLDER_WATCHERS=1 to suppress this error")

        threading.Thread(target=_start_watchers, name="WatcherInit", daemon=True).start()
        
        # Start processing schedule checker
        schedule_enabled = Config.getboolean('schedule', 'enabled', fallback=False)
        schedule_start = Config.get('schedule', 'start_hour', fallback='1')
        schedule_end = Config.get('schedule', 'end_hour', fallback='5')
        schedule_tz = Config.get('schedule', 'timezone', fallback='system local')
        logger.info(f"Schedule configuration: enabled={schedule_enabled}, "
                    f"window={schedule_start}:00-{schedule_end}:00, timezone={schedule_tz}")
        try:
            _schedule_stop_event.clear()
            globals.schedule_checker = ScheduleChecker(
                server=ollama_server_val,
                model=ollama_model_val,
                stop_event=_schedule_stop_event
            )
            globals.schedule_checker.start()
            if schedule_enabled:
                logger.info("ScheduleChecker started — will auto-trigger batch processing at window open")
            else:
                logger.warning("Schedule is DISABLED — ScheduleChecker running but will NOT auto-trigger. "
                               "Enable it via Settings page or set schedule.enabled=true in config.ini")
        except Exception as e:
            logger.error(f"Failed to start schedule checker: {e}")

        # Startup scan (if enabled)
        scan_on_startup = Config.getboolean('processing', 'scan_on_startup', fallback=False)
        if scan_on_startup:
            try:
                scan_library_on_startup(ollama_server_val, ollama_model_val)
                logger.info("Startup library scan initiated")
            except Exception as e:
                logger.error(f"Failed to initiate startup scan: {e}")

        # Always scan DB for legacy untagged images (regardless of scan_on_startup)
        try:
            from .tasks import scan_db_for_untagged_images
            db_untagged = scan_db_for_untagged_images(ollama_server_val, ollama_model_val)
            if db_untagged > 0:
                logger.info(f"Startup: Found {db_untagged} DB images without tags — added to reprocessing queue")
            else:
                logger.info("Startup: All DB images already have tags")
        except Exception as e:
            logger.error(f"Failed to scan DB for untagged images: {e}")

        logger.info("Image Tagger WebUI started successfully")

        yield  # Run the application
        
        # Shutdown logic
        logger.info("Shutting down Image Tagger WebUI...")
        
        # Stop folder watchers
        if hasattr(globals, 'observer') and globals.observer:
            try:
                stop_folder_watchers(globals.observer)
                logger.info("Folder watchers stopped")
            except Exception as e:
                logger.error(f"Error stopping folder watchers: {e}")

        # Stop schedule checker
        if globals.schedule_checker:
            try:
                globals.schedule_checker.stop()
                logger.info("Schedule checker stopped")
            except Exception as e:
                logger.error(f"Error stopping schedule checker: {e}")

        logger.info("Image Tagger WebUI shutdown complete")
        
    except Exception as e:
        log_error_with_context(e, {"event": "lifespan"})
        logger.error(f"Error during application lifecycle: {e}")
        raise

# Create the FastAPI application
app = FastAPI(
    title="Image Tagger WebUI",
    description="A web interface for tagging and searching images with AI-generated descriptions",
    version="1.0.0",
    lifespan=lifespan
)

# Add security middleware if enabled
try:
    enable_headers = Config.getboolean('security', 'enable_security_headers', fallback=True)
    enable_rate_limiting = Config.getboolean('security', 'enable_rate_limiting', fallback=False)
    
    if config_available and enable_headers:
        rate_limit = Config.getint('security', 'rate_limit_per_minute', fallback=60)
        security_middleware = get_security_middleware(rate_limit, enable_rate_limiting)
        app.middleware("http")(security_middleware)
        logger.info(f"Security middleware enabled (Headers: yes, Rate Limit: {'yes' if enable_rate_limiting else 'no'})")
    else:
        logger.info("Security middleware (headers) disabled")
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

# Image root for serving files — configurable for Docker vs bare-metal
IMAGE_ROOT = os.environ.get("IMAGE_ROOT", "/")

@app.get("/images/{path:path}")
async def serve_image(path: str):
    """
    Serve images from the configured IMAGE_ROOT.
    In Docker this is typically /images (the mounted volume).
    Outside Docker this defaults to / (filesystem root).
    """
    image_path = Path(IMAGE_ROOT) / path
    if not image_path.exists():
        logger.warning(f"Image not found on disk: {image_path}")
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)

@app.get("/api/health")
async def health_check():
    """Simple health check endpoint for monitoring."""
    try:
        db = db_models.SessionLocal()
        db.execute(db_models.text("SELECT 1"))
        db.close()
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "degraded", "db": str(e)}

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
    app.include_router(search.router, prefix="/api", tags=["search"])
    app.include_router(api_settings.router, prefix="/api", tags=["settings"])
    app.include_router(thumbnails.router, prefix="/api", tags=["thumbnails"])
    logger.info("API routers included successfully")
except Exception as e:
    logger.error(f"Failed to include API routers: {e}")

# Define routes
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"request": request})

@app.get("/folders")
async def folders_page(request: Request):
    return templates.TemplateResponse(request=request, name="folders.html", context={"request": request})

@app.get("/gallery")
async def gallery_page(request: Request):
    return templates.TemplateResponse(request=request, name="gallery.html", context={"request": request})

@app.get("/search")
async def search_page(request: Request):
    return templates.TemplateResponse(request=request, name="search.html", context={"request": request})

@app.get("/settings")
async def settings_page(request: Request):
    return templates.TemplateResponse(request=request, name="settings.html", context={"request": request})

# Initialize global app state
globals.app_state = AppState()

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    logger.warning(f"HTTP {exc.status_code}: {exc.detail} for {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status_code": exc.status_code}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    log_error_with_context(exc, {"request_path": request.url.path})
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "status_code": 500}
    )

# Run the app if executed directly
if __name__ == "__main__":
    host_val = Config.get('general', 'host', fallback="0.0.0.0")
    port_val = Config.getint('general', 'port', fallback=8491)

    # Environment variables take precedence
    host_val = os.environ.get("HOST", host_val)
    port_val = int(os.environ.get("PORT", str(port_val)))

    logger.info(f"Starting Image Tagger WebUI on http://{host_val}:{port_val}")
    if host_val == "127.0.0.1" or host_val == "localhost":
        logger.warning("Binding to 127.0.0.1 — only accessible from this machine. Use 0.0.0.0 for LAN access.")

    uvicorn.run(
        "backend.app:app",
        host=host_val,
        port=port_val,
        reload=True
    )
