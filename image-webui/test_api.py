#!/usr/bin/env python3
"""
Test script to check what the images API is returning
"""

import requests
import json

def test_images_api():
    """Test the images API endpoint"""
    try:
        # Test the images endpoint
        response = requests.get('http://localhost:8491/api/images?page=1&limit=20')
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Number of images returned: {len(data)}")
            if data:
                print(f"First image: {json.dumps(data[0], indent=2)}")
            else:
                print("No images returned")
        else:
            print(f"Error response: {response.text}")
            
    except Exception as e:
        print(f"Error: {e}")

def test_database_direct():
    """Test database connection directly"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / "backend"))
    
    from backend.database import SessionLocal
    from backend.models import Image
    
    db = SessionLocal()
    try:
        images = db.query(Image).all()
        print(f"Direct database query: {len(images)} images")
        if images:
            print(f"First image ID: {images[0].id}, Path: {images[0].path}")
    except Exception as e:
        print(f"Database error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    print("Testing Images API...")
    test_images_api()
    print("\nTesting Database Direct...")
    test_database_direct() 