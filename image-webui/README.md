# 🏷️ Image Tagger WebUI - Complete Documentation

A sophisticated web interface for automatically tagging images using AI-powered vision models through Ollama. This application provides intelligent image management with automated tagging, advanced search capabilities, and a modern responsive interface.

## ✨ Core Features

### 🤖 AI-Powered Image Processing
- **Automatic Tagging**: Uses Ollama vision models (qwen2.5vl:latest) for intelligent image analysis
- **Smart Descriptions**: Generates detailed, contextual descriptions for each image
- **Tag Extraction**: Automatically extracts relevant tags from image content
- **Batch Processing**: Efficiently handles large image collections

### 📁 Intelligent Folder Management
- **Folder Watching**: Real-time monitoring of designated folders for new images
- **Recursive Scanning**: Support for nested folder structures
- **Dynamic Management**: Add, remove, or re-activate watched folders on-the-fly
- **Background Processing**: Non-blocking image processing with progress tracking

### 🔍 Advanced Search & Discovery
- **Full-Text Search**: Search through image descriptions and metadata
- **Tag-Based Filtering**: Filter images by specific tags or combinations
- **Visual Gallery**: Thumbnail-based browsing with lightbox support
- **Tag Cloud**: Visual representation of popular tags in your collection

### 🎨 Modern User Interface
- **Responsive Design**: Works seamlessly on desktop, tablet, and mobile devices
- **Bootstrap 5**: Modern, accessible UI components
- **Real-Time Progress**: Universal progress indicator for long-running operations
- **Dark Theme Support**: Eye-friendly interface options
- **Intuitive Navigation**: Easy-to-use page structure and controlsebUI

A web-based interface for the Image Tagger application, allowing you to organize, tag, and search images with AI-generated descriptions.

## Features

- **Folder Watching**: Register folders to automatically tag new images
- **Image Gallery**: Browse all tagged images with their descriptions and tags
- **Search Capabilities**: Find images by description text or tags
- **Tag Cloud**: Visualize popular tags in your image collection
- **Bootstrap UI**: Modern, responsive interface
- **Background Processing**: Images are processed asynchronously
- **REST API**: Documented endpoints for programmatic access
- **Persistent Storage**: Database and thumbnails are stored persistently
- **Dynamic Folder Management**: Add, remove, or re-activate watched folders
- **Database Migrations**: Automatic schema management with Alembic

## 🏗️ Architecture Overview

### System Components

#### Frontend Layer
- **Templates**: Jinja2-based HTML templates with Bootstrap 5
- **Static Assets**: CSS, JavaScript, and image resources
- **Progressive Enhancement**: JavaScript-powered interactions with graceful degradation
- **Universal Progress Indicator**: Real-time operation tracking across all pages

#### Backend Layer
- **FastAPI Application**: High-performance Python web framework
- **SQLAlchemy ORM**: Robust database abstraction and migrations
- **Background Tasks**: Asynchronous image processing with Celery-like functionality
- **File System Monitoring**: Watchdog-based folder watching for real-time updates

#### AI Integration
- **Ollama Client**: Direct integration with local Ollama instance
- **Vision Models**: Support for qwen2.5vl and other vision-capable models
- **Flexible Configuration**: Configurable AI server endpoints and model selection
- **Error Recovery**: Robust handling of AI service interruptions

#### Data Layer
- **SQLite Database**: Lightweight, file-based database for metadata storage
- **Image Metadata**: EXIF data integration and custom tagging
- **Thumbnail Generation**: Automated thumbnail creation for fast gallery loading
- **File Tracking**: Prevents duplicate processing with checksum-based tracking

### Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Web Framework** | FastAPI | High-performance async web API |
| **Frontend** | Bootstrap 5 + jQuery | Responsive UI components |
| **Database** | SQLite + SQLAlchemy | Data persistence and ORM |
| **AI Processing** | Ollama + qwen2.5vl | Image analysis and tagging |
| **File Monitoring** | Watchdog | Real-time folder watching |
| **Image Processing** | Pillow + ExifTool | Thumbnail generation and metadata |
| **Template Engine** | Jinja2 | Server-side HTML rendering |
| **Configuration** | ConfigParser | INI-based configuration management |

## 📋 Requirements

### System Requirements
- **Operating System**: macOS, Linux, or Windows
- **Python**: 3.9 or higher
- **Memory**: 4GB RAM minimum (8GB recommended for large collections)
- **Storage**: 1GB free space for application + space for thumbnails
- **Network**: Internet access for initial AI model download

### Dependencies

#### Core Python Packages
```txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
sqlalchemy>=2.0.0
alembic>=1.12.0
watchdog>=3.0.0
pillow>=10.0.0
jinja2>=3.1.0
python-multipart>=0.0.6
requests>=2.31.0
```

#### External Tools
- **Ollama**: For AI-powered image analysis
  ```bash
  # Install Ollama (macOS)
  brew install ollama
  
  # Pull vision model
  ollama pull qwen2.5vl:latest
  ```

- **ExifTool**: For image metadata manipulation
  ```bash
  # macOS
  brew install exiftool
  
  # Ubuntu/Debian
  apt-get install libimage-exiftool-perl
  
  # Windows
  # Download from https://exiftool.org/
  ```

## 🚀 Installation & Setup

### Quick Start (Recommended)

1. **Clone the Repository**
   ```bash
   git clone <repository-url>
   cd image-tagger-1/image-webui
   ```

2. **Install Dependencies**
   ```bash
   # Install Python dependencies
   pip install -r requirements.txt
   
   # Install system dependencies (macOS)
   brew install ollama exiftool libheif
   
   # Start Ollama and pull vision model
   ollama serve &
   ollama pull qwen2.5vl:latest
   ```

3. **Initialize Database**
   ```bash
   # Setup database and run migrations
   ./setup_db.sh
   ```

4. **Start the Application**
   ```bash
   # Start the web server
   ./run.sh
   
   # Or manually:
   python -m backend.app
   ```

5. **Access Web Interface**
   - Open browser to: http://localhost:8491
   - Settings page: http://localhost:8491/settings

### Detailed Installation Steps

#### 1. Environment Setup
```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On macOS/Linux
# venv\Scripts\activate    # On Windows

# Upgrade pip
pip install --upgrade pip
```

#### 2. System Dependencies

**macOS (using Homebrew):**
```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install required packages
brew install ollama exiftool libheif python@3.11

# Start Ollama service
brew services start ollama
# Or run manually: ollama serve
```

**Ubuntu/Debian:**
```bash
# Install system packages
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv libimage-exiftool-perl libheif-dev

# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
sudo systemctl start ollama
```

**Windows:**
```powershell
# Install Python from python.org
# Install ExifTool from https://exiftool.org/
# Install Ollama from https://ollama.ai/

# Start Ollama
ollama serve
```

#### 3. AI Model Setup
```bash
# Pull the vision model (this may take several minutes)
ollama pull qwen2.5vl:latest

# Verify model is available
ollama list

# Test model (optional)
ollama run qwen2.5vl:latest "Describe this image" < test_image.jpg
```

#### 4. Application Configuration
```bash
# Copy default configuration
cp config.ini.example config.ini  # If example exists

# Edit configuration file
nano config.ini
```

**Key Configuration Settings:**
```ini
[general]
host = 0.0.0.0
port = 8000
debug = false
log_level = INFO

[database]
path = sqlite:///data/image_tagger.db

[ollama]
server = http://127.0.0.1:11434
model = qwen2.5vl:latest

[storage]
thumbnail_dir = data/thumbnails
thumbnail_max_size = 300

[security]
enable_cors = true
cors_origins = *
```

#### 5. Database Initialization
```bash
# Create data directory
mkdir -p data

# Initialize database
python -c "from backend.models import init_db, get_db_engine; init_db(get_db_engine('sqlite:///data/image_tagger.db'))"

# Or use the setup script
./setup_db.sh
```

### Docker Installation (Alternative)

```bash
# Build and run with Docker Compose
docker-compose up -d

# Or build manually
docker build -t image-tagger-webui .
docker run -p 8000:8000 -v $(pwd)/data:/app/data image-tagger-webui
```

## ⚙️ Configuration

### Configuration File (`config.ini`)

The application uses an INI-based configuration system with the following sections:

#### General Settings
```ini
[general]
host = 0.0.0.0          # Server bind address
port = 8000             # Server port
debug = false           # Enable debug mode
log_level = INFO        # Logging level (DEBUG, INFO, WARNING, ERROR)
```

#### Database Configuration
```ini
[database]
path = sqlite:///data/image_tagger.db  # Database file path
# For PostgreSQL: postgresql://user:pass@host:port/dbname
```

#### AI/Ollama Settings
```ini
[ollama]
server = http://127.0.0.1:11434  # Ollama server URL
model = qwen2.5vl:latest         # Vision model to use
timeout = 300                    # Request timeout in seconds
max_retries = 3                  # Max retry attempts for failed requests
```

#### Storage Settings
```ini
[storage]
thumbnail_dir = data/thumbnails  # Thumbnail storage directory
thumbnail_max_size = 300         # Max thumbnail dimension in pixels
thumbnail_quality = 85           # JPEG quality for thumbnails (1-100)
```

#### Security Settings
```ini
[security]
enable_cors = true     # Enable CORS for API access
cors_origins = *       # Allowed CORS origins (comma-separated)
```

#### Processing Settings
```ini
[processing]
batch_size = 10              # Images to process in each batch
batch_delay = 2              # Delay between batches (seconds)
max_concurrent_folders = 3   # Max folders to process simultaneously
background_processing = true # Enable background processing
```

#### File Tracking
```ini
[core]
use_file_tracking = true                        # Enable duplicate detection
tracking_db_path = data/image-tagger-tracking.db  # Tracking database path
```

### Environment Variables

Configuration can also be set via environment variables (overrides config file):

```bash
# Server settings
export HOST=0.0.0.0
export PORT=8000
export DEBUG=false

# Database
export DB_PATH=sqlite:///data/image_tagger.db

# Ollama
export OLLAMA_SERVER=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen2.5vl:latest

# Disable folder watchers if needed
export DISABLE_FOLDER_WATCHERS=1
```

### Advanced Configuration

#### Custom AI Models
```ini
[ollama]
# Use different models for different purposes
model = llama3.2-vision:latest     # Alternative vision model
# model = qwen2.5vl:7b              # Smaller model for faster processing
# model = qwen2.5vl:32b             # Larger model for better accuracy
```

#### Multiple Ollama Servers
```ini
[ollama]
# Load balancing across multiple Ollama instances
server = http://server1:11434,http://server2:11434,http://server3:11434
```

#### Performance Tuning
```ini
[processing]
batch_size = 50          # Larger batches for better throughput
batch_delay = 0          # No delay for maximum speed
max_workers = 4          # Number of worker threads
```

## 📖 Usage Guide

### Getting Started

#### 1. First Launch
After installation, navigate to http://localhost:8491 and you'll see the main dashboard with:
- **Folders**: Manage watched directories
- **Gallery**: Browse tagged images
- **Search**: Find specific images
- **Settings**: Configure the application

#### 2. Adding Folders to Watch
1. Go to **Folders** page (http://localhost:8491/folders)
2. Click **Add Folder** and enter the path to your image directory
3. Enable **Recursive** to include subdirectories
4. Click **Add Folder** to start monitoring

**Example paths:**
```bash
# macOS
/Users/username/Pictures
/Users/username/Photos

# Linux
/home/username/Pictures
/media/external-drive/photos

# Windows
C:\Users\username\Pictures
D:\Photos
```

#### 3. Processing Images
Images are processed automatically when added to watched folders, or you can manually trigger processing:

**Automatic Processing:**
- New images in watched folders are detected and processed in the background
- The Universal Progress Indicator shows real-time progress

**Manual Processing:**
1. Go to **Settings** page
2. Click **"Process All Images with AI"** for unprocessed images
3. Click **"Scan All Folders for New Images"** to find new files
4. Monitor progress in the floating progress indicator

#### 4. Browsing Your Collection
**Gallery View:**
- Navigate to **Gallery** (http://localhost:8491/gallery)
- Browse thumbnail grid of all processed images
- Click images for full-size lightbox view
- Use filters to narrow results

**Search Interface:**
- Go to **Search** page (http://localhost:8491/search)
- Enter text to search image descriptions
- Click tags in the tag cloud to filter by specific tags
- Combine text search with tag filtering

### Core Features

#### Image Management

**Supported Formats:**
- JPEG/JPG (including EXIF metadata)
- PNG (with transparency support)
- GIF (static and animated)
- BMP (Windows bitmap)
- TIFF/TIF (multi-page support)
- HEIC/HEIF (Apple Live Photos, etc.)

**Metadata Handling:**
- Automatically extracts EXIF data
- Preserves original image metadata
- Adds AI-generated descriptions to EXIF
- Embeds tags in image metadata
- Supports geolocation data

**Thumbnail Generation:**
- Creates optimized thumbnails for fast loading
- Maintains aspect ratios
- Configurable size and quality
- Progressive JPEG encoding

#### AI-Powered Analysis

**Description Generation:**
```
Example: "The image shows a vibrant sunset over a calm lake with mountains 
in the background. A small wooden dock extends into the water, and tall 
pine trees frame the scene on both sides."
```

**Tag Extraction:**
```
Generated tags: sunset, lake, mountains, dock, water, pine trees, nature, 
landscape, peaceful, evening, reflection, scenic, outdoor, tranquil
```

**Smart Features:**
- Context-aware descriptions
- Object and scene recognition
- Color and mood analysis
- Compositional elements
- Activity and action detection

#### Search Capabilities

**Text Search:**
- Full-text search through descriptions
- Partial word matching
- Case-insensitive search
- Boolean operators (AND, OR, NOT)

**Tag-Based Filtering:**
- Click tags to filter results
- Multiple tag selection (AND logic)
- Tag frequency visualization
- Hierarchical tag organization

**Advanced Filters:**
- Date range filtering
- File type filtering
- Size and resolution filters
- EXIF metadata search

### Advanced Usage

#### Batch Operations

**Processing Large Collections:**
```bash
# For very large collections, consider:
# 1. Processing in smaller batches
# 2. Running overnight
# 3. Using more powerful hardware
# 4. Monitoring system resources
```

**Performance Tips:**
- Process during off-peak hours
- Ensure sufficient RAM (8GB+ recommended)
- Use SSD storage for better I/O
- Monitor CPU temperature during processing

#### API Usage

The application provides a RESTful API for programmatic access:

**Get all folders:**
```bash
curl http://localhost:8491/api/folders
```

**Add a new folder:**
```bash
curl -X POST http://localhost:8491/api/folders \
  -H "Content-Type: application/json" \
  -d '{"path": "/Users/username/Pictures", "recursive": true}'
```

**Search images:**
```bash
curl "http://localhost:8491/api/images/search?q=sunset&tags=nature,landscape"
```

**Get processing status:**
```bash
curl http://localhost:8491/api/settings/processing-status
```

#### Custom Workflows

**Workflow 1: Photography Archive**
1. Add camera import folder to watched directories
2. Enable recursive scanning for organized folder structure
3. Use date-based organization in your photo management software
4. Search by location, event, or content using generated tags

**Workflow 2: Digital Asset Management**
1. Set up multiple watched folders for different content types
2. Use batch processing for existing archives
3. Implement API-based integration with other tools
4. Export metadata for external catalog systems

**Workflow 3: Content Discovery**
1. Process large image collections with batch operations
2. Use tag cloud to discover content themes
3. Create custom search queries for specific projects
4. Export filtered results for presentations or sharing

### Troubleshooting

#### Common Issues

**Images Not Being Processed:**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Check server logs
tail -f server.log

# Verify folder permissions
ls -la /path/to/watched/folder

# Test AI model manually
ollama run qwen2.5vl:latest "Describe this test image"
```

**Slow Processing:**
- Check available system resources (CPU, RAM)
- Reduce batch size in configuration
- Close other resource-intensive applications
- Consider processing during off-peak hours

**Permission Errors:**
```bash
# Fix folder permissions (macOS/Linux)
chmod -R 755 /path/to/image/folders

# Fix data directory permissions
chmod -R 755 data/

# Check ExifTool installation
which exiftool
exiftool -ver
```

**Database Issues:**
```bash
# Reset database (WARNING: deletes all data)
rm data/image_tagger.db
python -c "from backend.models import init_db, get_db_engine; init_db(get_db_engine('sqlite:///data/image_tagger.db'))"

# Backup database
cp data/image_tagger.db data/image_tagger_backup.db
```

#### Performance Optimization

**Hardware Recommendations:**
- CPU: Multi-core processor (4+ cores recommended)
- RAM: 8GB minimum, 16GB+ for large collections
- Storage: SSD for database and thumbnails
- Network: Stable connection for Ollama communication

**Software Optimization:**
```ini
# config.ini optimizations for performance
[processing]
batch_size = 20          # Larger batches
batch_delay = 0          # No delays
max_workers = 6          # More workers

[storage]
thumbnail_quality = 75   # Lower quality for speed
thumbnail_max_size = 200 # Smaller thumbnails
```

## 🛠️ Development

### Project Structure

```
image-webui/
├── backend/                 # Python backend application
│   ├── api/                # FastAPI route handlers
│   │   ├── folders.py      # Folder management endpoints
│   │   ├── images.py       # Image browsing endpoints
│   │   ├── search.py       # Search functionality
│   │   ├── settings.py     # Configuration and status
│   │   └── tags.py         # Tag management
│   ├── image_tagger/       # AI processing core
│   │   └── core.py         # Image analysis functions
│   ├── app.py              # FastAPI application entry
│   ├── models.py           # SQLAlchemy database models
│   ├── schemas.py          # Pydantic data schemas
│   ├── tasks.py            # Background task handlers
│   ├── config.py           # Configuration management
│   └── globals.py          # Global state management
├── frontend/               # Web interface
│   ├── templates/          # Jinja2 HTML templates
│   │   ├── layout.html     # Base template with navigation
│   │   ├── index.html      # Dashboard page
│   │   ├── folders.html    # Folder management
│   │   ├── gallery.html    # Image browsing
│   │   ├── search.html     # Search interface
│   │   └── settings.html   # Configuration page
│   └── static/            # CSS, JavaScript, images
│       ├── css/           # Custom stylesheets
│       └── js/            # JavaScript modules
│           └── main.js    # Core UI functionality
├── data/                  # Application data
│   ├── image_tagger.db    # Main SQLite database
│   ├── thumbnails/        # Generated thumbnails
│   └── tracking.db        # Processing tracking
├── migrations/            # Database migrations
├── config.ini            # Application configuration
├── requirements.txt      # Python dependencies
└── run.sh               # Startup script
```

### Database Schema

#### Core Tables

**folders** - Watched directory configuration
```sql
CREATE TABLE folders (
    id INTEGER PRIMARY KEY,
    path VARCHAR NOT NULL UNIQUE,
    recursive BOOLEAN DEFAULT true,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**images** - Image metadata and AI analysis results
```sql
CREATE TABLE images (
    id INTEGER PRIMARY KEY,
    path VARCHAR NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_size INTEGER,
    width INTEGER,
    height INTEGER,
    format VARCHAR(10)
);
```

**tags** - Extracted image tags
```sql
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**image_tags** - Many-to-many relationship
```sql
CREATE TABLE image_tags (
    image_id INTEGER REFERENCES images(id),
    tag_id INTEGER REFERENCES tags(id),
    PRIMARY KEY (image_id, tag_id)
);
```

### API Documentation

#### Authentication
Currently, the API does not require authentication. For production deployment, consider implementing:
- API key authentication
- OAuth 2.0 integration
- Rate limiting
- CORS configuration

#### Endpoints

**Folder Management**
```
GET    /api/folders           # List all folders
POST   /api/folders           # Add new folder
PUT    /api/folders/{id}      # Update folder
DELETE /api/folders/{id}      # Remove folder
POST   /api/folders/{id}/scan # Trigger folder scan
```

**Image Operations**
```
GET    /api/images            # List images with pagination
GET    /api/images/{id}       # Get image details
GET    /api/images/search     # Search images
GET    /api/images/stats      # Get collection statistics
```

**Tag Management**
```
GET    /api/tags              # List all tags
GET    /api/tags/{id}/images  # Get images with specific tag
GET    /api/tags/cloud        # Get tag cloud data
```

**System Operations**
```
GET    /api/settings/status           # System status
GET    /api/settings/processing-status # Processing progress
POST   /api/settings/process-all-images # Batch process
POST   /api/settings/scan-all-folders  # Scan all folders
```

#### Response Formats

**Success Response**
```json
{
  "status": "success",
  "message": "Operation completed successfully",
  "data": { /* response data */ }
}
```

**Error Response**
```json
{
  "status": "error",
  "message": "Error description",
  "details": { /* error details */ }
}
```

**Progress Response**
```json
{
  "active": true,
  "current_task": "Processing image 45 of 113",
  "progress": 39.8,
  "total_tasks": 113,
  "completed_tasks": 45,
  "error": null
}
```

### Contributing

#### Development Setup

1. **Fork and Clone**
   ```bash
   git clone https://github.com/yourusername/image-tagger-webui.git
   cd image-tagger-webui
   ```

2. **Development Environment**
   ```bash
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate

   # Install dependencies
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # If available

   # Install pre-commit hooks
   pre-commit install
   ```

3. **Development Server**
   ```bash
   # Run with auto-reload
   uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload

   # Or use the development script
   ./run.sh --dev
   ```

#### Code Style

**Python Code**
- Follow PEP 8 style guidelines
- Use type hints for all function parameters and returns
- Document functions with docstrings
- Maximum line length: 100 characters

**JavaScript Code**
- Use modern ES6+ syntax
- Follow ESLint configuration
- Document functions with JSDoc comments
- Use consistent indentation (2 spaces)

**HTML/CSS**
- Use semantic HTML elements
- Follow Bootstrap conventions
- Maintain responsive design principles
- Use CSS custom properties for theming

#### Testing

**Run Tests**
```bash
# Run all tests
python -m pytest

# Run specific test categories
python -m pytest tests/test_api.py      # API tests
python -m pytest tests/test_models.py   # Database tests
python -m pytest tests/test_tasks.py    # Background task tests

# Run with coverage
python -m pytest --cov=backend --cov-report=html
```

**Test Categories**
- Unit tests for core functionality
- Integration tests for API endpoints
- End-to-end tests for complete workflows
- Performance tests for large datasets

#### Pull Request Process

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**
   - Write tests for new functionality
   - Update documentation
   - Ensure all tests pass
   - Follow code style guidelines

3. **Submit Pull Request**
   - Provide clear description of changes
   - Reference related issues
   - Include screenshots for UI changes
   - Ensure CI checks pass

### Deployment

#### Production Deployment

**Using Docker (Recommended)**
```bash
# Build production image
docker build -t image-tagger-webui:latest .

# Run with docker-compose
docker-compose -f docker-compose.prod.yml up -d

# Or run directly
docker run -d \
  -p 8000:8000 \
  -v /path/to/images:/app/images \
  -v /path/to/data:/app/data \
  image-tagger-webui:latest
```

**Manual Deployment**
```bash
# Set production environment
export ENVIRONMENT=production
export DEBUG=false

# Use production ASGI server
gunicorn backend.app:app -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 --access-logfile - --error-logfile -
```

**Reverse Proxy (Nginx)**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /path/to/app/frontend/static/;
        expires 30d;
    }

    location /thumbnails/ {
        alias /path/to/app/data/thumbnails/;
        expires 7d;
    }
}
```

#### Security Considerations

**Production Checklist**
- [ ] Disable debug mode
- [ ] Configure CORS properly
- [ ] Implement authentication
- [ ] Set up HTTPS/TLS
- [ ] Configure firewall rules
- [ ] Regular security updates
- [ ] Database backups
- [ ] Log monitoring
- [ ] Resource limits

## 🔧 Maintenance

### Regular Maintenance Tasks

#### Database Maintenance
```bash
# Vacuum SQLite database (reclaim space)
sqlite3 data/image_tagger.db "VACUUM;"

# Analyze database for query optimization
sqlite3 data/image_tagger.db "ANALYZE;"

# Check database integrity
sqlite3 data/image_tagger.db "PRAGMA integrity_check;"

# Backup database
cp data/image_tagger.db "backups/image_tagger_$(date +%Y%m%d).db"
```

#### Thumbnail Management
```bash
# Clean orphaned thumbnails
python -c "
from backend.models import SessionLocal, Image
from pathlib import Path
import os

db = SessionLocal()
images = db.query(Image).all()
valid_paths = {str(Path(img.path).stem) for img in images}

thumb_dir = Path('data/thumbnails')
for thumb_file in thumb_dir.glob('*.jpg'):
    if thumb_file.stem not in valid_paths:
        print(f'Removing orphaned thumbnail: {thumb_file}')
        thumb_file.unlink()
"

# Regenerate all thumbnails
python -c "
from backend.tasks import regenerate_thumbnails
regenerate_thumbnails()
"
```

#### Log Management
```bash
# Rotate logs (if using file logging)
logrotate /etc/logrotate.d/image-tagger

# Clean old logs
find logs/ -name "*.log" -mtime +30 -delete

# Monitor log size
du -sh logs/
```

### Monitoring & Health Checks

#### System Health
```bash
# Check application status
curl -f http://localhost:8000/api/settings/status || echo "Service down"

# Check database connectivity
python -c "
from backend.models import SessionLocal
try:
    db = SessionLocal()
    db.execute('SELECT 1')
    print('Database: OK')
except Exception as e:
    print(f'Database error: {e}')
"

# Check Ollama connectivity
curl -f http://localhost:11434/api/tags || echo "Ollama unavailable"
```

#### Performance Monitoring
```bash
# Monitor resource usage
htop
iostat -x 1
df -h

# Database query performance
sqlite3 data/image_tagger.db ".timer on" ".stats on" "SELECT COUNT(*) FROM images;"

# Application metrics
curl http://localhost:8000/api/settings/stats
```

### Backup & Recovery

#### Backup Strategy
```bash
#!/bin/bash
# backup.sh - Comprehensive backup script

BACKUP_DIR="/path/to/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup database
cp data/image_tagger.db "$BACKUP_DIR/"
cp data/image-tagger-tracking.db "$BACKUP_DIR/"

# Backup configuration
cp config.ini "$BACKUP_DIR/"

# Backup thumbnails (optional - can be regenerated)
tar -czf "$BACKUP_DIR/thumbnails.tar.gz" data/thumbnails/

# Create backup manifest
echo "Backup created: $(date)" > "$BACKUP_DIR/manifest.txt"
echo "Database size: $(du -h data/image_tagger.db | cut -f1)" >> "$BACKUP_DIR/manifest.txt"
echo "Image count: $(sqlite3 data/image_tagger.db 'SELECT COUNT(*) FROM images;')" >> "$BACKUP_DIR/manifest.txt"

echo "Backup completed: $BACKUP_DIR"
```

#### Recovery Procedures
```bash
# Restore from backup
BACKUP_DIR="/path/to/backups/20250610_120000"

# Stop application
./stop.sh

# Restore database
cp "$BACKUP_DIR/image_tagger.db" data/
cp "$BACKUP_DIR/image-tagger-tracking.db" data/

# Restore configuration
cp "$BACKUP_DIR/config.ini" .

# Restore thumbnails
tar -xzf "$BACKUP_DIR/thumbnails.tar.gz" -C data/

# Restart application
./run.sh

echo "Recovery completed from $BACKUP_DIR"
```

### Troubleshooting Guide

#### Common Error Messages

**"Database is locked"**
```bash
# Solution 1: Check for hung processes
ps aux | grep python
kill -9 <process_id>

# Solution 2: Remove lock file
rm data/image_tagger.db-wal
rm data/image_tagger.db-shm

# Solution 3: Backup and restore database
sqlite3 data/image_tagger.db ".backup backup.db"
mv backup.db data/image_tagger.db
```

**"Ollama connection refused"**
```bash
# Check if Ollama is running
systemctl status ollama
# or
ps aux | grep ollama

# Start Ollama
ollama serve &

# Verify model availability
ollama list
```

**"Permission denied accessing images"**
```bash
# Fix file permissions
chmod -R 755 /path/to/image/directories

# Check SELinux (if applicable)
setsebool -P httpd_can_network_connect 1
```

**"Out of disk space"**
```bash
# Check disk usage
df -h

# Clean up thumbnails
rm -rf data/thumbnails/*

# Clean up logs
truncate -s 0 logs/*.log

# Clean up tracking database
rm data/image-tagger-tracking.db
```

#### Debug Mode

**Enable Debug Logging**
```ini
# config.ini
[general]
debug = true
log_level = DEBUG
```

**Detailed Error Logging**
```bash
# Run with verbose logging
python -m backend.app --log-level DEBUG

# Monitor logs in real-time
tail -f server.log | grep ERROR
```

**Performance Profiling**
```python
# Add to app.py for performance analysis
import cProfile
import pstats

def profile_route():
    profiler = cProfile.Profile()
    profiler.enable()
    # ... route logic ...
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)
```

## 📚 Additional Resources

### Documentation
- [Progress Indicator Documentation](PROGRESS_INDICATOR_DOCUMENTATION.md) - Detailed progress tracking system docs
- [Universal Status Indicator](UNIVERSAL_STATUS_INDICATOR.md) - UI component documentation
- [API Reference](docs/api.md) - Complete API documentation
- [Configuration Guide](docs/configuration.md) - Advanced configuration options

### External Resources
- [Ollama Documentation](https://ollama.ai/docs) - AI model management
- [FastAPI Documentation](https://fastapi.tiangolo.com/) - Web framework
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/) - Database ORM
- [Bootstrap Documentation](https://getbootstrap.com/docs/) - UI framework

### Community
- [GitHub Issues](https://github.com/yourusername/image-tagger-webui/issues) - Bug reports and feature requests
- [Discussions](https://github.com/yourusername/image-tagger-webui/discussions) - Community support
- [Wiki](https://github.com/yourusername/image-tagger-webui/wiki) - User guides and tutorials

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Ollama Team** - For providing the excellent AI model serving infrastructure
- **FastAPI Team** - For the high-performance web framework
- **Bootstrap Team** - For the responsive UI components
- **SQLAlchemy Team** - For the robust database abstraction layer
- **PIL/Pillow Team** - For image processing capabilities
- **ExifTool Team** - For comprehensive metadata handling

## 📊 Statistics

- **Lines of Code**: ~15,000+ (Python, JavaScript, HTML, CSS)
- **Supported Image Formats**: 7 (JPEG, PNG, GIF, BMP, TIFF, HEIC, HEIF)
- **API Endpoints**: 25+ REST endpoints
- **Database Tables**: 4 core tables with relationships
- **UI Pages**: 5 main interface pages
- **Background Tasks**: Real-time folder monitoring and batch processing

---

**Last Updated**: June 10, 2025  
**Version**: 1.0.0  
**Status**: ✅ Production Ready  
**Platform**: Cross-platform (macOS, Linux, Windows)  
**Python**: 3.9+ Required

- **libheif**: For HEIC/HEIF image support
  ```bash
  # macOS
  brew install libheif
  
  # Ubuntu/Debian
  apt-get install libheif-dev
  ```

## Installation

### Using Docker (Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/image-tagger.git
   cd image-tagger/image-webui
   ```

2. Edit the `docker-compose.yml` file to point to your image directories:
   ```yaml
   volumes:
     - ./data:/app/data
     # IMPORTANT: Edit the lines below to mount your image directories
     - /path/to/your/photos:/images/photos:ro  # Example: Photos directory
     - /path/to/your/wallpapers:/images/wallpapers:ro  # Example: Wallpapers directory
   ```
   ```yaml
   volumes:
     - /path/to/your/images:/images:ro
   ```

3. Run the application:
   ```bash
   docker-compose up -d
   ```

4. Access the WebUI at http://localhost:8491

### Manual Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/image-tagger.git
   cd image-tagger/image-webui
   ```

2. Install system dependencies:
   ```bash
   # Debian/Ubuntu
   sudo apt-get update
   sudo apt-get install -y libheif-dev libimage-exiftool-perl
   
   # macOS
   brew install libheif exiftool
   ```

3. Create a virtual environment and install Python dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. Run the application:
   ```bash
   chmod +x run.sh
   ./run.sh
   ```

5. Access the WebUI at http://localhost:8491

## Configuration

### Environment Variables

The following environment variables can be set to customize the application:

- `HOST`: Hostname to bind to (default: "0.0.0.0")
- `PORT`: Port to listen on (default: 8000)
- `DB_PATH`: SQLite database URL (default: "sqlite:///data/image_tagger.db")
- `OLLAMA_SERVER`: URL of the Ollama server (default: "http://127.0.0.1:11434")
- `OLLAMA_MODEL`: Vision model to use (default: "llama3.2-vision")

5. Access the WebUI at http://localhost:8491

## Usage

### Managing Folders

1. Go to the "Folders" page
2. Add folders you want to watch for new images
3. Toggle "Recursive" to include subdirectories
4. Use "Scan Now" to process existing images in a folder

### Browsing Images

1. Go to the "Gallery" page
2. Browse all tagged images
3. Filter by description text or tags
4. Click on an image to view it in full size

### Searching Images

1. Go to the "Search" page
2. Enter text to search in descriptions
3. Select tags from the tag cloud
4. View and explore search results

## API Documentation

The API documentation is available at http://localhost:8491/docs when the application is running.

### Key Endpoints

- `/api/folders`: Manage watched folders
- `/api/images`: List and retrieve images
- `/api/search`: Search for images by text or tags
- `/api/tags`: Get all available tags
- `/api/tagcloud`: Get tag usage statistics for tag cloud visualization

## Database Migrations

The application uses Alembic for database migrations. If you need to make schema changes:

```bash
# Create a new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head
```

## Troubleshooting

### Ollama Connection Issues
- Ensure Ollama is running and accessible at the configured URL
- Check that the vision model is properly installed (`ollama pull llama3.2-vision`)
- The application will automatically retry connections to Ollama

### File Permissions
- Ensure the application has read access to your image directories
- Ensure write access to the data directory for storing database and thumbnails

### Docker Issues
- Make sure to properly configure volume mounts in docker-compose.yml
- If using host networking, ensure port 8000 is not already in use

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Image Tagger WebUI

## Unified Installer & CLI Integration (NEW)

- The CLI tool is now integrated into the WebUI backend (see `backend/image_tagger_cli.py`).
- Use the new `install-all.sh` script at the project root to install **both** the CLI and the WebUI in one step.
- The CLI (`image-tagger`) and search tool (`image-search`) will be available system-wide after installation.
- All dependencies are managed in a single Python environment under `venv`.
