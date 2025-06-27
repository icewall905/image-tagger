---
note_type: deployment_guide
date: 2025-06-10
summary: Deployment scenarios, CLI vs Web UI comparison, and operational guidance
related_files:
  - image-tagger-install.sh
  - image-webui/run.sh
  - image-tagger.sh
  - notes/important.md
---

# Image Tagger Deployment & Operational Guide

## 🎯 Deployment Scenarios

### Scenario 1: Personal CLI Usage
**Best for**: Individual users, batch processing, scripting
```bash
# One-time setup
sudo ./image-tagger-install.sh

# Usage
image-tagger -r /Users/username/Pictures
image-search "sunset beach"
```

### Scenario 2: Personal Web Interface  
**Best for**: Interactive browsing, ongoing management, visual interface
```bash
cd image-webui
./run.sh
# Access: http://localhost:8491
```

### Scenario 3: Dual Setup (Recommended)
**Best for**: Flexibility, both CLI scripting and web browsing
```bash
# Install both
./image-tagger.sh
# Choose option 1 for CLI, option 2 for Web UI
```

### Scenario 4: Server Deployment
**Best for**: Team access, always-on processing
```bash
# Production deployment with Docker
docker-compose up -d

# Or systemd service
# [See image-webui/README.md for full instructions]
```

## 🔄 CLI vs Web UI Comparison

| Feature | CLI Tool | Web UI |
|---------|----------|---------|
| **Installation** | System-wide (`/usr/local/bin`) | Local directory |
| **Interface** | Command line | Modern web browser |
| **Processing** | Immediate, synchronous | Background, asynchronous |
| **Progress Tracking** | Terminal output | Real-time UI indicator |
| **Search** | `image-search` command | Interactive web interface |
| **Configuration** | YAML config file | Web-based settings page |
| **Database** | File tracking only | Full SQLite with gallery |
| **Thumbnails** | None | Auto-generated |
| **Folder Watching** | Manual scanning | Real-time monitoring |
| **Scalability** | Single execution | Multi-user capable |
| **Dependencies** | Python + ExifTool | + FastAPI + SQLAlchemy |

## 🛠️ Operational Patterns

### Daily Usage Patterns

#### Pattern 1: Import New Photos
```bash
# CLI approach
image-tagger -r ~/Pictures/2025-06-10/

# Web UI approach
1. Add folder via Folders page
2. Click "Scan All Folders"
3. Monitor progress in UI
```

#### Pattern 2: Find Specific Images
```bash
# CLI approach
image-search -r ~/Pictures "beach vacation"

# Web UI approach
1. Visit Search page
2. Enter "beach vacation"
3. Browse visual results
```

#### Pattern 3: Bulk Processing
```bash
# CLI approach (preferred for bulk)
image-tagger --batch-size 20 --batch-delay 2 -r /massive/photo/archive

# Web UI approach
1. Settings -> Process All Images
2. Monitor Universal Progress Indicator
```

### Maintenance Workflows

#### Weekly Maintenance
```bash
# Clean up tracking database
image-tagger --clean-db

# Or via Web UI: Settings -> Test Database
```

#### Monthly Maintenance  
```bash
# Backup database (Web UI only)
# Visit Settings -> Backup Database

# Check system health
curl http://localhost:8491/api/settings/stats
```

#### Performance Monitoring
```bash
# Monitor resource usage during processing
htop
iostat -x 1

# Check processing speed
tail -f /var/log/image-tagger.log  # CLI
tail -f image-webui/server.log    # Web UI
```

## 🚀 Setup Recommendations by Use Case

### Personal Photo Organization
**Recommended**: Web UI + selective CLI use
```bash
# Setup
cd image-webui && ./run.sh

# Workflow
1. Register important photo folders
2. Let background processing handle new photos
3. Use web interface for browsing/searching
4. Use CLI for one-off batch operations
```

### Professional Photography Workflow
**Recommended**: CLI-focused with Web UI for clients
```bash
# Setup both
sudo ./image-tagger-install.sh  # For your workflow
cd image-webui && ./run.sh      # For client access

# Workflow
1. Process shoots via CLI (faster, scriptable)
2. Share web UI URL with clients for browsing
3. Use search to quickly find specific shots
```

### Family/Group Photo Sharing
**Recommended**: Web UI deployment on local server
```bash
# Setup on always-on machine
docker-compose up -d

# Configure
- Set host = 0.0.0.0 in config.ini
- Add family members' photo folders
- Share URL: http://[server-ip]:8491
```

### Developer/Technical User
**Recommended**: Full setup with both interfaces
```bash
# Development setup
cd image-webui
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
./run.sh

# Plus CLI for scripting
sudo ./image-tagger-install.sh
```

## 📊 Performance Guidelines

### Hardware Sizing

#### Small Collection (< 1,000 images)
- **CPU**: 2+ cores
- **RAM**: 4GB
- **Storage**: 100MB for app + 10-50MB thumbnails
- **Processing Time**: ~1-2 seconds per image

#### Medium Collection (1,000 - 10,000 images)
- **CPU**: 4+ cores  
- **RAM**: 8GB
- **Storage**: 100MB for app + 100-500MB thumbnails
- **Processing Time**: Initial batch 2-6 hours

#### Large Collection (10,000+ images)
- **CPU**: 6+ cores
- **RAM**: 16GB
- **Storage**: 1GB+ for thumbnails
- **Processing Time**: Plan for overnight processing

### Configuration Tuning

#### Fast Processing (High-end hardware)
```ini
[processing]
batch_size = 50
batch_delay = 0
max_workers = 8

[ollama]
timeout = 120  # Shorter timeout
```

#### Conservative Processing (Limited hardware)
```ini
[processing]
batch_size = 5
batch_delay = 5
max_workers = 2

[ollama]
timeout = 300  # Longer timeout
```

#### Storage Optimization
```ini
[storage]
thumbnail_max_size = 200     # Smaller thumbnails
thumbnail_quality = 70       # Lower quality
max_cache_size_mb = 500     # Limit cache
```

## 🔧 Troubleshooting Guide

### Common Issues & Solutions

#### "Ollama connection refused"
```bash
# Check if Ollama is running
ps aux | grep ollama
ollama serve &

# Verify model available
ollama list | grep qwen2.5vl
ollama pull qwen2.5vl:latest  # If missing
```

#### "Permission denied" errors
```bash
# Fix file permissions
chmod -R 755 /path/to/photos

# Fix app data permissions
chmod -R 755 image-webui/data/
```

#### Slow processing
```bash
# Check system resources
htop
df -h

# Reduce batch size in config
# Close other applications
# Process during off-peak hours
```

#### Database locked
```bash
# Kill hung processes
ps aux | grep python | grep image-tagger
kill -9 [process_id]

# Remove lock files
rm image-webui/data/image_tagger.db-wal
rm image-webui/data/image_tagger.db-shm
```

### Performance Optimization

#### I/O Optimization
- Use SSD storage for database and thumbnails
- Separate image storage from app storage if possible
- Monitor disk I/O during processing (`iostat -x 1`)

#### Memory Optimization
- Monitor RAM usage during processing
- Reduce batch size if memory pressure occurs
- Consider processing smaller folders separately

#### Network Optimization (for Ollama)
- Use local Ollama instance when possible
- If using remote Ollama, ensure stable network
- Consider multiple Ollama instances for load balancing

## 🏷️ Quick Decision Matrix

| Need | Recommendation |
|------|----------------|
| Just want to tag photos quickly | CLI tool |
| Want to browse and search visually | Web UI |
| Need to share with others | Web UI |
| Processing huge collections | CLI tool |
| Want folder monitoring | Web UI |
| Need thumbnails | Web UI |
| Want progress tracking | Both (different styles) |
| Need API access | Web UI |
| Want configuration via UI | Web UI |
| Prefer command-line workflow | CLI tool |
| Need database backups | Web UI |
| Want real-time processing | Web UI |

The choice isn't exclusive - many users benefit from having both interfaces available for different use cases.
