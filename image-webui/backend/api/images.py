from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import os
from pathlib import Path

from ..models import Image, Tag
from ..models import get_db

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
    description: Optional[str] = None
    processed_at: Optional[datetime] = None
    processing_status: Optional[str] = None
    tags: List[TagResponse]

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }

class ImageListResponse(BaseModel):
    id: int
    path: str
    description: Optional[str] = None
    processed_at: Optional[datetime] = None
    processing_status: Optional[str] = None
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
    status: Optional[str] = Query(None, description="Filter by processing status: 'completed', 'pending', 'failed', 'skipped', 'processing', or 'all' for all images"),
    db: Session = Depends(get_db)
):
    """
    List images with optional filtering by search query, tag, or processing status.
    By default shows ALL images regardless of processing status.
    Use ?status=completed to see only AI-processed images.
    """
    offset = (page - 1) * limit

    query = db.query(Image)

    # Filter by processing status if specified
    if status and status != "all":
        query = query.filter(Image.processing_status == status)

    # Apply search filters if provided
    if q:
        query = query.filter(Image.description.ilike(f"%{q}%"))

    if tag:
        query = query.join(Image.tags).filter(Tag.name == tag)

    # Apply pagination with deterministic ordering
    images = query.order_by(Image.id.desc()).offset(offset).limit(limit).all()

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

@router.get("/images/{image_id}/file")
def serve_image_file(image_id: int, download: bool = Query(False), db: Session = Depends(get_db)):
    """
    Serve the actual image file by database ID.
    Set ?download=true to force download.
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path = Path(image.path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    media_type = None
    suffix = file_path.suffix.lower()
    mime_map = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
        '.gif': 'image/gif', '.bmp': 'image/bmp', '.webp': 'image/webp',
        '.avif': 'image/avif', '.tif': 'image/tiff', '.tiff': 'image/tiff',
        '.heic': 'image/heic', '.heif': 'image/heif',
    }
    media_type = mime_map.get(suffix)

    if download:
        return FileResponse(
            file_path,
            media_type=media_type,
            filename=file_path.name,
            headers={"Content-Disposition": f'attachment; filename="{file_path.name}"'}
        )
    return FileResponse(file_path, media_type=media_type)

@router.get("/tags", response_model=List[TagResponse])
def list_tags(db: Session = Depends(get_db)):
    """
    List all available tags
    """
    tags = db.query(Tag).all()
    return tags
