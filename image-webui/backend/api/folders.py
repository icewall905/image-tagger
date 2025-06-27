from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

import os
from pathlib import Path

from ..models import Folder, get_db
from ..tasks import process_existing_images
from .. import globals

router = APIRouter()

# Pydantic models for request/response
class FolderCreate(BaseModel):
    path: str
    recursive: bool = True

class FolderResponse(BaseModel):
    id: int
    path: str
    recursive: bool
    active: bool
    added_at: datetime
    
    class Config:
        from_attributes = True

class FileBrowserItem(BaseModel):
    name: str
    path: str
    is_dir: bool
    is_readable: bool
    size: Optional[int] = None
    modified: Optional[datetime] = None

class FileBrowserResponse(BaseModel):
    current_path: str
    parent_path: Optional[str] = None
    items: List[FileBrowserItem]

@router.get("/folders", response_model=List[FolderResponse])
def list_folders(db: Session = Depends(get_db)):
    """List all watched folders"""
    folders = db.query(Folder).all()
    return folders

@router.post("/folders", response_model=FolderResponse)
def add_folder(folder: FolderCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Add a new folder to watch"""
    # Check if the path exists
    path = Path(folder.path)
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail="Folder path does not exist")
    
    # Check if it's already being watched
    existing = db.query(Folder).filter_by(path=folder.path).first()
    if existing:
        raise HTTPException(status_code=400, detail="Folder is already being watched")
    
    # Create the folder record
    new_folder = Folder(
        path=folder.path,
        recursive=folder.recursive
    )
    
    db.add(new_folder)
    db.commit()
    db.refresh(new_folder)
    
    # Get Ollama settings from config or environment
    from ..config import Config
    ollama_server_val = Config.get('ollama', 'server', fallback="http://127.0.0.1:11434")
    ollama_model_val = Config.get('ollama', 'model', fallback="qwen2.5vl:latest")
    
    # Environment variables override config
    if 'OLLAMA_SERVER' in os.environ:
        ollama_server_val = os.environ["OLLAMA_SERVER"]
    if 'OLLAMA_MODEL' in os.environ:
        ollama_model_val = os.environ["OLLAMA_MODEL"]
    
    # Process existing images in the background
    # BackgroundTasks should ideally use their own sessions.
    # process_existing_images now creates its own database session
    background_tasks.add_task(
        process_existing_images, 
        new_folder, 
        ollama_server_val,
        ollama_model_val
    )
    
    return new_folder

@router.delete("/folders/{folder_id}", response_model=dict)
def remove_folder(folder_id: int, db: Session = Depends(get_db)):
    """Remove a folder from watching"""
    folder = db.query(Folder).filter_by(id=folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    # Instead of deleting, mark as inactive
    folder.active = False
    db.commit()
    
    return {"message": "Folder removed from watching"}

@router.put("/folders/{folder_id}/activate", response_model=FolderResponse)
def activate_folder(folder_id: int, db: Session = Depends(get_db)):
    """Activate a folder for watching"""
    folder = db.query(Folder).filter_by(id=folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    folder.active = True
    db.commit()
    db.refresh(folder)
    
    # Note: The folder will be automatically added to the observer on next application restart
    # or when the folder watchers are restarted. For now, we'll just mark it as active.
    # The observer management is handled in the tasks.py module.
    
    return folder

@router.post("/folders/{folder_id}/scan", response_model=dict)
def scan_folder(folder_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Force a scan of a folder"""
    folder = db.query(Folder).filter_by(id=folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    # Process images in the background
    from ..config import Config
    ollama_server_val = Config.get('ollama', 'server', fallback="http://127.0.0.1:11434")
    ollama_model_val = Config.get('ollama', 'model', fallback="qwen2.5vl:latest")
    
    # Environment variables override config
    if 'OLLAMA_SERVER' in os.environ:
        ollama_server_val = os.environ["OLLAMA_SERVER"]
    if 'OLLAMA_MODEL' in os.environ:
        ollama_model_val = os.environ["OLLAMA_MODEL"]
    
    background_tasks.add_task(
        process_existing_images, 
        folder, 
        ollama_server_val,
        ollama_model_val
    )
    
    return {"status": "success", "message": "Folder scan started in the background"}

@router.get("/folders/browse", response_model=FileBrowserResponse)
def browse_filesystem(path: str = "/"):
    """Browse the file system to help users select folders"""
    try:
        # Security: Ensure the path is absolute and doesn't contain dangerous patterns
        if not os.path.isabs(path):
            path = os.path.abspath(path)
        
        # Prevent directory traversal attacks
        if ".." in path:
            raise HTTPException(status_code=400, detail="Invalid path: directory traversal not allowed")
        
        # Prevent access to system directories (platform-specific)
        system_dirs = ["/proc", "/sys", "/dev", "/var/run", "/tmp"]
        if any(path.startswith(system_dir) for system_dir in system_dirs):
            raise HTTPException(status_code=400, detail="Access to system directories not allowed")
        
        path_obj = Path(path)
        
        # Check if path exists and is readable
        if not path_obj.exists():
            raise HTTPException(status_code=404, detail="Path does not exist")
        
        if not path_obj.is_dir():
            raise HTTPException(status_code=400, detail="Path is not a directory")
        
        if not os.access(path, os.R_OK):
            raise HTTPException(status_code=403, detail="Directory is not readable")
        
        # Get parent path
        parent_path = str(path_obj.parent) if path_obj.parent != path_obj else None
        
        # List directory contents
        items = []
        try:
            for item in path_obj.iterdir():
                try:
                    # Skip hidden files and system files
                    if item.name.startswith('.'):
                        continue
                    
                    # Check if item is readable
                    is_readable = os.access(item, os.R_OK)
                    
                    # Get file info
                    stat = item.stat()
                    is_dir = item.is_dir()
                    
                    browser_item = FileBrowserItem(
                        name=item.name,
                        path=str(item),
                        is_dir=is_dir,
                        is_readable=is_readable,
                        size=stat.st_size if not is_dir else None,
                        modified=datetime.fromtimestamp(stat.st_mtime)
                    )
                    
                    items.append(browser_item)
                    
                except (PermissionError, OSError):
                    # Skip items we can't access
                    continue
            
            # Sort: directories first, then files, both alphabetically
            items.sort(key=lambda x: (not x.is_dir, x.name.lower()))
            
        except PermissionError:
            raise HTTPException(status_code=403, detail="Cannot read directory contents")
        
        return FileBrowserResponse(
            current_path=str(path_obj),
            parent_path=parent_path,
            items=items
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error browsing filesystem: {str(e)}")
