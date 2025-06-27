from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from PIL import Image as PILImage
import io
import os
import time
import hashlib
from pathlib import Path
from typing import Optional
import logging

from ..models import Image
from ..models import get_db
from ..config import Config

router = APIRouter()
logger = logging.getLogger(__name__)

# Thumbnail cache directory
THUMBNAIL_DIR = Path("data/thumbnails")
if not THUMBNAIL_DIR.exists():
    THUMBNAIL_DIR.mkdir(parents=True)

# Cache for tracking recently accessed thumbnails
_thumbnail_cache = {}
_cache_max_size = 1000  # Maximum number of entries in memory cache

def get_thumbnail_path(image_id: int, size: int) -> Path:
    """Generate thumbnail file path with size in filename"""
    return THUMBNAIL_DIR / f"{image_id}_{size}.jpg"

def get_cache_key(image_id: int, size: int) -> str:
    """Generate cache key for thumbnail"""
    return f"{image_id}_{size}"

def manage_cache_size():
    """Remove oldest entries if cache is too large"""
    if len(_thumbnail_cache) > _cache_max_size:
        # Remove oldest entries (simple LRU)
        items_to_remove = len(_thumbnail_cache) - _cache_max_size + 100
        oldest_keys = sorted(_thumbnail_cache.keys(), key=lambda k: _thumbnail_cache[k]['timestamp'])[:items_to_remove]
        for key in oldest_keys:
            del _thumbnail_cache[key]

def cleanup_orphaned_thumbnails(db: Session):
    """Remove thumbnail files for images that no longer exist in database"""
    try:
        # Get all image IDs from database
        db_image_ids = {img.id for img in db.query(Image.id).all()}
        
        # Check thumbnail directory
        for thumbnail_file in THUMBNAIL_DIR.glob("*.jpg"):
            try:
                # Extract image_id from filename (format: image_id_size.jpg)
                parts = thumbnail_file.stem.split('_')
                if len(parts) >= 2:
                    image_id = int(parts[0])
                    if image_id not in db_image_ids:
                        thumbnail_file.unlink()
                        logger.info(f"Removed orphaned thumbnail: {thumbnail_file}")
            except (ValueError, IndexError):
                # Invalid filename format, remove it
                thumbnail_file.unlink()
                logger.info(f"Removed invalid thumbnail filename: {thumbnail_file}")
    except Exception as e:
        logger.error(f"Error cleaning up orphaned thumbnails: {e}")

def get_cache_size_mb() -> float:
    """Get current cache size in MB"""
    total_size = 0
    try:
        for file_path in THUMBNAIL_DIR.rglob("*.jpg"):
            total_size += file_path.stat().st_size
        return total_size / (1024 * 1024)
    except Exception:
        return 0.0

def enforce_cache_size_limit():
    """Enforce maximum cache size by removing oldest files"""
    try:
        max_cache_size_mb = Config.getfloat('storage', 'max_cache_size_mb', fallback=1000.0)
        current_size_mb = get_cache_size_mb()
        
        if current_size_mb > max_cache_size_mb:
            logger.info(f"Cache size ({current_size_mb:.1f}MB) exceeds limit ({max_cache_size_mb}MB), cleaning up...")
            
            # Get all thumbnail files with their modification times
            thumbnail_files = []
            for file_path in THUMBNAIL_DIR.glob("*.jpg"):
                try:
                    mtime = file_path.stat().st_mtime
                    thumbnail_files.append((file_path, mtime))
                except OSError:
                    continue
            
            # Sort by modification time (oldest first)
            thumbnail_files.sort(key=lambda x: x[1])
            
            # Remove oldest files until under limit
            for file_path, _ in thumbnail_files:
                try:
                    file_path.unlink()
                    current_size_mb = get_cache_size_mb()
                    if current_size_mb <= max_cache_size_mb * 0.8:  # Leave 20% buffer
                        break
                except OSError:
                    continue
            
            logger.info(f"Cache cleanup complete. New size: {get_cache_size_mb():.1f}MB")
    except Exception as e:
        logger.error(f"Error enforcing cache size limit: {e}")

@router.get("/thumbnails/{image_id}")
def get_thumbnail(image_id: int, size: int = 200, db: Session = Depends(get_db)):
    """
    Generate and serve a thumbnail for an image with enhanced caching
    """
    # Validate size parameter
    if size < 50 or size > 800:
        raise HTTPException(status_code=400, detail="Size must be between 50 and 800")
    
    # Check memory cache first
    cache_key = get_cache_key(image_id, size)
    if cache_key in _thumbnail_cache:
        cache_entry = _thumbnail_cache[cache_key]
        # Update timestamp for LRU
        cache_entry['timestamp'] = time.time()
        logger.debug(f"Thumbnail served from memory cache: {cache_key}")
        return Response(content=cache_entry['data'], media_type="image/jpeg")
    
    # Check if thumbnail already exists in file cache
    thumbnail_path = get_thumbnail_path(image_id, size)
    
    if thumbnail_path.exists():
        try:
            # Read from file cache
            with open(thumbnail_path, "rb") as f:
                thumbnail_data = f.read()
            
            # Add to memory cache
            manage_cache_size()
            _thumbnail_cache[cache_key] = {
                'data': thumbnail_data,
                'timestamp': time.time()
            }
            
            logger.debug(f"Thumbnail served from file cache: {cache_key}")
            return Response(content=thumbnail_data, media_type="image/jpeg")
        except Exception as e:
            logger.error(f"Error reading cached thumbnail {thumbnail_path}: {e}")
            # Continue to regenerate
    
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
                # Create white background
                background = PILImage.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[-1])
                else:  # LA mode
                    background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode == 'P':
                # Convert palette mode to RGB
                img = img.convert('RGB')
            elif img.mode not in ('RGB', 'L'):
                # Convert any other mode to RGB
                img = img.convert('RGB')
                
            # Calculate new dimensions while preserving aspect ratio
            width, height = img.size
            if width > height:
                new_width = size
                new_height = int(height * (size / width))
            else:
                new_height = size
                new_width = int(width * (size / height))
                
            # Create thumbnail with high-quality resampling
            img.thumbnail((new_width, new_height), PILImage.Resampling.LANCZOS)
            
            # Get quality setting from config
            quality = Config.getint('storage', 'thumbnail_quality', fallback=85)
            
            # Save to file cache
            img.save(thumbnail_path, "JPEG", quality=quality, optimize=True)
            
            # Prepare response data
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=quality, optimize=True)
            thumbnail_data = img_byte_arr.getvalue()
            
            # Add to memory cache
            manage_cache_size()
            _thumbnail_cache[cache_key] = {
                'data': thumbnail_data,
                'timestamp': time.time()
            }
            
            # Enforce cache size limit periodically
            if len(_thumbnail_cache) % 50 == 0:  # Check every 50 new thumbnails
                enforce_cache_size_limit()
            
            logger.debug(f"Thumbnail generated and cached: {cache_key}")
            return Response(content=thumbnail_data, media_type="image/jpeg")
            
    except Exception as e:
        logger.error(f"Error generating thumbnail for image {image_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating thumbnail: {str(e)}")

@router.delete("/thumbnails/{image_id}")
def delete_thumbnail(image_id: int, size: Optional[int] = None):
    """
    Delete thumbnail(s) for an image
    """
    try:
        if size:
            # Delete specific size
            thumbnail_path = get_thumbnail_path(image_id, size)
            cache_key = get_cache_key(image_id, size)
            
            if thumbnail_path.exists():
                thumbnail_path.unlink()
            if cache_key in _thumbnail_cache:
                del _thumbnail_cache[cache_key]
        else:
            # Delete all sizes for this image
            for thumbnail_file in THUMBNAIL_DIR.glob(f"{image_id}_*.jpg"):
                thumbnail_file.unlink()
            
            # Remove from memory cache
            keys_to_remove = [k for k in _thumbnail_cache.keys() if k.startswith(f"{image_id}_")]
            for key in keys_to_remove:
                del _thumbnail_cache[key]
        
        return {"message": "Thumbnail(s) deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting thumbnail for image {image_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting thumbnail: {str(e)}")

@router.post("/thumbnails/cleanup")
def cleanup_thumbnails(db: Session = Depends(get_db)):
    """
    Clean up orphaned thumbnails and enforce cache limits
    """
    try:
        cleanup_orphaned_thumbnails(db)
        enforce_cache_size_limit()
        
        cache_size_mb = get_cache_size_mb()
        return {
            "message": "Thumbnail cleanup completed",
            "cache_size_mb": cache_size_mb,
            "memory_cache_entries": len(_thumbnail_cache)
        }
    except Exception as e:
        logger.error(f"Error during thumbnail cleanup: {e}")
        raise HTTPException(status_code=500, detail=f"Error during cleanup: {str(e)}")
