# Image Tagger

An AI-powered tool for automatically tagging and organizing your image collection. This tool uses the Ollama API to generate detailed descriptions and searchable tags for your images, storing them directly in the image metadata for easy searching and organization.

Make sure llama3.2-vision is first pulled on your Ollama instance.

## Features

- 🤖 AI-powered image analysis using Ollama's vision models
- 🏷️ Automatic tag generation from image content
- 📝 Detailed image descriptions stored in metadata
- 🔍 Built-in search utility for finding images by content
- 💾 Metadata stored directly in image files (EXIF/PNG chunks)
- 🖥️ Cross-platform support (macOS and Linux)
- 📂 Recursive directory processing
- 📊 Detailed logging and progress tracking

## Prerequisites

- macOS or Linux (Debian/Ubuntu)
- Python 3.x
- For macOS: Homebrew
- For Linux: `apt-get` package manager
- Ollama server running locally or accessible via network (with llama3.2-vision pulled)

## Installation

### Automatic Installation

1. Download the installation script:
```bash
git clone https://github.com/icewall905/image-tagger.git && cd image-tagger
```

2. Make it executable:
```bash
chmod +x install.sh
```

3. Run the installation script:
```bash
sudo ./install.sh
```

The script will automatically:
- Install required system dependencies
- Set up Python virtual environment
- Install required Python packages
- Create necessary log files and directories
- Install both the tagger and search utilities

### Manual Installation

If you prefer manual installation, ensure you have the following Python packages installed:
- pillow
- requests
- piexif

## Usage

### Image Tagger

The `image-tagger` command processes images and adds AI-generated descriptions and tags to their metadata.

```bash
# Process all images in current directory
image-tagger

# Process a single image
image-tagger image.jpg

# Process all images in a specific directory
image-tagger /path/to/images

# Process images recursively
image-tagger -r /path/to/images

# Use custom Ollama endpoint
image-tagger -e http://localhost:11434 image.jpg

# Override existing tags
image-tagger --override image.jpg

# Quiet mode (minimal output)
image-tagger -q image.jpg

# Show help
image-tagger -h
```

### Image Search

The `image-search` utility helps you find images based on their content descriptions and tags.

```bash
# Search current directory for images containing "table" in metadata
image-search "table"

# Recursive search from a specific path
image-search -r -p /path/to/images "bottle"

# Non-recursive search in specific directory
image-search -p /some/dir "woman"

# Show help
image-search -h
```

## Log Files

The tools maintain detailed logs at:
- `/var/log/image-tagger.log` - For tagging operations
- `/var/log/image-search.log` - For search operations

## Metadata Storage

- JPEG/TIFF: Metadata is stored in EXIF tags (ImageDescription, UserComment, XPKeywords)
- PNG: Metadata is stored in PNG text chunks
- All metadata is stored directly in the image files for portability

## Troubleshooting

1. **Ollama Connection Issues**
   - Ensure Ollama is running (`ollama serve`)
   - Check the endpoint URL (-e option)
   - Verify network connectivity to Ollama server

2. **Permission Issues**
   - Ensure log files are writable
   - Check directory permissions
   - Run with sudo if necessary

3. **Python Environment Issues**
   - Verify Python installation
   - Check virtual environment activation
   - Confirm package installations

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

Created by HNB

## Version

Current version: 0.5
