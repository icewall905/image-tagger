#!/usr/bin/env python3
"""
Script to generate thumbnails for all existing images in the database
"""

import sys
import os
from pathlib import Path

# Add the backend directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from backend.database import SessionLocal
from backend.models import Image
from backend.api.thumbnails import get_thumbnail_path
from PIL import Image as PILImage
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_thumbnails_for_all_images():
    """Generate thumbnails for all images in the database"""
    db = SessionLocal()
    
    try:
        # Get all images from database
        images = db.query(Image).all()
        logger.info(f"Found {len(images)} images in database")
        
        generated_count = 0
        error_count = 0
        
        for image in images:
            try:
                # Check if image file exists
                if not os.path.exists(image.path):
                    logger.warning(f"Image file not found: {image.path}")
                    continue
                
                # Check if thumbnail already exists
                thumbnail_path = get_thumbnail_path(image.id, 200)
                if thumbnail_path.exists():
                    logger.debug(f"Thumbnail already exists for image {image.id}")
                    continue
                
                # Generate thumbnail
                with PILImage.open(image.path) as img:
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
                    generated_count += 1
                    logger.info(f"Generated thumbnail for image {image.id}: {os.path.basename(image.path)}")
                    
            except Exception as e:
                logger.error(f"Error generating thumbnail for image {image.id}: {e}")
                error_count += 1
        
        logger.info(f"Thumbnail generation complete: {generated_count} generated, {error_count} errors")
        
    except Exception as e:
        logger.error(f"Error in thumbnail generation: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    generate_thumbnails_for_all_images() 