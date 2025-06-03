# Test imports to verify environment setup
try:
    print("Trying to import fastapi...")
    import fastapi
    print("Trying to import uvicorn...")
    import uvicorn
    print("Trying to import sqlalchemy...")
    import sqlalchemy
    print("Trying to import alembic...")
    import alembic
    print("Trying to import requests...")
    import requests
    print("Trying to import psutil...")
    import psutil
    print("Trying to import pydantic...")
    import pydantic
    print("Trying to import watchdog...")
    import watchdog
    print("Trying to import PIL...")
    import PIL
    print("All imports successful!")
except ImportError as e:
    print(f"Import error: {e}")
