import os
import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from PIL import Image as PILImage

from .models import Folder, Image, Tag, SessionLocal
from .image_tagger import core as tagger
from .utils import log_error_with_context, log_performance_metric
from . import globals
from .api.thumbnails import get_thumbnail_path

# Configure logging for this module
logger = logging.getLogger(__name__)

# Image file extensions we'll monitor for changes
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif', '.tif', '.tiff')

class ImageEventHandler(FileSystemEventHandler):
    """Handle file system events for images, process new or modified images"""
    
    def __init__(self, server: str, model: str):
        # Don't store db_session - create fresh session for each event
        self.server = server
        self.model = model
        
    def on_created(self, event):
        """Handle new file creation events"""
        if event.is_directory:
            return
            
        path = Path(event.src_path)
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            self._process_image(path)
            
    def on_modified(self, event):
        """Handle file modification events"""
        if event.is_directory:
            return
            
        path = Path(event.src_path)
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            self._process_image(path)
    
    def _process_image(self, image_path: Path):
        """Process a single image file"""
        start_time = time.time()
        
        try:
            # Create fresh database session for this event
            db = SessionLocal()
            
            try:
                # Check if image already exists in database
                existing_image = db.query(Image).filter_by(path=str(image_path)).first()
                if existing_image:
                    logger.debug(f"Image already in database: {image_path}")
                    return
                
                # Process the image with AI (pass database session for deduplication)
                logger.info(f"Processing new image: {image_path}")
                result = tagger.process_image(
                    image_path, 
                    self.server, 
                    self.model, 
                    quiet=True,
                    return_data=True,
                    db_session=db  # Pass database session for deduplication
                )
                
                if result[0] and result[0] != "skipped" and result[0] is not False:
                    description, tags = result[0], result[1]
                    
                    # Add to database
                    new_image = Image(
                        path=str(image_path),
                        description=description
                    )
                    db.add(new_image)
                    
                    # Add tags
                    for tag_name in tags:
                        tag = db.query(Tag).filter_by(name=tag_name).first()
                        if not tag:
                            tag = Tag(name=tag_name)
                            db.add(tag)
                        new_image.tags.append(tag)
                    
                    db.commit()
                    processed_count = 1
                    logger.info(f"Processed {processed_count}/{total_images_in_folder}: {image_path.name}")
                    
                    # Generate thumbnail for the newly added image
                    try:
                        # Get the image ID that was just added
                        db.refresh(new_image)
                        thumbnail_path = get_thumbnail_path(new_image.id, 200)
                        
                        # Generate thumbnail using PIL
                        with PILImage.open(image_path) as img:
                            # Convert RGBA to RGB if needed
                            if img.mode in ('RGBA', 'LA'):
                                background = PILImage.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'RGBA':
                                    background.paste(img, mask=img.split()[-1])
                                else:
                                    background.paste(img, mask=img.split()[-1])
                                img = background
                            elif img.mode == 'P':
                                img = img.convert('RGB')
                            elif img.mode not in ('RGB', 'L'):
                                img = img.convert('RGB')
                            
                            # Calculate new dimensions while preserving aspect ratio
                            width, height = img.size
                            if width > height:
                                new_width = 200
                                new_height = int(height * (200 / width))
                            else:
                                new_height = 200
                                new_width = int(width * (200 / height))
                            
                            # Create thumbnail
                            img.thumbnail((new_width, new_height), PILImage.Resampling.LANCZOS)
                            
                            # Save thumbnail
                            img.save(thumbnail_path, "JPEG", quality=85, optimize=True)
                            logger.debug(f"Generated thumbnail: {thumbnail_path}")
                            
                    except Exception as e:
                        logger.error(f"Error generating thumbnail for {image_path}: {e}")
                    
                elif result[0] == "skipped":
                    logger.debug(f"Image skipped (already processed): {image_path}")
                else:
                    logger.error(f"Failed to process image: {image_path}")
                    
            except Exception as e:
                db.rollback()
                log_error_with_context(e, {"image_path": str(image_path), "event": "file_processing"})
                logger.error(f"Error processing image {image_path}: {e}")
            finally:
                db.close()
                
        except Exception as e:
            log_error_with_context(e, {"image_path": str(image_path), "event": "file_event"})
            logger.error(f"Fatal error in file event handler for {image_path}: {e}")
        
        finally:
            duration = time.time() - start_time
            log_performance_metric("file_event_processing", duration, success=True, 
                                 extra_data={"image_path": str(image_path)})

    def generate_thumbnail(self, image_path: Path):
        """Generate a thumbnail for the processed image"""
        try:
            # Open the image
            with PILImage.open(image_path) as img:
                # Resize the image to fit within the thumbnail size
                img.thumbnail((200, 200))
                
                # Save the thumbnail
                thumbnail_path = get_thumbnail_path(image_path)
                img.save(thumbnail_path)
                
                logger.info(f"Thumbnail generated and saved: {thumbnail_path}")
        except Exception as e:
            log_error_with_context(e, {"image_path": str(image_path), "event": "thumbnail_generation"})
            logger.error(f"Error generating thumbnail for {image_path}: {e}")

def start_folder_watchers(db_session: Session, server: str, model: str) -> Optional[Observer]:
    """Start watching folders for new images"""
    try:
        # Create fresh database session
        db = SessionLocal()
        
        try:
            # Get all active folders
            active_folders = db.query(Folder).filter_by(active=True).all()
            
            if not active_folders:
                logger.info("No active folders to watch")
                return None
            
            # Create observer
            observer = Observer()
            
            # Add handlers for each folder
            for folder in active_folders:
                try:
                    folder_path = Path(folder.path)
                    if folder_path.exists() and folder_path.is_dir():
                        event_handler = ImageEventHandler(server, model)
                        observer.schedule(event_handler, str(folder_path), recursive=folder.recursive)
                        logger.info(f"Added watcher for folder: {folder.path} (recursive: {folder.recursive})")
                    else:
                        logger.warning(f"Folder does not exist or is not a directory: {folder.path}")
                except Exception as e:
                    logger.error(f"Error adding watcher for folder {folder.path}: {e}")
            
            # Start the observer
            observer.start()
            logger.info(f"Started watching {len(active_folders)} folders")
            return observer
            
        except Exception as e:
            log_error_with_context(e, {"event": "start_folder_watchers"})
            logger.error(f"Error starting folder watchers: {e}")
            return None
        finally:
            db.close()
            
    except Exception as e:
        log_error_with_context(e, {"event": "start_folder_watchers"})
        logger.error(f"Fatal error starting folder watchers: {e}")
        return None

def stop_folder_watchers(observer: Observer):
    """Stop folder watchers"""
    try:
        if observer and observer.is_alive():
            observer.stop()
            observer.join()
            logger.info("Folder watchers stopped")
    except Exception as e:
        log_error_with_context(e, {"event": "stop_folder_watchers"})
        logger.error(f"Error stopping folder watchers: {e}")

def process_existing_images(folder: Folder, server: str, model: str, global_progress_offset: int = 0, total_global_images: int = 0):
    """Process all images in a folder and add them to the database with progress tracking"""
    from . import globals
    from pathlib import Path
    
    # Create a fresh database session for this background task
    db = SessionLocal()
    
    try:
        # DEBUG: Log what server is being used and progress parameters
        logger.info(f"🔧 DEBUG: process_existing_images called with server={server}, model={model}")
        logger.info(f"🔧 DEBUG: Progress parameters - global_progress_offset={global_progress_offset}, total_global_images={total_global_images}")
        
        # Get config options
        config = tagger.load_config()
        
        logger.info(f"Processing existing images in folder: {folder.path}")
        
        # Collect all image files first to get accurate count
        folder_path = Path(folder.path)
        if not folder_path.exists():
            logger.warning(f"Folder does not exist: {folder.path}")
            return 0
        
        # Find all image files
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif', '.tif', '.tiff')
        if folder.recursive:
            all_files = list(folder_path.rglob('*'))
        else:
            all_files = list(folder_path.glob('*'))
            
        image_files = [f for f in all_files if f.suffix.lower() in image_extensions and f.is_file()]
        
        # Sort files by modification time, newest first
        process_newest_first = config.get("process_newest_first", True)
        if process_newest_first:
            image_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            logger.info("Files sorted by modification time, processing newest first")
        
        # Filter out images already in database
        new_image_files = []
        for image_file in image_files:
            existing = db.query(Image).filter_by(path=str(image_file)).first()
            if not existing:
                new_image_files.append(image_file)
        
        total_images_in_folder = len(new_image_files)
        logger.info(f"Found {total_images_in_folder} new images to process in {folder.path}")
        
        if total_images_in_folder == 0:
            logger.info(f"No new images to process in {folder.path}")
            return 0
        
        # Update global progress
        if hasattr(globals, 'app_state'):
            globals.app_state.task_total = total_global_images if total_global_images > 0 else total_images_in_folder
            globals.app_state.completed_tasks = global_progress_offset
        
        processed_count = 0
        
        # Process each image
        for idx, file_path in enumerate(new_image_files):
            try:
                # Update progress
                if hasattr(globals, 'app_state'):
                    current_progress = ((global_progress_offset + idx) / globals.app_state.task_total) * 100
                    globals.app_state.task_progress = current_progress
                    globals.app_state.current_task = f"Processing {file_path.name}"
                
                # Process the image with AI (pass database session for deduplication)
                result = tagger.process_image(
                    file_path, 
                    server, 
                    model, 
                    quiet=True,
                    return_data=True,
                    db_session=db  # Pass database session for deduplication
                )
                
                if result[0] and result[0] != "skipped" and result[0] is not False:
                    description, tags = result[0], result[1]
                    
                    # Add to database
                    new_image = Image(
                        path=str(file_path),
                        description=description
                    )
                    db.add(new_image)
                    
                    # Add tags
                    for tag_name in tags:
                        tag = db.query(Tag).filter_by(name=tag_name).first()
                        if not tag:
                            tag = Tag(name=tag_name)
                            db.add(tag)
                        new_image.tags.append(tag)
                    
                    db.commit()
                    processed_count += 1
                    logger.info(f"Processed {processed_count}/{total_images_in_folder}: {file_path.name}")
                    
                    # Generate thumbnail for the newly added image
                    try:
                        # Get the image ID that was just added
                        db.refresh(new_image)
                        thumbnail_path = get_thumbnail_path(new_image.id, 200)
                        
                        # Generate thumbnail using PIL
                        with PILImage.open(file_path) as img:
                            # Convert RGBA to RGB if needed
                            if img.mode in ('RGBA', 'LA'):
                                background = PILImage.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'RGBA':
                                    background.paste(img, mask=img.split()[-1])
                                else:
                                    background.paste(img, mask=img.split()[-1])
                                img = background
                            elif img.mode == 'P':
                                img = img.convert('RGB')
                            elif img.mode not in ('RGB', 'L'):
                                img = img.convert('RGB')
                            
                            # Calculate new dimensions while preserving aspect ratio
                            width, height = img.size
                            if width > height:
                                new_width = 200
                                new_height = int(height * (200 / width))
                            else:
                                new_height = 200
                                new_width = int(width * (200 / height))
                            
                            # Create thumbnail
                            img.thumbnail((new_width, new_height), PILImage.Resampling.LANCZOS)
                            
                            # Save thumbnail
                            img.save(thumbnail_path, "JPEG", quality=85, optimize=True)
                            logger.debug(f"Generated thumbnail: {thumbnail_path}")
                            
                    except Exception as e:
                        logger.error(f"Error generating thumbnail for {file_path}: {e}")
                    
                elif result[0] == "skipped":
                    logger.debug(f"Skipped already processed file: {file_path}")
                else:
                    logger.error(f"Failed to process image: {file_path}")
                
                # Update completed tasks count
                if hasattr(globals, 'app_state'):
                    globals.app_state.completed_tasks = global_progress_offset + idx + 1
                
            except Exception as e:
                logger.error(f"Error processing image {file_path}: {str(e)}")
                db.rollback()  # Rollback on error
                continue
        
        logger.info(f"Completed processing {processed_count}/{total_images_in_folder} images in {folder.path}")
        return processed_count
        
    except Exception as e:
        logger.error(f"Fatal error in process_existing_images for folder {folder.path}: {str(e)}")
        db.rollback()
        return 0
    finally:
        db.close()

def process_images_with_ai(images, server: str, model: str, progress_tracker=None):
    """Process a list of images with AI and update their descriptions"""
    # Create a fresh database session for this background task
    db = SessionLocal()
    
    try:
        total_images = len(images)
        processed_count = 0
        error_count = 0
        max_retries = 3
        retry_delay = 30
        
        logger.info(f"Starting AI processing for {total_images} images")
        
        for idx, image in enumerate(images):
            try:
                if progress_tracker:
                    progress_tracker.update({
                        "current_task": f"Processing image {idx + 1} of {total_images}: {os.path.basename(image.path)}",
                        "progress": (idx / total_images) * 100,
                        "completed_tasks": idx,
                        "task_total": total_images
                    })
                
                # Check if image file still exists
                if not Path(image.path).exists():
                    logger.warning(f"Skipping {image.path} - file not found")
                    continue
                
                # Process the image with AI (with retry logic and database session)
                success = False
                for attempt in range(max_retries):
                    try:
                        result = tagger.process_image(
                            image.path, 
                            server, 
                            model, 
                            quiet=True,
                            return_data=True,
                            db_session=db  # Pass database session for deduplication
                        )
                        
                        if result[0] and result[0] != "skipped" and result[0] is not False:
                            description, tags = result[0], result[1]
                            
                            # Update the image in database
                            image.description = description
                            
                            # Clear existing tags and add new ones
                            image.tags.clear()
                            for tag_name in tags:
                                tag = db.query(Tag).filter_by(name=tag_name).first()
                                if not tag:
                                    tag = Tag(name=tag_name)
                                    db.add(tag)
                                image.tags.append(tag)
                            
                            db.commit()
                            processed_count += 1
                            success = True
                            logger.info(f"Successfully processed {image.path}")
                            break
                            
                        elif result[0] == "skipped":
                            logger.info(f"Skipped already processed image: {image.path}")
                            success = True
                            break
                            
                        else:
                            logger.warning(f"No description or tags returned for {image.path}")
                            if attempt == max_retries - 1:
                                error_count += 1
                            else:
                                logger.info(f"Retrying in {retry_delay} seconds...")
                                time.sleep(retry_delay)
                            
                    except Exception as e:
                        logger.error(f"Error processing image {image.path} (attempt {attempt + 1}): {str(e)}")
                        if attempt == max_retries - 1:
                            error_count += 1
                        else:
                            logger.info(f"Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                    
            except Exception as e:
                logger.critical(f"Fatal error processing image {image.path}: {str(e)}")
                error_count += 1
                continue
        
        if progress_tracker:
            progress_tracker.update({
                "current_task": f"AI processing completed - {processed_count} processed, {error_count} errors",
                "progress": 100.0,
                "completed_tasks": total_images,
                "task_total": total_images
            })
            
    except Exception as e:
        logger.error(f"Fatal error in process_images_with_ai: {str(e)}")
        db.rollback()
    finally:
        db.close()

def scan_folders_for_images(folders, progress_tracker=None):
    """Scan folders for new images and add them to database"""
    # Create a fresh database session for this background task
    db = SessionLocal()
    
    try:
        total_folders = len(folders)
        new_images_count = 0
        
        # Update initial progress
        if progress_tracker:
            progress_tracker.update({
                "current_task": f"Starting scan of {total_folders} folders",
                "progress": 0.0,
                "completed_tasks": 0,
                "task_total": total_folders
            })
        
        for idx, folder in enumerate(folders):
            try:
                if progress_tracker:
                    progress_tracker.update({
                        "current_task": f"Scanning folder {idx + 1} of {total_folders}: {os.path.basename(folder.path)}",
                        "progress": (idx / total_folders) * 100,
                        "completed_tasks": idx,
                        "task_total": total_folders
                    })
                
                folder_path = Path(folder.path)
                if not folder_path.exists():
                    continue
                
                # Find image files in the folder
                if folder.recursive:
                    image_files = []
                    for ext in IMAGE_EXTENSIONS:
                        image_files.extend(folder_path.rglob(f"*{ext}"))
                        image_files.extend(folder_path.rglob(f"*{ext.upper()}"))
                else:
                    image_files = []
                    for ext in IMAGE_EXTENSIONS:
                        image_files.extend(folder_path.glob(f"*{ext}"))
                        image_files.extend(folder_path.glob(f"*{ext.upper()}"))
                
                # Add new images to database
                for image_file in image_files:
                    try:
                        existing = db.query(Image).filter_by(path=str(image_file)).first()
                        if not existing:
                            new_image = Image(path=str(image_file))
                            db.add(new_image)
                            new_images_count += 1
                    except Exception as e:
                        logger.error(f"Error adding image {image_file} to database: {e}")
                        continue
                
                db.commit()
                logger.info(f"Scanned folder {folder.path}: found {len(image_files)} images, {new_images_count} new")
                
            except Exception as e:
                logger.error(f"Error scanning folder {folder.path}: {e}")
                db.rollback()
                continue
        
        logger.info(f"Folder scanning completed: {new_images_count} new images found")
        return new_images_count
        
    except Exception as e:
        logger.error(f"Fatal error in scan_folders_for_images: {str(e)}")
        db.rollback()
        return 0
    finally:
        db.close()
