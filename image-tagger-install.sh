#!/bin/bash

# Text formatting
BOLD=$(tput bold)
NORMAL=$(tput sgr0)
GREEN=$(tput setaf 2)
RED=$(tput setaf 1)
YELLOW=$(tput setaf 3)

# Function to print status messages
print_status() {
    echo "${BOLD}${GREEN}==>${NORMAL} $1"
}

print_error() {
    echo "${BOLD}${RED}Error:${NORMAL} $1"
}

print_warning() {
    echo "${BOLD}${YELLOW}Warning:${NORMAL} $1"
}

# Function to exit on error
exit_on_error() {
    print_error "$1"
    exit 1
}

# Check for sudo access
check_sudo() {
    if ! sudo -v &> /dev/null; then
        exit_on_error "This script requires sudo privileges for installation. Please run with sudo."
    fi
}

# Detect the user
USER_NAME="$(whoami)"

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    print_status "Detected macOS system"
    
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        exit_on_error "Homebrew is required but not installed. Please install Homebrew first.\nVisit https://brew.sh for installation instructions."
    fi
    
    print_status "Installing dependencies via Homebrew..."
    brew install python@3.13 || exit_on_error "Failed to install python@3.13 via Homebrew."
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux (Assuming Debian/Ubuntu)
    print_status "Detected Linux system (assuming Debian/Ubuntu)"
    
    print_status "Installing dependencies..."
    check_sudo
    sudo apt-get update || exit_on_error "Failed to update package lists."
    sudo apt-get install -y python3-pip python3-venv || exit_on_error "Failed to install python3-pip and python3-venv."
else
    exit_on_error "Unsupported operating system: $OSTYPE"
fi

# Define installation directory
INSTALL_DIR="/opt/image-tagger"

# Remove any existing installation
if [ -d "$INSTALL_DIR" ]; then
    print_status "Removing existing installation at ${INSTALL_DIR}..."
    check_sudo
    sudo rm -rf "$INSTALL_DIR" || exit_on_error "Failed to remove existing installation directory."
fi

# Create installation directory
print_status "Creating installation directory at ${INSTALL_DIR}..."
check_sudo
sudo mkdir -p "$INSTALL_DIR" || exit_on_error "Failed to create installation directory."

# Set ownership of the installation directory to the user
print_status "Setting ownership of ${INSTALL_DIR} to user ${USER_NAME}..."
check_sudo
sudo chown -R "$USER_NAME:$(id -gn "$USER_NAME")" "$INSTALL_DIR" || exit_on_error "Failed to set ownership."

# Define log file paths
IMAGE_TAGGER_LOG="/var/log/image-tagger.log"
IMAGE_SEARCH_LOG="/var/log/image-search.log"

# Create log files
print_status "Creating log files..."
check_sudo
sudo touch "$IMAGE_TAGGER_LOG" "$IMAGE_SEARCH_LOG" || exit_on_error "Failed to create log files."

# Set ownership to the user
print_status "Setting ownership of log files to user ${USER_NAME}..."
check_sudo
sudo chown "$USER_NAME:$(id -gn "$USER_NAME")" "$IMAGE_TAGGER_LOG" "$IMAGE_SEARCH_LOG" || exit_on_error "Failed to set ownership of log files."

# Set appropriate permissions (read and write for owner, read for group and others)
print_status "Setting permissions for log files..."
check_sudo
sudo chmod 644 "$IMAGE_TAGGER_LOG" "$IMAGE_SEARCH_LOG" || exit_on_error "Failed to set permissions for log files."

# Create virtual environment
print_status "Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv" || exit_on_error "Failed to create virtual environment."

# Install dependencies (including PyYAML for config, pillow-heif for HEIC)
print_status "Installing Python dependencies within the virtual environment..."
source "$INSTALL_DIR/venv/bin/activate" && \
  pip install --upgrade pip && \
  pip install pillow requests piexif pyyaml pillow-heif || \
  exit_on_error "Failed to install Python dependencies."

#######################################################
# Setup config directory and file
#######################################################
CONFIG_DIR="/etc/image-tagger"
check_sudo
sudo mkdir -p "$CONFIG_DIR"
sudo chown root:root "$CONFIG_DIR"
sudo chmod 755 "$CONFIG_DIR"

print_status "Creating default config file at $CONFIG_DIR/config.yml (if not existing)..."
CONFIG_FILE="$CONFIG_DIR/config.yml"

if [ ! -f "$CONFIG_FILE" ]; then
cat << 'EOF' | sudo tee "$CONFIG_FILE" >/dev/null
server: "http://127.0.0.1:11434"
model: "llama3.2-vision"
EOF
fi

# Ensure it's world-readable
check_sudo
sudo chmod 644 "$CONFIG_FILE"

#######################################################
# Create the main image-tagger script
#######################################################
print_status "Installing image-tagger script..."
cat > "$INSTALL_DIR/venv/bin/image-tagger-script.py" << 'EOL'
#!/usr/bin/env python3
import os
import sys
import argparse
import base64
import requests
import json
import logging
import io
import re
import yaml
from pathlib import Path
from PIL import Image
import piexif
from piexif import helper
from PIL.PngImagePlugin import PngInfo

# Force pillow_heif to register uppercase .HEIC / .HEIF as recognized
try:
    import pillow_heif
    # If "auto registration" doesn't catch uppercase, do it manually:
    #pillow_heif.register_heif_opener(extensions=[".heic", ".heif", ".HEIC", ".HEIF"])
except ImportError:
    pass

def load_config():
    """
    Loads server/model defaults from /etc/image-tagger/config.yml.
    If not found or invalid, returns built-in defaults.
    """
    default = {"server": "http://127.0.0.1:11434", "model": "llama3.2-vision"}
    config_path = Path("/etc/image-tagger/config.yml")
    if config_path.is_file():
        try:
            with open(config_path, 'r') as f:
                user_cfg = yaml.safe_load(f)
            if isinstance(user_cfg, dict):
                default.update(user_cfg)
        except Exception as e:
            logging.warning(f"Unable to parse config.yml: {e}")
    return default

def setup_logging(verbose=False):
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Define log format with timestamps
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # File handler
    try:
        fh = logging.FileHandler('/var/log/image-tagger.log')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except PermissionError:
        logger.error("Permission denied: Unable to write to /var/log/image-tagger.log. Please check file permissions.")
    except Exception as e:
        logger.error(f"Failed to set up file logging: {e}")

def extract_tags_from_description(description):
    """
    Extract meaningful, searchable tags from the AI-generated description.
    
    Uses regex patterns and simple keyword extraction without NLTK.
    """
    # Define stop words to exclude common words
    stop_words = {
        'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'he',
        'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 'to', 'was', 'were',
        'will', 'with', 'this', 'but', 'they', 'have', 'had', 'what', 'when',
        'where', 'who', 'which', 'why', 'could', 'would', 'should', 'there',
        'shows', 'appears', 'suggests', 'looks', 'seems', 'may', 'might', 'image',
        'picture', 'photo', 'photograph', 'visible', 'seen', 'into', 'being'
    }

    # Define regex patterns for multi-word tags
    patterns = [
        # People and groups
        r'(?:young |old )?(?:man|woman|person|people|child|kid|teen|baby|girl|boy|group)',
        
        # Physical features with specific hair colors
        r'(?:light brown|dark brown|blonde|brown|black|gray|grey|ginger|auburn) hair',
        r'(?:light|dark) (?:hair|skin)',
        r'(?:short|long|curly|straight) hair',
        r'facial hair|beard|stubble|mustache',
        
        # Clothing - capture color + item combinations
        r'(?:dark|light|blue|black|white|navy|brown|grey|gray|pink|red|green|orange|yellow|purple) (?:suit|shirt|dress|jacket|blazer|tie|pants|shorts|skirt|hat|cap|coat|hoodie)',
        r'(?:white|blue|pink|red|green) (?:collar|collared) (?:shirt|dress)',
        
        # Photo style
        r'close-up|portrait|headshot|landscape|selfie|candid|group photo|family photo',
        
        # Setting/Location
        r'(?:in|at) (?:the )?(?:office|home|beach|park|city|building|car|room|outdoor|indoor|restaurant|forest|kitchen|living room|bedroom|couch)',
        r'(?:city|beach|mountain|office|home|room|building|kitchen|living room|bedroom|yard|garden) (?:background|setting|scene)',
        
        # Actions
        r'(?:sitting|standing|walking|smiling|looking|working|holding|running|eating|drinking|reading|writing|playing|talking|watching|leaning)',
        
        # Objects
        r'(?:desk|table|chair|sofa|couch|window|door|wall|computer|phone|glass|book|bottle|remote|television|lamp|cup|plate|bowl|bag|camera)',
        
        # Expressions/Emotions
        r'(?:happy|serious|smiling|laughing|focused|professional|excited|angry|sad|relaxed|casual|formal|business|vacation)'
    ]

    tags = set()
    # 1. Apply regex patterns
    for pattern in patterns:
        matches = re.findall(pattern, description.lower())
        for match in matches:
            tag = match.strip()
            if tag and tag not in stop_words:
                tags.add(tag)

    # 2. Simple keyword extraction
    words = re.findall(r'\b\w+\b', description.lower())
    for word in words:
        if word not in stop_words and len(word) > 2:
            tags.add(word)

    # 3. Sort
    return sorted(tags)

def encode_image_to_base64(image_path):
    """Convert image to base64 string (JPEG bytes)."""
    try:
        with Image.open(image_path) as img:
            if img.mode in ('RGBA', 'LA'):
                img = img.convert('RGB')
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG')
            img_byte_arr = img_byte_arr.getvalue()
            return base64.b64encode(img_byte_arr).decode('utf-8')
    except Exception as e:
        logging.error(
            f"Error encoding image {image_path}: {str(e)}\n"
            "Make sure libheif is installed and the file is fully downloaded (not an iCloud stub)."
        )
        return None

def get_image_description(image_base64, server, model):
    """
    Get image description from Ollama API using streaming response.
    """
    headers = {'Content-Type': 'application/json'}
    
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "List all the visible elements in this image: people, "
                    "actions, clothing, objects, furniture, decorations, colors, "
                    "patterns, setting, and atmosphere. Be specific about colors, "
                    "patterns, and designs. Focus on nouns and descriptive adjectives."
                ),
                "images": [image_base64]
            }
        ]
    }
    
    try:
        response = requests.post(
            f"{server.rstrip('/')}/api/chat",
            headers=headers,
            json=payload,
            stream=True
        )
        response.raise_for_status()
        
        full_response = []
        for line in response.iter_lines():
            if line:
                try:
                    json_response = json.loads(line)
                    if 'message' in json_response and 'content' in json_response['message']:
                        content = json_response['message']['content']
                        full_response.append(content)
                except json.JSONDecodeError:
                    continue
        
        return ''.join(full_response)
                        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling Ollama API: {str(e)}")
        return None

def _save_exif_heic(img, image_path, exif_bytes):
    """
    Attempt to save the image as HEIF with updated EXIF in place.
    Returns True if successful, False if it fails.
    """
    try:
        img.save(str(image_path), format="HEIF", exif=exif_bytes, quality=90)
        return True
    except Exception as e:
        logging.warning(f"Error saving EXIF to HEIC: {str(e)}")
        return False

def _save_exif_jpeg(img, new_jpg_path, exif_bytes):
    """
    Save the image as a new .jpg with updated EXIF.
    """
    try:
        img.save(str(new_jpg_path), format="JPEG", exif=exif_bytes, quality=90)
        return True
    except Exception as e:
        logging.warning(f"Error saving EXIF data to fallback JPEG: {str(e)}")
        return False

def update_image_metadata(image_path, description, tags):
    """
    Update image metadata with the description/tags:
      - For PNG, use text-chunks
      - For JPEG/TIFF, normal exif
      - For HEIC, try exif if possible
      - If HEIC exif fails, fallback to .jpg
    """
    try:
        img = Image.open(image_path)
        ext_lower = image_path.suffix.lower()
        tags_str = ", ".join(tags)
        
        # If PNG, just write text-chunks
        if ext_lower == '.png':
            metadata = PngInfo()
            metadata.add_text("Description", description)
            metadata.add_text("Tags", tags_str)
            img.save(str(image_path), pnginfo=metadata)
            logging.info(f"✓ Updated metadata (PNG) for: {image_path}")
            return True
        
        # Exif-based approach
        if 'exif' not in img.info:
            logging.info(
                f"No existing EXIF data for {image_path} - only description/tags will be added."
            )
            exif_dict = {'0th': {}, 'Exif': {}, 'GPS': {}, '1st': {}, 'thumbnail': None}
        else:
            try:
                exif_dict = piexif.load(img.info['exif'])
            except Exception as e:
                logging.warning(
                    f"Could not parse EXIF for {image_path}, skipping metadata update. Error: {e}"
                )
                return False
        
        # Keep date/gps
        date_time_original = exif_dict['Exif'].get(piexif.ExifIFD.DateTimeOriginal)
        date_time_digitized = exif_dict['Exif'].get(piexif.ExifIFD.DateTimeDigitized)
        date_time = exif_dict['0th'].get(piexif.ImageIFD.DateTime)
        
        gps_lat_ref = exif_dict['GPS'].get(piexif.GPSIFD.GPSLatitudeRef)
        gps_lat = exif_dict['GPS'].get(piexif.GPSIFD.GPSLatitude)
        gps_lon_ref = exif_dict['GPS'].get(piexif.GPSIFD.GPSLongitudeRef)
        gps_lon = exif_dict['GPS'].get(piexif.GPSIFD.GPSLongitude)
        
        if date_time_original:
            exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = date_time_original
        if date_time_digitized:
            exif_dict['Exif'][piexif.ExifIFD.DateTimeDigitized] = date_time_digitized
        if date_time:
            exif_dict['0th'][piexif.ImageIFD.DateTime] = date_time
        
        if gps_lat and gps_lat_ref and gps_lon and gps_lon_ref:
            exif_dict['GPS'][piexif.GPSIFD.GPSLatitudeRef] = gps_lat_ref
            exif_dict['GPS'][piexif.GPSIFD.GPSLatitude] = gps_lat
            exif_dict['GPS'][piexif.GPSIFD.GPSLongitudeRef] = gps_lon_ref
            exif_dict['GPS'][piexif.GPSIFD.GPSLongitude] = gps_lon
        
        # Insert or update textual fields
        try:
            user_comment = helper.UserComment.dump(f"{description}\nTags: {tags_str}")
            exif_dict['Exif'][piexif.ExifIFD.UserComment] = user_comment
        except Exception:
            pass
        
        try:
            exif_dict['0th'][piexif.ImageIFD.ImageDescription] = description.encode('utf-8')
        except Exception:
            pass
        
        try:
            if '0th' not in exif_dict:
                exif_dict['0th'] = {}
            exif_dict['0th'][piexif.ImageIFD.XPKeywords] = tags_str.encode('utf-16le')
        except Exception:
            pass
        
        exif_bytes = piexif.dump(exif_dict)
        
        # Now save the updated exif
        if ext_lower in ('.heic', '.heif'):
            # Attempt to save as HEIF
            if _save_exif_heic(img, image_path, exif_bytes):
                logging.info(f"✓ Updated metadata in-place for HEIC: {image_path}")
                return True
            else:
                # fallback to .jpg
                new_jpg_path = image_path.with_suffix('.jpg')
                logging.warning(f"Writing HEIC exif failed, fallback to {new_jpg_path}")
                if _save_exif_jpeg(img, new_jpg_path, exif_bytes):
                    logging.info(
                        f"✓ Created new JPG with tags: {new_jpg_path} "
                        f"(original HEIC left untouched)."
                    )
                    return True
                else:
                    logging.error(f"Failed fallback to .jpg for {image_path}")
                    return False
        
        elif ext_lower in ('.jpg', '.jpeg', '.tif', '.tiff'):
            # Normal approach for JPEG/TIFF
            try:
                img.save(str(image_path), exif=exif_bytes)
                logging.info(f"✓ Updated metadata in-place for: {image_path}")
                return True
            except Exception as e:
                logging.warning(
                    f"Error saving EXIF data for {image_path}, fallback no-EXIF. {str(e)}"
                )
                img.save(str(image_path))
                return True
        
        else:
            # Some other format, fallback to .jpg
            logging.warning(f"{ext_lower} not supported for exif, converting to .jpg fallback.")
            new_jpg_path = image_path.with_suffix('.jpg')
            if _save_exif_jpeg(img, new_jpg_path, exif_bytes):
                logging.info(f"✓ Created new JPG with tags: {new_jpg_path}")
                return True
            else:
                logging.error(f"Could not create fallback .jpg for {image_path}")
                return False
    
    except Exception as e:
        logging.error(f"Error updating metadata for {image_path}: {str(e)}")
        return False

def process_image(image_path, server, model, quiet=False, override=False):
    """Process a single image and update its metadata."""
    if not quiet:
        logging.info(f"Processing image: {image_path}")
    
    ext_lower = image_path.suffix.lower()
    exif_based = ('.jpg', '.jpeg', '.tif', '.tiff', '.heic', '.heif')
    png_based  = ('.png',)
    
    # Skip if tags exist (and override is False)
    if not override:
        try:
            with Image.open(image_path) as img:
                if ext_lower in png_based:
                    if 'Tags' in img.info:
                        if not quiet:
                            logging.info(f"Skipping {image_path}: already has tags.")
                        return True
                elif ext_lower in exif_based:
                    if 'exif' in img.info:
                        exif_dict = piexif.load(img.info['exif'])
                        if piexif.ImageIFD.XPKeywords in exif_dict['0th']:
                            if not quiet:
                                logging.info(f"Skipping {image_path}: already has tags.")
                            return True
        except Exception as e:
            logging.debug(f"Error checking existing tags for {image_path}: {str(e)}")
    
    # Convert to base64 for AI request
    image_base64 = encode_image_to_base64(image_path)
    if not image_base64:
        return False
    
    # Ask Ollama for description
    description = get_image_description(image_base64, server, model)
    if not description:
        return False
    
    if not quiet:
        logging.info(f"Generated description:\n{description}")
    
    tags = extract_tags_from_description(description)
    if not quiet and tags:
        logging.info(f"Generated tags:\n{', '.join(tags)}")
    
    return update_image_metadata(image_path, description, tags)

def main():
    config = load_config()  # Load /etc/image-tagger/config.yml

    parser = argparse.ArgumentParser(
        description='Image-tagger v0.7 by HNB. Tag images (JPEG, PNG, HEIC, etc.) with AI-generated searchable descriptions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                     # Process all images in current directory
  %(prog)s image.jpg           # Process a single image
  %(prog)s photo.HEIC          # Process uppercase extension (if fails, fallback to .jpg)
  %(prog)s /path/to/images     # Process all images in specified directory
  %(prog)s -r /path/to/images  # Process images recursively
  %(prog)s -e http://localhost:11434 image.jpg  # Use custom Ollama endpoint
  %(prog)s -m my-custom-model image.heic        # Use custom model
  """)
    
    parser.add_argument('path', nargs='?', default='.',
                        help='Path to image or directory (default: current directory)')
    parser.add_argument('-r', '--recursive', action='store_true',
                        help='Process directories recursively')
    parser.add_argument('-e', '--endpoint', default=None,
                        help='Ollama API endpoint (override config.yml)')
    parser.add_argument('-m', '--model', default=None,
                        help='Ollama model name (override config.yml)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose output')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Minimal output')
    parser.add_argument('--override', action='store_true',
                        help='Override existing tags if present')
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    input_path = Path(args.path)
    
    # Merge CLI arguments with config file
    server = args.endpoint if args.endpoint else config.get("server", "http://127.0.0.1:11434")
    model  = args.model    if args.model    else config.get("model", "llama3.2-vision")
    
    if input_path.is_file():
        process_image(input_path, server, model, args.quiet, args.override)
    elif input_path.is_dir():
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif', '.tif', '.tiff')
        if args.recursive:
            files = input_path.rglob('*')
        else:
            files = input_path.glob('*')
        for file_path in files:
            if file_path.suffix.lower() in image_extensions:
                process_image(file_path, server, model, args.quiet, args.override)
    else:
        logging.error(f"Invalid input path: {input_path}")
        sys.exit(1)

if __name__ == "__main__":
    main()
EOL

# Make the image-tagger script executable
chmod +x "$INSTALL_DIR/venv/bin/image-tagger-script.py"

# Create wrapper script for 'image-tagger'
print_status "Creating wrapper script for 'image-tagger'..."
check_sudo
sudo bash -c "cat > /usr/local/bin/image-tagger << 'EOL'
#!/bin/bash
source '/opt/image-tagger/venv/bin/activate'
python '/opt/image-tagger/venv/bin/image-tagger-script.py' "$@"
EOL"

check_sudo
sudo chmod +x /usr/local/bin/image-tagger

#######################################################
# Create "image-search" utility to locate images by
# searching metadata (Description + Tags).
#######################################################
print_status "Installing image-search script..."
cat > "$INSTALL_DIR/venv/bin/image-search.py" << 'EOL'
#!/usr/bin/env python3
import os
import sys
import argparse
import logging
from pathlib import Path
from PIL import Image
import piexif
import re
from PIL.PngImagePlugin import PngInfo

# Force pillow_heif to register uppercase .HEIC / .HEIF
try:
    import pillow_heif
    #pillow_heif.register_heif_opener(extensions=[".heic", ".heif", ".HEIC", ".HEIF"])
except ImportError:
    pass

def setup_logging(verbose=False):
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Define log format with timestamps
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # File handler
    try:
        fh = logging.FileHandler('/var/log/image-search.log')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except PermissionError:
        logger.error("Permission denied: Unable to write to /var/log/image-search.log. Check file permissions.")
    except Exception as e:
        logger.error(f"Failed to set up file logging: {e}")

def get_metadata_text(image_path):
    """
    Retrieve textual metadata from the image (Description + Tags).
    For PNG: stored in text chunks.
    For JPEG/TIFF/HEIC: stored in EXIF (ImageDescription, UserComment, XPKeywords).
    """
    try:
        with Image.open(image_path) as img:
            metadata_parts = []
            
            ext_lower = image_path.suffix.lower()
            if ext_lower == '.png':
                for k, v in img.info.items():
                    if isinstance(v, str):
                        metadata_parts.append(v.lower())
            else:
                exif_data = img.info.get('exif', None)
                if exif_data:
                    try:
                        exif_dict = piexif.load(exif_data)
                        # 0th ImageDescription
                        desc_bytes = exif_dict['0th'].get(piexif.ImageIFD.ImageDescription)
                        if desc_bytes:
                            metadata_parts.append(desc_bytes.decode('utf-8', errors='ignore').lower())
                        
                        # Exif UserComment
                        usercomment_bytes = exif_dict['Exif'].get(piexif.ExifIFD.UserComment)
                        if usercomment_bytes:
                            try:
                                from piexif.helper import UserComment
                                user_comment_str = UserComment.load(usercomment_bytes)
                                if user_comment_str:
                                    metadata_parts.append(user_comment_str.lower())
                            except Exception:
                                pass
                        
                        # XPKeywords
                        xpkeywords_bytes = exif_dict['0th'].get(piexif.ImageIFD.XPKeywords)
                        if xpkeywords_bytes:
                            try:
                                keywords_str = xpkeywords_bytes.decode('utf-16le', errors='ignore').lower()
                                metadata_parts.append(keywords_str)
                            except Exception:
                                pass
                    except Exception as e:
                        logging.debug(f"Unable to parse EXIF for {image_path}: {e}")
            return " ".join(metadata_parts)
    except Exception as e:
        logging.debug(f"Error reading metadata for {image_path}: {e}")
        return ""

def search_images(root_path, query, recursive=False):
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif', '.tif', '.tiff')
    if recursive:
        files = Path(root_path).rglob('*')
    else:
        files = Path(root_path).glob('*')
    
    matches_found = 0
    qlower = query.lower()
    
    for file_path in files:
        if file_path.suffix.lower() in image_extensions and file_path.is_file():
            text = get_metadata_text(file_path)
            if qlower in text:
                print(str(file_path))
                matches_found += 1
    
    return matches_found

def main():
    print(f"DEBUG: path={args.path}, recursive={args.recursive}")

    parser = argparse.ArgumentParser(
        description='Image-search v0.7 by HNB. Search images by metadata (Description + Tags).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""

Examples:
  image-search "table"                  # Search current dir for "table"
  image-search -r -p /path "bottle"     # Recursive search of /path for "bottle"
  image-search -p /some/dir "woman"     # Non-recursive search for "woman"
  """)
    
    parser.add_argument('query', help='Search term (case-insensitive, substring match)')
    parser.add_argument('-p', '--path', default='.',
                        help='Path to image or directory (default: current dir)')
    parser.add_argument('-r', '--recursive', action='store_true',
                        help='Search directories recursively')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose output')
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    count = search_images(args.path, args.query, args.recursive)
    logging.info(f"Found {count} match(es).")

if __name__ == "__main__":
    main()
EOL

# Make the image-search script executable
chmod +x "$INSTALL_DIR/venv/bin/image-search.py"

# Create wrapper script for 'image-search'
print_status "Creating wrapper script for 'image-search'..."
check_sudo
cat << 'EOF' | sudo tee /usr/local/bin/image-tagger > /dev/null
#!/bin/bash
source '/opt/image-tagger/venv/bin/activate'
python '/opt/image-tagger/venv/bin/image-tagger-script.py' "$@"
EOF

sudo chmod +x /usr/local/bin/image-tagger



#######################################################
# Final verification and summary
#######################################################
print_status "Verifying installation..."

# Verify image-tagger
if command -v image-tagger &> /dev/null; then
    tagger_status="${GREEN}image-tagger is installed.${NORMAL}"
else
    tagger_status="${RED}image-tagger installation failed.${NORMAL}"
fi

# Verify image-search
if command -v image-search &> /dev/null; then
    search_status="${GREEN}image-search is installed.${NORMAL}"
else
    search_status="${RED}image-search installation failed.${NORMAL}"
fi

echo -e "${tagger_status}"
echo -e "${search_status}"

if command -v image-tagger &> /dev/null && command -v image-search &> /dev/null; then
    print_status "${GREEN}Installation of Image-tagger and Image-search v0.7 by HNB successful!${NORMAL}"
    echo
    echo "Default configuration at /etc/image-tagger/config.yml"
    echo "  server: \"http://127.0.0.1:11434\""
    echo "  model:  \"llama3.2-vision\""
    echo
    echo "Important notes for uppercase .HEIC / iCloud files:"
    echo " - We force-registered .HEIC with pillow_heif."
    echo " - Make sure 'libheif' is installed, and the file is fully downloaded (not an empty placeholder)."
    echo
    echo "Usage examples for tagging (including uppercase .HEIC fallback to .jpg if fails):"
    echo "  image-tagger IMG_3433.HEIC"
    echo "  image-tagger -r /path/to/images"
    echo "  image-tagger --override photo.HEIF"
    echo
    echo "Usage examples for searching metadata (including .HEIC / .HEIF):"
    echo "  image-search \"keyboard\""
    echo "  image-search -r -p /path/to/images \"office\""
else
    print_error "Installation failed. Please check the error messages above."
    exit 1
fi
