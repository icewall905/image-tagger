from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Dict, Any, List
import requests
import re
import urllib.parse
import os
import shutil
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import Config
from .. import globals
from .. import models
from .. import schemas

# Remove the prefix to avoid double prefixing in app.py
router = APIRouter(tags=["settings"])

# Add the schema classes if they don't exist in the schemas.py file
class ConfigUpdateRequest(BaseModel):
    config: Dict[str, Dict[str, Any]]

class ConfigResponse(BaseModel):
    message: str
    config: Dict[str, Dict[str, Any]]

class OllamaTestConfig(BaseModel):
    server: str
    model: str

# Add the configuration endpoints
@router.get("/settings/config", response_model=ConfigResponse)
def get_config():
    """Get current configuration values"""
    try:
        # Get the entire configuration
        config_dict = {}
        for section in Config.sections():
            config_dict[section] = {}
            for key, value in Config.items(section):
                # Convert value types appropriately
                if value.lower() in ['true', 'false']:
                    config_dict[section][key] = value.lower() == 'true'
                elif value.isdigit():
                    config_dict[section][key] = int(value)
                elif re.match(r'^-?\d+\.\d+$', value):
                    config_dict[section][key] = float(value)
                else:
                    config_dict[section][key] = value

        return {"message": "Configuration loaded successfully", "config": config_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading configuration: {str(e)}")

@router.post("/settings/config", response_model=schemas.MessageResponse)
def save_config(config_data: ConfigUpdateRequest):
    """Save configuration values"""
    try:
        config_dict = config_data.config
        
        # Update each section and key in the configuration
        for section, section_data in config_dict.items():
            if not Config.has_section(section):
                Config.add_section(section)
                
            for key, value in section_data.items():
                # Convert value types to strings for ConfigParser
                if isinstance(value, bool):
                    value_str = str(value).lower()
                else:
                    value_str = str(value)
                    
                Config.set(section, key, value_str)
        
        # Save the configuration to file
        Config.save()
        return {"message": "Configuration saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving configuration: {str(e)}")

# Keep existing test-ollama endpoint or add it if it doesn't exist
@router.post("/settings/test-ollama", response_model=schemas.MessageResponse)
def test_ollama(ollama_config: OllamaTestConfig):
    """Test connection to Ollama server"""
    try:
        server = ollama_config.server
        model = ollama_config.model
        
        # Add http:// prefix if not present
        if not server.startswith(("http://", "https://")):
            server = f"http://{server}"
            
        # Extract host and port
        parsed_url = urllib.parse.urlparse(server)
        host = parsed_url.netloc.split(':')[0]
        port = parsed_url.netloc.split(':')[1] if ':' in parsed_url.netloc else "11434"
        
        # Try to connect to Ollama server
        response = requests.get(f"{server}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json()
            available_models = [m['name'] for m in models.get('models', [])]
            
            # Check if the specified model is available
            if model in available_models:
                return {"message": f"Successfully connected to Ollama. Model '{model}' is available."}
            else:
                return {"message": f"Connected to Ollama, but model '{model}' is not available. Available models: {', '.join(available_models)}"}
        else:
            raise HTTPException(status_code=400, detail=f"Ollama server returned status {response.status_code}")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=400, detail=f"Could not connect to Ollama server at {server}")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=400, detail=f"Connection to Ollama server timed out")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error testing Ollama connection: {str(e)}")

# Add new endpoints for the settings page functionality
@router.post("/settings/test-db", response_model=schemas.MessageResponse)
def test_database_connection():
    """Test database connection"""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.sql import text
        import os
        
        # Get the database path from environment or config
        db_path = Config.get('database', 'path', fallback="sqlite:///data/image_tagger.db")
        if 'DB_PATH' in os.environ:
            db_path = os.environ["DB_PATH"]
            
        # Test connection by creating an engine and executing a simple query
        engine = create_engine(db_path)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            row = result.fetchone()
            if row and row[0] == 1:
                return {"message": "Database connection successful"}
            else:
                raise HTTPException(status_code=500, detail="Database test query failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

@router.post("/settings/backup-db", response_model=schemas.MessageResponse)
def backup_database():
    """Backup the database"""
    try:
        from datetime import datetime
        
        # Get the database file path (extract from SQLite connection string)
        db_path = Config.get('database', 'path', fallback="sqlite:///data/image_tagger.db")
        if 'DB_PATH' in os.environ:
            db_path = os.environ["DB_PATH"]
        
        # Ensure db_path is not None
        if not db_path:
            db_path = "sqlite:///data/image_tagger.db"
            
        # For SQLite, extract the file path
        if db_path.startswith('sqlite:///'):
            db_file = db_path[10:]  # Remove 'sqlite:///'
        else:
            raise HTTPException(status_code=400, detail="Database backup only supported for SQLite databases")
            
        # Create backups directory if it doesn't exist
        backup_dir = os.path.join(os.path.dirname(db_file), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        # Create a timestamped backup file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"image_tagger_{timestamp}.db")
        
        # Copy the database file
        shutil.copy2(db_file, backup_file)
        
        return {"message": f"Database backed up successfully to {backup_file}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database backup failed: {str(e)}")

@router.post("/settings/reset-db", response_model=schemas.MessageResponse)
def reset_database():
    """Reset the database (DANGEROUS: removes all data)"""
    try:
        from sqlalchemy import create_engine
        from ..models import Base
        
        # Get the database path
        db_path = Config.get('database', 'path', fallback="sqlite:///data/image_tagger.db")
        if 'DB_PATH' in os.environ:
            db_path = os.environ["DB_PATH"]
        
        # Create the engine
        engine = create_engine(db_path)
        
        # Drop all tables and recreate them
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        
        return {"message": "Database has been reset successfully. All data has been removed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database reset failed: {str(e)}")

@router.post("/settings/test-storage", response_model=schemas.MessageResponse)
def test_storage_access():
    """Test access to storage directories"""
    try:
        
        # Get the thumbnail directory
        thumbnail_dir = Config.get('storage', 'thumbnail_dir', fallback="data/thumbnails")
        
        # Ensure thumbnail_dir is not None
        if not thumbnail_dir:
            thumbnail_dir = "data/thumbnails"
        
        # Check if directory exists, create it if it doesn't
        if not os.path.exists(thumbnail_dir):
            os.makedirs(thumbnail_dir)
        
        # Test write access by creating a test file
        test_file = os.path.join(thumbnail_dir, "test_access.txt")
        with open(test_file, 'w') as f:
            f.write("Storage access test")
        
        # Clean up the test file
        os.remove(test_file)
        
        return {"message": f"Storage access test successful. Directory {thumbnail_dir} is writable."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage access test failed: {str(e)}")

@router.post("/settings/clear-thumbnails", response_model=schemas.MessageResponse)
def clear_thumbnail_cache():
    """Clear the thumbnail cache"""
    try:
        
        # Get the thumbnail directory
        thumbnail_dir = Config.get('storage', 'thumbnail_dir', fallback="data/thumbnails")
        
        # Ensure thumbnail_dir is not None
        if not thumbnail_dir:
            thumbnail_dir = "data/thumbnails"
        
        # Check if directory exists
        if os.path.exists(thumbnail_dir):
            # Remove all files in the directory
            for file in os.listdir(thumbnail_dir):
                file_path = os.path.join(thumbnail_dir, file)
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
        
        return {"message": "Thumbnail cache cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear thumbnail cache: {str(e)}")

@router.get("/settings/stats", response_model=Dict[str, Any])
def get_statistics(db: Session = Depends(models.get_db)):
    """Get system statistics"""
    try:
        # Count folders
        folder_count = db.query(models.Folder).count()
        
        # Count images
        image_count = db.query(models.Image).count()
        
        # Count tags
        tag_count = db.query(models.Tag).count()
        
        # Count unprocessed images (those without descriptions)
        unprocessed_count = db.query(models.Image).filter(models.Image.description.is_(None)).count()
        
        # Get storage info
        thumbnail_dir = Config.get('storage', 'thumbnail_dir', fallback="data/thumbnails")
        
        # Ensure thumbnail_dir is not None
        if not thumbnail_dir:
            thumbnail_dir = "data/thumbnails"
            
        thumbnail_size = 0
        thumbnail_count = 0
        
        if os.path.exists(thumbnail_dir):
            for root, dirs, files in os.walk(thumbnail_dir):
                thumbnail_count += len(files)
                for f in files:
                    fp = os.path.join(root, f)
                    thumbnail_size += os.path.getsize(fp)
        
        # Return statistics
        return {
            "folder_count": folder_count,
            "image_count": image_count,
            "tag_count": tag_count,
            "queue_count": unprocessed_count,
            "thumbnail_count": thumbnail_count,
            "thumbnail_size": thumbnail_size,
            "thumbnail_size_formatted": format_file_size(thumbnail_size)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")

def format_file_size(size_bytes):
    """Format a file size in bytes to a human-readable string"""
    if size_bytes == 0:
        return "0B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    i = 0
    while size_bytes >= 1024 and i < len(units)-1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.2f} {units[i]}"

@router.post("/settings/process-all-images", response_model=schemas.MessageResponse)
def process_all_images(background_tasks: BackgroundTasks, db: Session = Depends(models.get_db)):
    """Process all unprocessed images with AI"""
    # Check if there is already a processing task running
    if globals.app_state.is_scanning:
        raise HTTPException(status_code=400, detail="A processing task is already running")
    
    try:
        # Update the app state
        globals.app_state.is_scanning = True
        globals.app_state.current_task = "Preparing to process images"
        globals.app_state.task_progress = 0
        globals.app_state.task_total = 0
        globals.app_state.completed_tasks = 0
        globals.app_state.last_error = None
        
        # Get all images without descriptions
        unprocessed_images = db.query(models.Image).filter(models.Image.description.is_(None)).all()
        
        if not unprocessed_images:
            globals.app_state.is_scanning = False
            return {"status": "success", "message": "No unprocessed images found"}
        
        # Get the Ollama server and model settings
        server = Config.get('ollama', 'server')
        model = Config.get('ollama', 'model')
        
        # DEBUG: Log configuration loading for process operation
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔧 DEBUG process_all_images: Config raw values - server={repr(server)}, model={repr(model)}")
        
        # Apply defaults only if values are None or empty
        if not server:
            server = "http://127.0.0.1:11434"
            logger.info(f"🔧 DEBUG process_all_images: Server defaulted because value was falsy: {repr(server)}")
        if not model:
            model = "qwen2.5vl:latest"
            logger.info(f"🔧 DEBUG process_all_images: Model defaulted because value was falsy: {repr(model)}")
        
        # Environment variables override config
        if 'OLLAMA_SERVER' in os.environ:
            server = os.environ["OLLAMA_SERVER"]
            logger.info(f"🔧 DEBUG process_all_images: Server overridden by env var: {server}")
        if 'OLLAMA_MODEL' in os.environ:
            model = os.environ["OLLAMA_MODEL"]
            logger.info(f"🔧 DEBUG process_all_images: Model overridden by env var: {model}")
            
        logger.info(f"🔧 DEBUG process_all_images: Final values - server={server}, model={model}")
        
        # Update total number of images to process
        globals.app_state.task_total = len(unprocessed_images)
        
        # Add the processing task to the background
        from ..tasks import process_images_with_ai
        background_tasks.add_task(
            process_images_with_ai,
            unprocessed_images,
            db,
            server,
            model,
            globals.app_state
        )
        
        return {"status": "success", "message": f"Started processing {len(unprocessed_images)} images with AI"}
    except Exception as e:
        globals.app_state.is_scanning = False
        globals.app_state.last_error = str(e)
        raise HTTPException(status_code=500, detail=f"Failed to start image processing: {str(e)}")

@router.post("/settings/scan-all-folders", response_model=schemas.MessageResponse)
def scan_all_folders(background_tasks: BackgroundTasks, db: Session = Depends(models.get_db)):
    """Scan all active folders for new images"""
    # Check if there is already a processing task running
    if globals.app_state.is_scanning:
        raise HTTPException(status_code=400, detail="A processing task is already running")
    
    try:
        # Update the app state
        globals.app_state.is_scanning = True
        globals.app_state.current_task = "Preparing to scan folders"
        globals.app_state.task_progress = 0
        globals.app_state.task_total = 0
        globals.app_state.completed_tasks = 0
        globals.app_state.last_error = None
        
        # Get all active folders
        active_folders = db.query(models.Folder).filter_by(active=True).all()
        
        if not active_folders:
            globals.app_state.is_scanning = False
            return {"status": "success", "message": "No active folders found"}
        
        # Get the Ollama server and model settings
        server = Config.get('ollama', 'server')
        model = Config.get('ollama', 'model')
        
        # DEBUG: Log configuration loading for scan operation
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔧 DEBUG scan_all_folders: Config raw values - server={repr(server)}, model={repr(model)}")
        
        # Apply defaults only if values are None or empty
        if not server:
            server = "http://127.0.0.1:11434"
            logger.info(f"🔧 DEBUG scan_all_folders: Server defaulted because value was falsy: {repr(server)}")
        if not model:
            model = "qwen2.5vl:latest"
            logger.info(f"🔧 DEBUG scan_all_folders: Model defaulted because value was falsy: {repr(model)}")
        
        # Environment variables override config
        if 'OLLAMA_SERVER' in os.environ:
            server = os.environ["OLLAMA_SERVER"]
            logger.info(f"🔧 DEBUG scan_all_folders: Server overridden by env var: {server}")
        if 'OLLAMA_MODEL' in os.environ:
            model = os.environ["OLLAMA_MODEL"]
            logger.info(f"🔧 DEBUG scan_all_folders: Model overridden by env var: {model}")
            
        logger.info(f"🔧 DEBUG scan_all_folders: Final values - server={server}, model={model}")
        
        # First pass: count total images across all folders for accurate progress
        total_images = 0
        folder_image_counts = {}
        
        for folder in active_folders:
            from pathlib import Path
            folder_path = Path(folder.path)
            if not folder_path.exists():
                folder_image_counts[folder.id] = 0
                continue
                
            # Find image files
            image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif', '.tif', '.tiff')
            if folder.recursive:
                all_files = list(folder_path.rglob('*'))
            else:
                all_files = list(folder_path.glob('*'))
                
            image_files = [f for f in all_files if f.suffix.lower() in image_extensions and f.is_file()]
            
            # Filter out images already in database
            new_image_count = 0
            for image_file in image_files:
                existing = db.query(models.Image).filter_by(path=str(image_file)).first()
                if not existing:
                    new_image_count += 1
                    
            folder_image_counts[folder.id] = new_image_count
            total_images += new_image_count
        
        # Update total number of images to scan (not folders)
        globals.app_state.task_total = total_images
        globals.app_state.completed_tasks = 0  # Reset completed tasks
        
        # DEBUG: Log initial state setup
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔧 DEBUG scan_all_folders: Initial state - task_total={total_images}, completed_tasks=0")
        
        if total_images == 0:
            globals.app_state.is_scanning = False
            return {"status": "success", "message": "No new images found to process"}
        
        # Process each folder in the background
        from ..tasks import process_existing_images
        
        async def process_all_folders():
            try:
                processed_images = 0
                logger.info(f"🔧 DEBUG process_all_folders: Starting with total_images={total_images}")
                
                for idx, folder in enumerate(active_folders):
                    folder_image_count = folder_image_counts.get(folder.id, 0)
                    
                    if folder_image_count == 0:
                        continue  # Skip folders with no new images
                    
                    # Update the app state for folder-level progress
                    globals.app_state.current_task = f"Starting scan of folder {idx + 1} of {len(active_folders)}: {folder.path}"
                    logger.info(f"🔧 DEBUG: Processing folder {idx + 1}/{len(active_folders)} with {folder_image_count} images")
                    
                    # Process the folder with global progress tracking
                    folder_processed = process_existing_images(
                        folder, 
                        db, 
                        server, 
                        model, 
                        global_progress_offset=processed_images,
                        total_global_images=total_images
                    )
                    
                    processed_images += folder_processed
                    logger.info(f"🔧 DEBUG: Processed {folder_processed} images from folder. Total processed: {processed_images}/{total_images}")
                
                # Mark as complete
                globals.app_state.is_scanning = False
                globals.app_state.task_progress = 100
                globals.app_state.completed_tasks = processed_images
                globals.app_state.current_task = f"Scanning complete - processed {processed_images} images"
                logger.info(f"🔧 DEBUG: Scan complete - final state: completed_tasks={processed_images}, task_total={globals.app_state.task_total}")
            except Exception as e:
                globals.app_state.is_scanning = False
                globals.app_state.last_error = str(e)
                logger.error(f"🔧 DEBUG: Error in process_all_folders: {str(e)}")
        
        background_tasks.add_task(process_all_folders)
        
        return {"status": "success", "message": f"Started scanning {len(active_folders)} folders for new images"}
    except Exception as e:
        globals.app_state.is_scanning = False
        globals.app_state.last_error = str(e)
        raise HTTPException(status_code=500, detail=f"Failed to start folder scanning: {str(e)}")

@router.get("/settings/processing-status", response_model=Dict[str, Any])
def get_processing_status():
    """Get the current status of processing tasks"""
    try:
        # Log current state for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔧 DEBUG: API processing-status - task_total={globals.app_state.task_total}, completed_tasks={globals.app_state.completed_tasks}, is_scanning={globals.app_state.is_scanning}")
        
        # Return the current state
        return {
            "active": globals.app_state.is_scanning,
            "current_task": globals.app_state.current_task,
            "progress": globals.app_state.task_progress,
            "total_tasks": globals.app_state.task_total,
            "completed_tasks": globals.app_state.completed_tasks,
            "error": globals.app_state.last_error
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get processing status: {str(e)}")
