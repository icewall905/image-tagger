from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

import os
from pathlib import Path

from ..models import Folder
from ..tasks import process_existing_images, add_folder_to_observer
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
    added_at: str
    
    class Config:
        orm_mode = True

# Database dependency
def get_db(db_session):
    try:
        yield db_session
    finally:
        pass

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
    
    # Add the folder to the active observer
    if globals.observer and globals.observer.is_alive():
        add_folder_to_observer(
            globals.observer, 
            folder.path, 
            folder.recursive, 
            db, 
            os.environ.get("OLLAMA_SERVER", "http://127.0.0.1:11434"),
            os.environ.get("OLLAMA_MODEL", "llama3.2-vision")
        )
    
    # Process existing images in the background
    background_tasks.add_task(
        process_existing_images, 
        new_folder, 
        db, 
        os.environ.get("OLLAMA_SERVER", "http://127.0.0.1:11434"),
        os.environ.get("OLLAMA_MODEL", "llama3.2-vision")
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
    if globals.observer and globals.observer.is_alive():
        add_folder_to_observer(
            globals.observer, 
            folder.path, 
            folder.recursive, 
            db, 
            os.environ.get("OLLAMA_SERVER", "http://127.0.0.1:11434"),
            os.environ.get("OLLAMA_MODEL", "llama3.2-vision")
        )
    
    return folder

@router.post("/folders/{folder_id}/scan", response_model=dict)
def scan_folder(folder_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Force a scan of a folder"""
    folder = db.query(Folder).filter_by(id=folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    # Process images in the background
    background_tasks.add_task(
        process_existing_images, 
        folder, 
        db, 
        os.environ.get("OLLAMA_SERVER", "http://127.0.0.1:11434"),
        os.environ.get("OLLAMA_MODEL", "llama3.2-vision")
    )
    
    return {"message": "Folder scan started in the background"}
