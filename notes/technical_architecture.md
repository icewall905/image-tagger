---
note_type: technical_architecture
date: 2025-06-10
summary: Detailed technical architecture, API documentation, and implementation details
related_files:
  - image-webui/backend/app.py
  - image-webui/backend/models.py
  - image-webui/backend/api/
  - image-webui/backend/image_tagger/core.py
---

# Image Tagger Technical Architecture

## 🏗️ System Architecture

### Application Layers

#### 1. Presentation Layer (Frontend)
```
frontend/
├── templates/           # Jinja2 HTML templates
│   ├── layout.html     # Base template with Bootstrap 5
│   ├── index.html      # Dashboard with statistics
│   ├── folders.html    # Folder management interface
│   ├── gallery.html    # Image browsing with thumbnails
│   ├── search.html     # Search interface
│   └── settings.html   # Configuration management
└── static/
    ├── css/           # Custom stylesheets
    └── js/            # JavaScript modules
        └── main.js    # Core UI functionality
```

**Technology Stack**:
- **Templates**: Jinja2 with Bootstrap 5 components
- **JavaScript**: jQuery + vanilla JS (no heavy frameworks)
- **CSS**: Bootstrap 5 + custom overrides
- **Icons**: Bootstrap Icons
- **Responsive**: Mobile-first design

#### 2. API Layer (Backend Routes)
```
backend/api/
├── folders.py          # Folder CRUD operations
├── images.py           # Image browsing and metadata
├── search.py           # Search functionality  
├── settings.py         # Configuration and system status
├── tags.py             # Tag management
└── thumbnails.py       # Thumbnail serving
```

**Key API Endpoints**:
```python
# Folder Management
GET    /api/folders                 # List all folders
POST   /api/folders                 # Add new folder
DELETE /api/folders/{id}            # Remove folder
PUT    /api/folders/{id}/activate   # Activate/deactivate folder
POST   /api/folders/{id}/scan       # Trigger manual scan

# Image Operations  
GET    /api/images                  # List images (paginated)
GET    /api/images/{id}             # Get image details
GET    /api/images/search           # Search images
GET    /api/images/stats            # Collection statistics

# Search & Discovery
GET    /api/search                  # Full-text search
GET    /api/tags                    # List all tags
GET    /api/tags/cloud              # Tag cloud data
GET    /api/tags/{id}/images        # Images with specific tag

# System Management
GET    /api/settings/config         # Get configuration
POST   /api/settings/config         # Save configuration
GET    /api/settings/status         # System health
GET    /api/settings/processing-status # Background task progress
POST   /api/settings/test-ollama    # Test AI connection
POST   /api/settings/scan-all-folders    # Batch scan operation
POST   /api/settings/process-all-images  # Batch AI processing
```

#### 3. Business Logic Layer
```
backend/
├── app.py              # FastAPI application setup
├── models.py           # SQLAlchemy ORM models
├── schemas.py          # Pydantic request/response models
├── tasks.py            # Background task processing
├── config.py           # Configuration management
├── globals.py          # Global state management
└── utils.py            # Utility functions
```

#### 4. AI Processing Layer
```
backend/image_tagger/
├── core.py             # Main AI processing functions
└── __init__.py         # Module initialization
```

**Core AI Functions**:
```python
# Primary processing functions
process_image(image_path, server, model, ...)       # Single image processing
process_directory(input_path, server, model, ...)   # Batch directory processing

# Utility functions
encode_image_to_base64(image_path)                   # Image encoding for API
extract_tags_from_description(description)          # Tag extraction from text
get_file_checksum(file_path)                        # Duplicate detection
load_config()                                       # Configuration loading
```

#### 5. Data Layer
```
data/
├── image_tagger.db             # Main SQLite database
├── image-tagger-tracking.db    # Processing tracking database
└── thumbnails/                 # Generated thumbnail cache
```

### Database Schema

#### Core Tables
```sql
-- Folder configuration
CREATE TABLE folders (
    id INTEGER PRIMARY KEY,
    path VARCHAR NOT NULL UNIQUE,
    recursive BOOLEAN DEFAULT true,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_scan TIMESTAMP
);

-- Image metadata
CREATE TABLE images (
    id INTEGER PRIMARY KEY,
    path VARCHAR NOT NULL UNIQUE,
    description TEXT,                    -- AI-generated description
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_size INTEGER,
    width INTEGER,
    height INTEGER,
    format VARCHAR(10),
    checksum VARCHAR(64)                 -- For duplicate detection
);

-- Tag vocabulary
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usage_count INTEGER DEFAULT 0       -- For tag cloud weighting
);

-- Many-to-many relationship
CREATE TABLE image_tags (
    image_id INTEGER REFERENCES images(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (image_id, tag_id)
);
```

## 🔧 Core Processing Pipeline

### 1. Image Discovery
```python
# Folder monitoring (real-time)
class FolderWatcher:
    def __init__(self, folder_path, recursive=True):
        self.observer = Observer()
        self.handler = ImageFileHandler()
        
    def on_created(self, event):
        if self.is_image_file(event.src_path):
            self.queue_for_processing(event.src_path)

# Manual scanning (on-demand)
def scan_folder(folder_path, recursive=True):
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif', '.tif', '.tiff')
    if recursive:
        files = folder_path.rglob('*')
    else:
        files = folder_path.glob('*')
    return [f for f in files if f.suffix.lower() in image_extensions]
```

### 2. AI Processing Workflow
```python
def process_image(image_path, server, model, **kwargs):
    # 1. Duplicate check (via file tracking)
    if not override and is_file_processed(image_path):
        return "skipped"
    
    # 2. Image encoding
    base64_image = encode_image_to_base64(image_path)
    
    # 3. AI API call with retry logic
    for attempt in range(max_retries):
        payload = {
            "model": model,
            "prompt": "Describe this image in detail...",
            "images": [base64_image],
            "stream": False,
            "options": {"temperature": 0.1}
        }
        
        response = requests.post(f"{server}/api/generate", 
                               json=payload, timeout=300)
        
        if response.status_code == 200:
            description = response.json()['response']
            tags = extract_tags_from_description(description)
            
            # 4. Metadata embedding
            update_image_metadata(image_path, description, tags)
            
            # 5. Database storage
            store_in_database(image_path, description, tags)
            
            # 6. Mark as processed
            mark_file_as_processed(image_path)
            return True
            
        # Retry logic with exponential backoff
        time.sleep(min(30, 5 * (2 ** attempt)))
    
    return False
```

### 3. Metadata Storage Strategy
```python
# EXIF metadata (JPEG/TIFF)
def update_exif_metadata(image_path, description, tags):
    exiftool_cmd = [
        'exiftool',
        '-overwrite_original',
        f'-ImageDescription={description}',
        f'-UserComment={description}', 
        f'-XPKeywords={";".join(tags)}',
        str(image_path)
    ]
    subprocess.run(exiftool_cmd, check=True)

# PNG text chunks
def update_png_metadata(image_path, description, tags):
    img = Image.open(image_path)
    metadata = PngInfo()
    metadata.add_text("Description", description)
    metadata.add_text("Keywords", ";".join(tags))
    img.save(image_path, pnginfo=metadata)
```

## 🌐 Web Framework Architecture

### FastAPI Application Structure
```python
# app.py - Main application setup
app = FastAPI(
    title="Image Tagger WebUI",
    description="AI-powered image tagging and search",
    version="1.0.0"
)

# Middleware stack
app.add_middleware(CORSMiddleware, ...)
app.add_middleware(StaticFiles, ...)

# Route inclusion
app.include_router(folders.router, prefix="/api", tags=["folders"])
app.include_router(images.router, prefix="/api", tags=["images"])
app.include_router(search.router, prefix="/api", tags=["search"])
app.include_router(settings.router, prefix="/api", tags=["settings"])

# Static file serving
app.mount("/static", StaticFiles(directory="frontend/static"))
app.mount("/thumbnails", StaticFiles(directory="data/thumbnails"))

# Template responses
templates = Jinja2Templates(directory="frontend/templates")

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
```

### Background Task Management
```python
# tasks.py - Asynchronous processing
import globals  # Shared application state

async def process_existing_images(folder: Folder, db_session: Session, 
                                server: str, model: str):
    # Update global progress state
    globals.app_state.current_task = f"Processing folder: {folder.path}"
    globals.app_state.task_total = total_images
    
    for idx, image_path in enumerate(image_files):
        # Update progress
        globals.app_state.task_progress = (idx / total_images) * 100
        globals.app_state.completed_tasks = idx
        
        # Process individual image
        result = tagger.process_image(image_path, server, model)
        
        # Store results in database
        if result:
            store_image_results(db_session, image_path, result)
```

### Real-time Progress Tracking
```javascript
// frontend/static/js/main.js - Universal Status Indicator
class UniversalProgressIndicator {
    constructor() {
        this.indicator = document.getElementById('universal-progress-indicator');
        this.startPolling();
    }
    
    async pollProgress() {
        try {
            const response = await fetch('/api/settings/processing-status');
            const status = await response.json();
            
            if (status.is_processing) {
                this.show();
                this.updateProgress(status.task_progress);
                this.updateText(status.current_task);
                this.updateCounts(status.completed_tasks, status.task_total);
            } else {
                this.hide();
            }
        } catch (error) {
            console.error('Progress polling error:', error);
        }
    }
    
    startPolling() {
        setInterval(() => this.pollProgress(), 2000);
    }
}
```

## 🔍 Search Implementation

### Database Search Strategy
```python
# Full-text search across descriptions
def search_images(query: str, tags: List[str] = None, limit: int = 50):
    search_query = db.query(Image)
    
    # Text search in descriptions
    if query:
        search_query = search_query.filter(
            Image.description.contains(query)
        )
    
    # Tag filtering
    if tags:
        search_query = search_query.join(Image.tags).filter(
            Tag.name.in_(tags)
        )
    
    return search_query.limit(limit).all()

# Tag cloud generation
def generate_tag_cloud():
    tag_counts = db.query(
        Tag.name, 
        func.count(image_tags.c.image_id).label('count')
    ).join(image_tags).group_by(Tag.name).all()
    
    return [{"name": name, "count": count} for name, count in tag_counts]
```

### Frontend Search Interface
```javascript
// search.html - Interactive search
function performSearch() {
    const query = document.getElementById('search-query').value;
    const selectedTags = getSelectedTags();
    
    fetch(`/api/search?q=${encodeURIComponent(query)}&tags=${selectedTags.join(',')}`)
        .then(response => response.json())
        .then(results => displayResults(results));
}

function displayResults(results) {
    const gallery = document.getElementById('search-results');
    gallery.innerHTML = results.map(image => `
        <div class="col-md-3 mb-3">
            <div class="card">
                <img src="/thumbnails/${image.id}.jpg" 
                     class="card-img-top" 
                     alt="${image.description}">
                <div class="card-body">
                    <p class="card-text">${image.description}</p>
                    <div class="tags">
                        ${image.tags.map(tag => 
                            `<span class="badge bg-secondary">${tag.name}</span>`
                        ).join(' ')}
                    </div>
                </div>
            </div>
        </div>
    `).join('');
}
```

## 🔧 Configuration Management

### Hierarchical Configuration
```python
# config.py - Configuration precedence
class Config:
    def __init__(self):
        self.config = configparser.ConfigParser()
        
        # 1. Load from file
        self.config.read('config.ini')
        
        # 2. Override with environment variables
        self.apply_env_overrides()
    
    def apply_env_overrides(self):
        env_mappings = {
            'DB_PATH': ('database', 'path'),
            'OLLAMA_SERVER': ('ollama', 'server'),
            'OLLAMA_MODEL': ('ollama', 'model'),
            'HOST': ('general', 'host'),
            'PORT': ('general', 'port'),
        }
        
        for env_var, (section, key) in env_mappings.items():
            if env_var in os.environ:
                if not self.config.has_section(section):
                    self.config.add_section(section)
                self.config.set(section, key, os.environ[env_var])
```

### Runtime Configuration Updates
```python
# API endpoint for configuration updates
@router.post("/settings/config")
def save_config(config_data: ConfigUpdateRequest):
    for section, section_data in config_data.config.items():
        if not Config.has_section(section):
            Config.add_section(section)
            
        for key, value in section_data.items():
            Config.set(section, key, str(value))
    
    Config.save()  # Persist to file
    return {"message": "Configuration saved successfully"}
```

## 🚀 Performance Optimizations

### Database Optimizations
```sql
-- Indexes for common queries
CREATE INDEX idx_images_description ON images(description);
CREATE INDEX idx_images_path ON images(path);
CREATE INDEX idx_tags_name ON tags(name);
CREATE INDEX idx_image_tags_image_id ON image_tags(image_id);
CREATE INDEX idx_image_tags_tag_id ON image_tags(tag_id);
```

### Caching Strategy
```python
# Thumbnail caching
def get_or_create_thumbnail(image_path: Path, size: int = 300) -> Path:
    thumb_path = THUMBNAIL_DIR / f"{hash(str(image_path))}_{size}.jpg"
    
    if not thumb_path.exists():
        with Image.open(image_path) as img:
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            img.convert('RGB').save(thumb_path, 'JPEG', quality=85)
    
    return thumb_path

# Database connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=StaticPool,
    pool_pre_ping=True,
    pool_recycle=300
)
```

### Async Processing
```python
# Background task queue
import asyncio
from concurrent.futures import ThreadPoolExecutor

class BackgroundProcessor:
    def __init__(self, max_workers=4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.queue = asyncio.Queue()
    
    async def add_task(self, func, *args, **kwargs):
        await self.queue.put((func, args, kwargs))
    
    async def process_queue(self):
        while True:
            func, args, kwargs = await self.queue.get()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, func, *args, **kwargs)
```

This technical documentation provides the foundation for understanding, maintaining, and extending the Image Tagger system architecture.
