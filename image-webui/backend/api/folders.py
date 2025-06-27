from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
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
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }

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
    
    # Add the folder back to the observer
    from ..config import Config
    ollama_server_val = Config.get('ollama', 'server', fallback="http://127.0.0.1:11434")
    ollama_model_val = Config.get('ollama', 'model', fallback="qwen2.5vl:latest")
    
    # Environment variables override config
    if 'OLLAMA_SERVER' in os.environ:
        ollama_server_val = os.environ["OLLAMA_SERVER"]
    if 'OLLAMA_MODEL' in os.environ:
        ollama_model_val = os.environ["OLLAMA_MODEL"]
    if globals.observer and globals.observer.is_alive():
        add_folder_to_observer(
            globals.observer, 
            folder.path, 
            folder.recursive, 
            db, # Passing request-scoped session
            ollama_server_val,
            ollama_model_val
        )
    
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
