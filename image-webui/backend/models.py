from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table, create_engine, Text, text
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
    description = Column(Text)
    processed_at = Column(DateTime, default=datetime.utcnow)

    # Processing tracking fields
    file_modified_at = Column(DateTime)
    file_size = Column(Integer)
    checksum = Column(String, nullable=True, index=True)
    processing_status = Column(String, default="pending")
    processing_error = Column(Text)
    last_processing_attempt = Column(DateTime)
    processing_attempts = Column(Integer, default=0)

    tags = relationship("Tag", secondary=image_tags, back_populates="images")

    @property
    def relative_path(self):
        return str(self.path)

    @property
    def thumbnail_path(self):
        return f"/thumbnails/{self.id}"

    @property
    def is_processed(self):
        return self.processing_status == "completed" and self.description is not None

    @property
    def file_size_mb(self):
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return None

class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    images = relationship("Image", secondary=image_tags, back_populates="tags")

# Database engine and session factory
engine = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def get_db_engine(db_path="sqlite:///image_tagger.db"):
    """Create a SQLAlchemy engine with SQLite-specific settings."""
    connect_args = {}
    if db_path.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(db_path, connect_args=connect_args)


def init_db(db_engine):
    """Initialize the database: create tables and configure session factory."""
    global engine
    engine = db_engine
    Base.metadata.create_all(bind=engine)
    SessionLocal.configure(bind=engine)


def get_db():
    """FastAPI dependency: yields a database session."""
    if not engine:
        raise RuntimeError("Database engine not initialized. Call init_db() first.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
