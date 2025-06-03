from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from pathlib import Path
from .config import get_config

# Get database URL from config
config = get_config()
db_path = config.database.path if hasattr(config, 'database') and hasattr(config.database, 'path') else 'sqlite:///data/image_tagger.db'

# If the path is a SQLite URL, extract the file path and ensure directory exists
if db_path.startswith("sqlite:///"):
    file_path = db_path.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    SQLALCHEMY_DATABASE_URL = db_path
else:
    # For other database types, use the path as is
    SQLALCHEMY_DATABASE_URL = db_path

# Create SQLAlchemy engine with appropriate connect args for SQLite
connect_args = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a base class for declarative models
Base = declarative_base()

# Dependency to get a database session
def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
