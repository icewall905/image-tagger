import os
import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any

from .models import Folder, Image, Tag
from .image_tagger import core as tagger

# Configure logging for this module
logger = logging.getLogger(__name__)

# Image file extensions we'll monitor for changes
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif', '.tif', '.tiff')

class ImageEventHandler(FileSystemEventHandler):
    """Handle file system events for images, process new or modified images"""
    
    def __init__(self, db_session: Session, server: str, model: str):
        self.db = db_session
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
            # Check if the file exists in the database
            existing = self.db.query(Image).filter_by(path=str(path)).first()
            if existing:
                # If it exists, delete it and reprocess
                self.db.delete(existing)
                self.db.commit()
            
            self._process_image(path)
    
    def _process_image(self, path: Path):
        """Process an image and add it to the database"""
        # Check if the image is already in the database
        existing = self.db.query(Image).filter_by(path=str(path)).first()
        if existing:
            return
            
        # Process the image with the AI model
        desc, tags = tagger.process_image(
            path, 
            server=self.server,
            model=self.model,
            return_data=True
        )
        
        if desc is False or not tags:
            return
            
        # Create a new image record
        img = Image(path=str(path), description=desc)
        
        # Add or retrieve tags
        for tag_name in tags:
            tag = self.db.query(Tag).filter_by(name=tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                self.db.add(tag)
            
            img.tags.append(tag)
            
        self.db.add(img)
        self.db.commit()

def _folder_for_path(path: Path, db_session: Session) -> Optional[Folder]:
    """Find the folder in the database that contains this path"""
    path_str = str(path)
    folders = db_session.query(Folder).filter_by(active=True).all()
    
    for folder in folders:
        if path_str.startswith(folder.path):
            return folder
    
    return None

def process_existing_images(folder: Folder, db_session: Session, server: str, model: str, global_progress_offset: int = 0, total_global_images: int = 0):
    """Process all images in a folder and add them to the database with progress tracking"""
    from . import globals
    from pathlib import Path
    
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
    
    # Filter out images already in database
    new_image_files = []
    for image_file in image_files:
        existing = db_session.query(Image).filter_by(path=str(image_file)).first()
        if not existing:
            new_image_files.append(image_file)
    
    total_images_in_folder = len(new_image_files)
    logger.info(f"Found {total_images_in_folder} new images to process in {folder.path}")
    
    if total_images_in_folder == 0:
        return 0
    
    # Process each image with progress updates
    processed_count = 0
    
    for idx, file_path in enumerate(new_image_files):
        try:
            # Calculate global progress if we have the total
            if total_global_images > 0:
                global_idx = global_progress_offset + idx
                progress_percent = (global_idx / total_global_images) * 100
                globals.app_state.task_progress = progress_percent
                globals.app_state.current_task = f"Processing image {global_idx + 1} of {total_global_images}: {file_path.name}"
            else:
                # Fallback to folder-level progress
                progress_percent = (idx / total_images_in_folder) * 100
                globals.app_state.task_progress = progress_percent
                globals.app_state.current_task = f"Processing image {idx + 1} of {total_images_in_folder}: {file_path.name}"
            
            # Process the image
            desc, tags = tagger.process_image(
                str(file_path),
                server=server,
                model=model,
                return_data=True
            )
            
            if desc is False or not tags:
                logger.warning(f"Failed to process image: {file_path}")
                continue
                
            # Handle boolean description (when processing succeeds but returns True)
            description = "" if isinstance(desc, bool) else desc
                
            # Create image record
            img = Image(path=str(file_path), description=description)
            
            # Add tags
            if tags:  # Only process tags if they exist
                for tag_name in tags:
                    tag = db_session.query(Tag).filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        db_session.add(tag)
                        
                    img.tags.append(tag)
                
            db_session.add(img)
            db_session.commit()
            processed_count += 1
            
            logger.info(f"Successfully processed image {idx + 1}/{total_images_in_folder}: {file_path.name}")
            
        except Exception as e:
            logger.error(f"Error processing image {file_path}: {str(e)}")
            continue
    
    logger.info(f"Completed processing {processed_count}/{total_images_in_folder} images in {folder.path}")
    return processed_count

def start_folder_watchers(db_session, server: str, model: str):
    """Start watching all active folders in the database"""
    import os
    
    # Check if folder watchers are disabled
    if os.environ.get('DISABLE_FOLDER_WATCHERS') == '1':
        logger.info("Folder watchers disabled by environment variable")
        return None
        
    observer = Observer()
    
    # Get all active folders
    folders = db_session.query(Folder).filter_by(active=True).all()
    
    # Schedule handlers for each folder
    for folder in folders:
        handler = ImageEventHandler(db_session, server, model)
        observer.schedule(handler, folder.path, recursive=folder.recursive)
    
    # Start the observer
    observer.start()
    return observer

def add_folder_to_observer(observer, folder_path, recursive, db_session, server, model):
    """Add a new folder to an existing observer"""
    if observer and observer.is_alive():
        handler = ImageEventHandler(db_session, server, model)
        observer.schedule(handler, folder_path, recursive=recursive)
        return True
    return False

def stop_folder_watchers(observer):
    """Stop watching folders"""
    if observer:
        observer.stop()
        observer.join()

def process_images_with_ai(images, db_session: Session, server: str, model: str, progress_tracker=None):
    """Process a list of images with AI and update database"""
    total_images = len(images)
    processed_count = 0
    error_count = 0
    
    for idx, image in enumerate(images):
        try:
            if progress_tracker:
                progress_tracker.update({
                    "current_task": f"Processing image {idx + 1} of {total_images}: {os.path.basename(image.path)}",
                    "progress": (idx / total_images) * 100,
                    "completed_tasks": idx
                })
            
            # Check if image file still exists
            if not Path(image.path).exists():
                logger.warning(f"Skipping {image.path} - file not found")
                continue
            
            # Process the image with AI (with retry logic)
            max_retries = 3
            retry_delay = 30  # Wait 30 seconds between retries for vision models
            
            for attempt in range(max_retries):
                try:
                    desc, tags = tagger.process_image(
                        Path(image.path),
                        server=server,
                        model=model,
                        return_data=True
                    )
                    
                    if desc and tags:
                        # Update the image description
                        image.description = desc
                        
                        # Clear existing tags first to avoid duplicates
                        image.tags.clear()
                        
                        # Add new tags
                        for tag_name in tags:
                            tag = db_session.query(Tag).filter_by(name=tag_name).first()
                            if not tag:
                                tag = Tag(name=tag_name)
                                db_session.add(tag)
                                db_session.flush()  # Ensure tag gets an ID
                            
                            image.tags.append(tag)
                        
                        db_session.commit()
                        processed_count += 1
                        break  # Success, exit retry loop
                        
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
            "completed_tasks": total_images
        })

def scan_folders_for_images(folders, db_session: Session, progress_tracker=None):
    """Scan folders for new images and add them to database"""
    total_folders = len(folders)
    new_images_count = 0
    
    for idx, folder in enumerate(folders):
        try:
            if progress_tracker:
                progress_tracker.update({
                    "current_task": f"Scanning folder {idx + 1} of {total_folders}: {os.path.basename(folder.path)}",
                    "progress": (idx / total_folders) * 100,
                    "completed_tasks": idx
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
            
            # Check each image file
            for image_file in image_files:
                # Skip if already in database
                existing = db_session.query(Image).filter_by(path=str(image_file)).first()
                if existing:
                    continue
                
                # Add new image to database (without AI processing)
                new_image = Image(path=str(image_file), description="")
                db_session.add(new_image)
                new_images_count += 1
            
            db_session.commit()
            
        except Exception as e:
            logger.error(f"Error scanning folder {folder.path}: {str(e)}")
            continue
    
    if progress_tracker:
        progress_tracker.update({
            "current_task": f"Scan completed - {new_images_count} new images found",
            "progress": 100.0,
            "completed_tasks": total_folders
        })
