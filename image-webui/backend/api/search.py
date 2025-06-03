from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy import func

from ..models import Image, Tag, image_tags
from ..image_tagger import core as tagger

router = APIRouter()

# Pydantic models
class TagCount(BaseModel):
    name: str
    count: int
    
    class Config:
        orm_mode = True

class SearchResult(BaseModel):
    id: int
    path: str
    description: str
    tags: List[str]
    
    class Config:
        orm_mode = True

# Database dependency
def get_db(db_session):
    try:
        yield db_session
    finally:
        pass

@router.get("/search", response_model=List[SearchResult])
def search_images(
    q: str = Query(..., min_length=1),
    tags: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Search for images by text query and/or tags
    """
    # Start with a base query
    query = db.query(Image)
    
    # Apply text search if provided
    if q:
        query = query.filter(Image.description.ilike(f"%{q}%"))
    
    # Filter by tags if provided
    if tags and len(tags) > 0:
        for tag in tags:
            query = query.join(Image.tags).filter(Tag.name == tag)
    
    # Execute the query
    results = query.all()
    
    # Format the results
    search_results = []
    for img in results:
        search_results.append({
            "id": img.id,
            "path": img.path,
            "description": img.description,
            "tags": [tag.name for tag in img.tags]
        })
    
    return search_results

@router.get("/tagcloud", response_model=List[TagCount])
def get_tag_cloud(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    """
    Get a list of tags with their usage counts for creating a tag cloud
    """
    # Query for tags and their counts
    tag_counts = db.query(
        Tag.name, 
        func.count(image_tags.c.image_id).label("count")
    ).join(
        image_tags,
        Tag.id == image_tags.c.tag_id
    ).group_by(
        Tag.name
    ).order_by(
        func.count(image_tags.c.image_id).desc()
    ).limit(limit).all()
    
    # Format the results
    results = [{"name": name, "count": count} for name, count in tag_counts]
    
    return results
