# Image Tagger WebUI

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

## Requirements

- Python 3.9+
- Ollama running with a vision-capable model (e.g., llama3.2-vision)
- ExifTool
- libheif for HEIC/HEIF support

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

4. Access the WebUI at http://localhost:8000

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

5. Access the WebUI at http://localhost:8000

## Configuration

### Environment Variables

The following environment variables can be set to customize the application:

- `HOST`: Hostname to bind to (default: "0.0.0.0")
- `PORT`: Port to listen on (default: 8000)
- `DB_PATH`: SQLite database URL (default: "sqlite:///data/image_tagger.db")
- `OLLAMA_SERVER`: URL of the Ollama server (default: "http://127.0.0.1:11434")
- `OLLAMA_MODEL`: Vision model to use (default: "llama3.2-vision")

5. Access the WebUI at http://localhost:8000

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

The API documentation is available at http://localhost:8000/docs when the application is running.

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
