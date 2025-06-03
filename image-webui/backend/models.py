from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

Base = declarative_base()

# Many-to-many relationship table between images and tags
image_tags = Table(
    "image_tags", Base.metadata,
    Column("image_id", ForeignKey("images.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True)
)

class Folder(Base):
    __tablename__ = "folders"
    id = Column(Integer, primary_key=True)
    path = Column(String, unique=True, nullable=False)
    recursive = Column(Boolean, default=True)
    active = Column(Boolean, default=True)
    added_at = Column(DateTime, default=datetime.utcnow)

class Image(Base):
    __tablename__ = "images"
    id = Column(Integer, primary_key=True)
    path = Column(String, unique=True, nullable=False)
    description = Column(String)
    processed_at = Column(DateTime, default=datetime.utcnow)
    tags = relationship("Tag", secondary=image_tags, back_populates="images")
    
    # Add property to get relative path for web display
    @property
    def relative_path(self):
        return str(self.path)
    
    # Add property to get thumbnail path
    @property
    def thumbnail_path(self):
        return f"/thumbnails/{self.id}"

class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    images = relationship("Image", secondary=image_tags, back_populates="tags")

# Database engine and session factory will be initialized in app.py
engine = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False)

# Create database engine
def get_db_engine(db_path="sqlite:///image_tagger.db"):
    return create_engine(db_path)

def init_db(db_engine):
    global engine
    engine = db_engine
    Base.metadata.create_all(bind=engine)
    SessionLocal.configure(bind=engine)

# Dependency to get DB session
def get_db():
    if not engine:
        raise RuntimeError("Database engine not initialized.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
