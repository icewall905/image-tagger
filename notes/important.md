---
note_type: master_overview
date: 2025-06-10
summary: Complete overview of Image Tagger project architecture, components, and critical information
related_files:
  - README.md
  - image-webui/README.md
  - image-webui/config.ini
  - image-tagger-install.sh
  - notes/2025-06-10_vscode_import_resolution_fix.md
  - notes/progress_tracking_and_permissions_fix.md
---

# Image Tagger Project - Complete Overview

## 🎯 Project Purpose
AI-powered image tagging and organization system with both CLI and modern web interfaces. Automatically generates detailed descriptions and searchable tags for image collections using Ollama vision models, storing metadata directly in image files for portability.

## 🏗️ Architecture Overview

### Dual Interface System
1. **CLI Tool** (`image-tagger-install.sh`) - Standalone command-line interface
2. **Web UI** (`image-webui/`) - Modern responsive web application

### Core Components

#### Web UI Architecture (Primary Interface)
```
image-webui/
├── backend/              # FastAPI application
│   ├── api/             # REST API endpoints
│   ├── image_tagger/    # AI processing core
│   ├── app.py          # Main application entry
│   ├── models.py       # SQLAlchemy database models
│   └── tasks.py        # Background processing
├── frontend/           # Jinja2 templates + Bootstrap 5
├── data/              # SQLite database + thumbnails
└── migrations/        # Alembic database migrations
```

#### Technology Stack
- **Backend**: FastAPI + SQLAlchemy + SQLite
- **Frontend**: Bootstrap 5 + jQuery + Jinja2
- **AI**: Ollama + qwen2.5vl:latest vision model
- **Image Processing**: Pillow + ExifTool
- **File Monitoring**: Watchdog (real-time folder watching)
- **Configuration**: INI-based with environment variable overrides

## 🚀 Installation & Deployment

### Quick Start
```bash
# Clone and setup
git clone <repo> && cd image-tagger-1

# CLI version
chmod +x image-tagger-install.sh
sudo ./image-tagger-install.sh

# Web UI version
cd image-webui
./run.sh
# Access at http://localhost:8000
```

### Prerequisites
- macOS/Linux with Python 3.9+
- Ollama server with qwen2.5vl:latest model
- ExifTool for metadata manipulation
- 8GB+ RAM recommended for large collections

## ⚙️ Configuration Management

### Primary Config File (`image-webui/config.ini`)
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
model = qwen2.5vl:latest  # Critical: Use qwen2.5vl, NOT llama3.2-vision
timeout = 180
temperature = 0.3

[storage]
thumbnail_dir = data/thumbnails
thumbnail_max_size = 300

[processing]
batch_size = 10
background_processing = true

[tracking]
db_path = data/image-tagger-tracking.db  # Fixed: Moved from /var/log
use_file_tracking = true
```

### Environment Variable Overrides
- `DB_PATH`, `OLLAMA_SERVER`, `OLLAMA_MODEL`, `HOST`, `PORT`
- Environment variables take precedence over config file

## 🔧 Core Functionality

### Image Processing Pipeline
1. **Detection**: Watchdog monitors registered folders for new images
2. **Analysis**: Ollama vision model generates descriptions + tags
3. **Storage**: Metadata embedded in image files (EXIF/PNG chunks)
4. **Database**: SQLite stores processed image metadata for searching
5. **Thumbnails**: Auto-generated for web gallery viewing

### Supported Formats
- JPEG/JPG (with EXIF metadata)
- PNG (with text chunks)
- GIF, BMP, TIFF/TIF
- HEIC/HEIF (Apple Live Photos)

### AI Processing Features
- **Smart Descriptions**: Contextual single-paragraph descriptions
- **Tag Extraction**: Automated keyword extraction from descriptions
- **Retry Logic**: Robust error handling with configurable retries
- **Duplicate Detection**: File tracking prevents reprocessing unchanged files
- **Batch Processing**: Configurable batching for large collections

## 🌐 Web Interface Features

### Pages & Functionality
- **Dashboard** (`/`) - System overview and statistics
- **Folders** (`/folders`) - Manage watched directories
- **Gallery** (`/gallery`) - Browse images with thumbnails
- **Search** (`/search`) - Full-text and tag-based searching  
- **Settings** (`/settings`) - Configuration management

### Universal Progress Indicator
- Real-time progress tracking across all operations
- Image-level progress updates (not just folder-level)
- Background processing with non-blocking UI

### API Endpoints
```
GET/POST /api/folders     # Folder management
GET      /api/images      # Image browsing with pagination
GET      /api/search      # Search functionality
GET      /api/tags        # Tag management
GET/POST /api/settings    # Configuration & system status
```

## 🗄️ Database Schema

### Core Tables
- **folders**: Watched directory configuration
- **images**: Image metadata and AI analysis results
- **tags**: Extracted image tags
- **image_tags**: Many-to-many relationship table

### Migration Management
- Alembic for schema versioning
- Automatic migrations via `setup_db.sh`
- Backup functionality in settings UI

## 🚨 Recent Critical Fixes (June 2025)

### 1. AI Model Configuration Fix
**Problem**: System defaulting to `llama3.2-vision` instead of `qwen2.5vl:latest`
**Solution**: Updated 8+ files with correct model references
**Files Fixed**: `backend/api/settings.py`, `backend/api/folders.py`, `backend/app.py`, `backend/image_tagger/core.py`, templates, config files

### 2. Progress Tracking Enhancement  
**Problem**: Universal Status Indicator stuck at "0 / 0 completed"
**Solution**: Enhanced progress tracking from folder-level to image-level granularity
**Result**: Real-time "Processing image X of Y" updates

### 3. Permissions Fix
**Problem**: Tracking database trying to write to `/var/log/` (permission denied)
**Solution**: Moved tracking DB to application data directory
**New Path**: `data/image-tagger-tracking.db`

### 4. VS Code Import Resolution
**Problem**: VS Code showing import errors despite working application
**Solution**: Enhanced `.vscode/settings.json` and `pyrightconfig.json`
**Status**: Functional priority over IDE warnings

## 🔍 Search & Discovery

### Search Capabilities
- **Full-text search** through AI-generated descriptions
- **Tag-based filtering** with multiple tag selection
- **Visual tag cloud** showing tag frequency
- **Advanced filters**: date range, file type, resolution
- **Boolean operators**: AND, OR, NOT support

## 🛠️ Development & Maintenance

### Project Structure
```
image-tagger-1/
├── README.md                    # CLI documentation
├── image-tagger-install.sh      # CLI installer script
├── image-tagger.sh             # Launcher script
├── image-webui/                # Web application
├── notes/                      # Project documentation
│   ├── instructions.md         # LLM guidance (immutable)
│   ├── important.md           # This overview
│   └── *.md                   # Issue-specific notes
└── LICENSE
```

### Development Workflow
1. **Local Development**: `./run.sh` starts dev server
2. **Database Changes**: Use Alembic migrations
3. **Configuration**: Modify `config.ini` or environment variables
4. **Testing**: Comprehensive test suite in `image-webui/test_*.py`
5. **Deployment**: Docker support with production configurations

### Performance Tuning
- **Hardware**: 4+ cores, 8GB+ RAM, SSD storage recommended
- **Batch Size**: Adjust based on system resources (default: 10)
- **Worker Threads**: Configure based on CPU cores (default: 4)
- **Thumbnail Quality**: Balance between size and quality (default: 85%)

## 🔐 Security Considerations

### Current Security Model
- **CORS**: Configurable (default: permissive for development)
- **Authentication**: None (local use assumed)
- **Rate Limiting**: Optional, disabled by default
- **File Access**: Read access to image directories required

### Production Hardening Needed
- Implement authentication/authorization
- Configure restrictive CORS policies
- Enable rate limiting
- Set up HTTPS/TLS
- Configure firewall rules

## 📊 System Monitoring

### Health Checks
```bash
# Application status
curl http://localhost:8000/api/settings/status

# Database connectivity  
curl http://localhost:8000/api/settings/test-db

# Ollama connectivity
curl http://localhost:11434/api/tags
```

### Log Locations
- **Web UI**: `image-webui/server.log`
- **CLI**: `/var/log/image-tagger.log` (if using CLI installer)
- **Configuration**: Centralized logging through Python logging module

## ⚠️ Known Issues & Limitations

### Current Limitations
1. **Single User**: No multi-user support
2. **Local Storage**: SQLite limits concurrent access
3. **No Authentication**: Open access to all features
4. **Memory Usage**: Large images may consume significant RAM during processing

### VS Code Development Notes
- Import resolution issues are cosmetic (application works correctly)
- Use pragmatic approach: ignore IDE warnings, focus on functionality
- Consider using virtual environment for cleaner IDE experience

## 🎯 Future Enhancement Opportunities

### High Priority
- Multi-user authentication system
- PostgreSQL support for better concurrency
- Improved error handling and recovery
- Performance optimizations for large collections

### Medium Priority  
- Docker deployment automation
- Advanced search filters (color, composition, etc.)
- Batch operations UI
- Export/import functionality

### Low Priority
- Mobile app companion
- Cloud storage integration
- Advanced AI model selection
- Custom tag taxonomies

## 📋 Quick Reference Commands

```bash
# Start Web UI
cd image-webui && ./run.sh

# CLI Processing
image-tagger -r /path/to/images

# Database Operations
cd image-webui && ./setup_db.sh

# Health Checks
curl http://localhost:8000/api/settings/stats

# View Progress
tail -f image-webui/server.log
```

## 🏷️ Project Metadata
- **Version**: 0.5 (CLI), 1.0+ (Web UI)
- **License**: MIT
- **Author**: HNB
- **Primary Language**: Python 3.9+
- **Last Major Update**: June 2025 (AI model fixes, progress tracking)
- **Status**: Production-ready for local use, development-ready for multi-user deployment
