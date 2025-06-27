from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import os
from pathlib import Path

from ..models import Image, Tag
from ..models import get_db # Added import for dependency

router = APIRouter()

# Pydantic models for request/response
class TagResponse(BaseModel):
    id: int
    name: str
    
    class Config:
        from_attributes = True

class ImageResponse(BaseModel):
    id: int
    path: str
    description: str
    processed_at: datetime
    tags: List[TagResponse]
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }
        
class ImageListResponse(BaseModel):
    id: int
    path: str
    thumbnail_path: str
    tags: List[TagResponse]
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }

@router.get("/images", response_model=List[ImageListResponse])
def list_images(
    q: Optional[str] = None,
    tag: Optional[str] = None, 
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    List images with optional filtering by search query or tag
    """
    # Calculate offset based on page and limit
    offset = (page - 1) * limit
    
    # Base query
    query = db.query(Image)
    
    # Apply filters if provided
    if q:
        query = query.filter(Image.description.ilike(f"%{q}%"))
        
    if tag:
        query = query.join(Image.tags).filter(Tag.name == tag)
    
    # Apply pagination
    images = query.offset(offset).limit(limit).all()
    
    return images

@router.get("/images/{image_id}", response_model=ImageResponse)
def get_image(image_id: int, db: Session = Depends(get_db)):
    """
    Get a single image by ID
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    return image

@router.get("/tags", response_model=List[TagResponse])
def list_tags(db: Session = Depends(get_db)):
    """
    List all available tags
    """
    tags = db.query(Tag).all()
    return tags
