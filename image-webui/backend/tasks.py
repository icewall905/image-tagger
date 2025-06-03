import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy.orm import Session

from models import Folder, Image, Tag
from image_tagger import core as tagger

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

def _folder_for_path(path: Path, db_session: Session) -> Folder:
    """Find the folder in the database that contains this path"""
    path_str = str(path)
    folders = db_session.query(Folder).filter_by(active=True).all()
    
    for folder in folders:
        if path_str.startswith(folder.path):
            return folder
    
    return None

def process_existing_images(folder: Folder, db_session: Session, server: str, model: str):
    """Process all images in a folder and add them to the database"""
    # Get config options
    config = tagger.load_config()
    
    # Process the directory
    results = tagger.process_directory(
        folder.path,
        server=server,
        model=model,
        recursive=folder.recursive,
        return_data=True
    )
    
    # Add each result to the database
    for file_path, description, tags in results:
        # Skip if image is already in database
        existing = db_session.query(Image).filter_by(path=str(file_path)).first()
        if existing:
            continue
            
        # Create image record
        img = Image(path=str(file_path), description=description)
        
        # Add tags
        for tag_name in tags:
            tag = db_session.query(Tag).filter_by(name=tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db_session.add(tag)
                
            img.tags.append(tag)
            
        db_session.add(img)
        db_session.commit()

def start_folder_watchers(db_session, server: str, model: str):
    """Start watching all active folders in the database"""
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
