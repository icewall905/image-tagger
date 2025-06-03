from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from PIL import Image as PILImage
import io
import os
from pathlib import Path

from ..models import Image
from ..models import get_db # Added import for dependency

router = APIRouter()

# Thumbnail cache directory
THUMBNAIL_DIR = Path("data/thumbnails")
if not THUMBNAIL_DIR.exists():
    THUMBNAIL_DIR.mkdir(parents=True)

@router.get("/thumbnails/{image_id}")
def get_thumbnail(image_id: int, size: int = 200, db: Session = Depends(get_db)):
    """
    Generate and serve a thumbnail for an image
    """
    # Check if thumbnail already exists in cache
    thumbnail_path = THUMBNAIL_DIR / f"{image_id}_{size}.jpg"
    
    if thumbnail_path.exists():
        # Serve from cache
        with open(thumbnail_path, "rb") as f:
            return Response(content=f.read(), media_type="image/jpeg")
    
    # Get the image from the database
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Check if the image file exists
    if not os.path.exists(image.path):
        raise HTTPException(status_code=404, detail="Image file not found")
    
    try:
        # Open the image and create a thumbnail
        with PILImage.open(image.path) as img:
            # Convert RGBA to RGB if needed
            if img.mode in ('RGBA', 'LA'):
                img = img.convert('RGB')
                
            # Calculate new dimensions while preserving aspect ratio
            width, height = img.size
            if width > height:
                new_width = size
                new_height = int(height * (size / width))
            else:
                new_height = size
                new_width = int(width * (size / height))
                
            # Create thumbnail
            img.thumbnail((new_width, new_height))
            
            # Save to cache
            img.save(thumbnail_path, "JPEG")
            
            # Serve the thumbnail
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG')
            return Response(content=img_byte_arr.getvalue(), media_type="image/jpeg")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating thumbnail: {str(e)}")
