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
    brew install python@3.13 libheif exiftool || exit_on_error "Failed to install dependencies via Homebrew."
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    print_status "Detected Linux system (assuming Debian/Ubuntu)"
    print_status "Installing dependencies..."
    check_sudo
    sudo apt-get update || exit_on_error "Failed to update package lists."
    sudo apt-get install -y python3-pip python3-venv libheif-dev libheif-examples \
         imagemagick libimage-exiftool-perl ffmpeg || exit_on_error "Failed to install dependencies."
    print_status "Attempting to install tifig (specialized HEIF converter)..."
    if command -v snap &> /dev/null; then
        sudo snap install tifig || print_warning "Couldn't install tifig via snap, continuing anyway"
    else
        print_warning "Snap not available, skipping tifig installation"
    fi
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
  pip install pillow requests pyyaml pillow-heif piexif || \
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
ollama_restart_cmd: "docker restart ollama"
skip_heic_errors: true
heic_conversion_quality: 90
max_retries: 3
find_similar_jpgs: true
delete_failed_conversions: false
EOF
fi

# Ensure it's world-readable
check_sudo
sudo chmod 644 "$CONFIG_FILE"

#######################################################
# Create the main image-tagger script (Python)
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
import subprocess
import time
from pathlib import Path
from PIL import Image
from PIL.PngImagePlugin import PngInfo

# Attempt to import pillow_heif (for HEIC)
try:
    import pillow_heif
except ImportError:
    pass

def load_config():
    """
    Loads server/model defaults from /etc/image-tagger/config.yml.
    If not found or invalid, returns built-in defaults.
    """
    default = {
        "server": "http://127.0.0.1:11434",
        "model": "granite3.2-vision",
        "ollama_restart_cmd": "docker restart ollama",
        "skip_heic_errors": True,
        "max_retries": 3
    }
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
    logging.getLogger().handlers = []
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger()
    
    # Remove all existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    # Reset root logger
    logging.root.handlers = []
    
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
        logger.warning("Permission denied: Unable to write to /var/log/image-tagger.log. Logging to console only.")
    except Exception as e:
        logger.warning(f"Failed to set up file logging: {e}")

def extract_tags_from_description(description):
    """
    Extract meaningful, searchable tags from the AI-generated description.
    Uses regex patterns and simple keyword extraction (no NLTK).
    """
    stop_words = {
        'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'he',
        'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 'to', 'was', 'were',
        'will', 'with', 'this', 'but', 'they', 'have', 'had', 'what', 'when',
        'where', 'who', 'which', 'why', 'could', 'would', 'should', 'there',
        'shows', 'appears', 'suggests', 'looks', 'seems', 'may', 'might', 'image',
        'picture', 'photo', 'photograph', 'visible', 'seen', 'into', 'being'
    }

    patterns = [
        r'(?:young |old )?(?:man|woman|person|people|child|kid|teen|baby|girl|boy|group)',
        r'(?:light brown|dark brown|blonde|brown|black|gray|grey|ginger|auburn) hair',
        r'(?:light|dark) (?:hair|skin)',
        r'(?:short|long|curly|straight) hair',
        r'facial hair|beard|stubble|mustache',
        r'(?:dark|light|blue|black|white|navy|brown|grey|gray|pink|red|green|orange|yellow|purple) (?:suit|shirt|dress|jacket|blazer|tie|pants|shorts|skirt|hat|cap|coat|hoodie)',
        r'(?:white|blue|pink|red|green) (?:collar|collared) (?:shirt|dress)',
        r'close-up|portrait|headshot|landscape|selfie|candid|group photo|family photo',
        r'(?:in|at) (?:the )?(?:office|home|beach|park|city|building|car|room|outdoor|indoor|restaurant|forest|kitchen|living room|bedroom|couch)',
        r'(?:city|beach|mountain|office|home|room|building|kitchen|living room|bedroom|yard|garden) (?:background|setting|scene)',
        r'(?:sitting|standing|walking|smiling|looking|working|holding|running|eating|drinking|reading|writing|playing|talking|watching|leaning)',
        r'(?:desk|table|chair|sofa|couch|window|door|wall|computer|phone|glass|book|bottle|remote|television|lamp|cup|plate|bowl|bag|camera)',
        r'(?:happy|serious|smiling|laughing|focused|professional|excited|angry|sad|relaxed|casual|formal|business|vacation)'
    ]

    tags = set()
    for pattern in patterns:
        matches = re.findall(pattern, description.lower())
        for match in matches:
            tag = match.strip()
            if tag and tag not in stop_words:
                tags.add(tag)

    words = re.findall(r'\b\w+\b', description.lower())
    for word in words:
        if word not in stop_words and len(word) > 2:
            tags.add(word)

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
        ext = image_path.suffix.lower()
        if ext in ('.heic', '.heif'):
            logging.error(
                f"❌ Cannot process HEIC/HEIF file {image_path}: {str(e)}\n"
                f"   This may be due to missing libheif library or an incomplete/stub file.\n"
                f"   Try: macOS: 'brew install libheif', Linux: 'apt install libheif-dev'"
            )
        else:
            logging.error(f"❌ Error encoding image {image_path}: {str(e)}")
        return None

def get_image_description(image_base64, server, model, ollama_restart_cmd=None, max_retries=3):
    """Get image description with automatic retries."""
    retries = 0
    while retries < max_retries:
        try:
            description = _get_image_description_inner(image_base64, server, model, ollama_restart_cmd)
            if description:
                return description
            
            # If we got None but no exception, increment retry counter
            retries += 1
            if retries < max_retries:
                logging.warning(f"Retrying API call ({retries}/{max_retries})...")
                time.sleep(5)  # Wait 5 seconds
        except Exception as e:
            logging.error(f"Error in API call: {e}")
            retries += 1
            if retries < max_retries:
                logging.warning(f"Retrying API call ({retries}/{max_retries})...")
                time.sleep(5)
    
    logging.error(f"Failed to get description after {max_retries} attempts")
    return None

def _get_image_description_inner(image_base64, server, model, ollama_restart_cmd=None):
    """
    Get image description from Ollama API using streaming response.
    If stuck or times out, optionally restart Ollama and return None (skip).
    """
    import threading

    headers = {'Content-Type': 'application/json'}
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "List all the visible elements in this image: people, "
                    "actions, clothing, objects, furniture, decorations, colors, "
                    "patterns, and designs. Focus on nouns and descriptive adjectives."
                ),
                "images": [image_base64]
            }
        ]
    }
    
    # Overall request timeout in seconds
    total_timeout_seconds = 300
    result = {"text": None, "completed": False, "error": None}
    
    def process_stream():
        try:
            logging.debug(f"Starting API request to {server} for model {model}")
            session = requests.Session()
            response = session.post(
                f"{server.rstrip('/')}/api/chat",
                headers=headers,
                json=payload,
                stream=True,
                timeout=(10, 30)  # (connect timeout, read timeout)
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
            
            result["text"] = ''.join(full_response)
            result["completed"] = True
            
        except requests.exceptions.Timeout as e:
            result["error"] = f"Timeout error: {str(e)}"
        except requests.exceptions.ConnectionError as e:
            result["error"] = f"Connection error: {str(e)}"
        except requests.exceptions.HTTPError as e:
            result["error"] = f"HTTP error: {str(e)}"
        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)}"
    
    thread = threading.Thread(target=process_stream)
    thread.daemon = True
    thread.start()
    
    thread.join(timeout=total_timeout_seconds)
    
    if thread.is_alive():
        logging.error(f"⚠️ TIMEOUT: API request timed out after {total_timeout_seconds} s. Skipping.")
        if ollama_restart_cmd:
            logging.warning(f"⚙️ Restarting Ollama using command: '{ollama_restart_cmd}'")
            restart_result = os.system(ollama_restart_cmd)
            if restart_result == 0:
                logging.info("✓ Ollama restart successful")
            else:
                logging.error(f"❌ Failed to restart Ollama (exit code: {restart_result})")
        return None
    
    if not result["completed"] or result["error"]:
        error_msg = result["error"] if result["error"] else "Unknown error"
        logging.error(f"❌ Error calling Ollama API: {error_msg}")
        if ollama_restart_cmd:
            logging.warning(f"⚙️ Restarting Ollama using command: '{ollama_restart_cmd}'")
            restart_result = os.system(ollama_restart_cmd)
            if restart_result == 0:
                logging.info("✓ Ollama restart successful")
            else:
                logging.error(f"❌ Failed to restart Ollama (exit code: {restart_result})")
        return None
    
    return result["text"]

#############################################
#          REPLACED WITH EXIFTOOL
#############################################
def update_image_metadata(image_path, description, tags):
    """
    Update image metadata with ExifTool (in-place for JPEG/TIFF/HEIC).
      - For PNG, still use text-chunks
      - For everything else, we call exiftool to preserve all existing EXIF data
        but insert new fields for:
          * ImageDescription
          * UserComment
          * XPKeywords
    """
    ext_lower = image_path.suffix.lower()
    tags_str = ", ".join(tags)

    # PNG: store "Description" and "Tags" in text-chunks
    if ext_lower == '.png':
        try:
            img = Image.open(image_path)
            metadata = PngInfo()
            metadata.add_text("Description", description)
            metadata.add_text("Tags", tags_str)
            img.save(str(image_path), pnginfo=metadata)
            logging.info(f"✓ Updated metadata (PNG) for: {image_path}")
            return True
        except Exception as e:
            logging.error(f"Error updating PNG metadata for {image_path}: {e}")
            return False

    # For JPEG, TIFF, HEIC, etc.: use exiftool
    # One-liner exiftool call that sets:
    #   - UserComment
    #   - ImageDescription
    #   - XPKeywords (semicolon-delimited or commas, up to you)
    # Overwrite original, preserving everything else.
    try:
        # Some systems prefer semicolons for XPKeywords.
        # We'll do commas here, but you can do: tags_str_semicolon = "; ".join(tags).
        desc_plus_tags = f"{description}\nTags: {tags_str}"

        cmd = [
            "exiftool",
            "-overwrite_original",
            f"-UserComment={desc_plus_tags}",
            f"-ImageDescription={description}",
            f"-XPKeywords={tags_str}",
            str(image_path)
        ]
        logging.debug(f"Running ExifTool: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0:
            logging.info(f"✓ Successfully updated metadata (ExifTool) for: {image_path}")
            return True
        else:
            err = result.stderr.decode('utf-8', errors='ignore')
            logging.error(f"ExifTool failed for {image_path}: {err}")
            return False
    except Exception as e:
        logging.error(f"Error running ExifTool for {image_path}: {str(e)}")
        return False


def check_file_integrity(file_path):
    """Check if a file is readable and valid. (Optional)"""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(12)
            if file_path.suffix.lower() in ('.heic', '.heif'):
                return len(header) >= 12 and (b'ftyp' in header)
            return len(header) > 0
    except Exception as e:
        logging.debug(f"File integrity check failed for {file_path}: {e}")
        return False

def process_heic_file(image_path, config=None):
    """
    Attempt HEIC -> JPG conversions if we can't open directly.
    Returns path to the newly created (or existing) .jpg if success, else None.
    """
    if config is None:
        config = load_config()
    logging.info(f"🔄 Attempting to convert HEIC file: {image_path}")
    jpg_path = image_path.with_suffix('.jpg')
    if jpg_path.exists():
        logging.info(f"✓ Found existing JPG version: {jpg_path}")
        return jpg_path
    try:
        file_size = image_path.stat().st_size
        if file_size < 20000:
            logging.warning(f"⚠️ {image_path} appears to be a placeholder file ({file_size} bytes)")
            return None
    except Exception as e:
        logging.debug(f"Error checking file size: {e}")

    methods = [
        ("pillow_heif", lambda: _convert_heic_with_pil(image_path, jpg_path)),
        ("heif-convert", lambda: _convert_heic_with_heifconvert(image_path, jpg_path)),
        ("imagemagick", lambda: _convert_heic_with_imagemagick(image_path, jpg_path)),
        ("exiftool_preview", lambda: _extract_preview_with_exiftool(image_path, jpg_path)),
        ("tifig", lambda: _convert_heic_with_tifig(image_path, jpg_path)),
        ("ffmpeg", lambda: _convert_heic_with_ffmpeg(image_path, jpg_path)),
        ("sips", lambda: _convert_heic_with_sips(image_path, jpg_path)),
    ]

    for method_name, method_func in methods:
        try:
            logging.info(f"Trying {method_name} for HEIC conversion...")
            if method_func():
                logging.info(f"✓ Converted {image_path} to {jpg_path} via {method_name}")
                return jpg_path
        except Exception as e:
            logging.warning(f"⚠️ {method_name} conversion failed: {e}")

    # Attempt to guess a similar JPG if user has duplicates
    try:
        parent_dir = image_path.parent
        base_name = image_path.stem
        similar_jpgs = list(parent_dir.glob(f"{base_name.split('_')[0]}*.jpg"))
        if similar_jpgs:
            logging.info(f"Found similar JPG: {similar_jpgs[0]}")
            return similar_jpgs[0]
    except Exception as e:
        logging.debug(f"Error finding similar JPGs: {e}")

    logging.error(f"❌ All HEIC conversion methods failed for {image_path}")
    if config.get("skip_heic_errors", True):
        logging.warning("Skipping HEIC file due to conversion failure (skip_heic_errors=True)")
        return None
    else:
        raise RuntimeError(f"Failed to convert HEIC file: {image_path}")

# Conversion helpers
def _convert_heic_with_pil(heic_path, jpg_path):
    with Image.open(heic_path) as heic_img:
        heic_img.save(str(jpg_path), format="JPEG", quality=90)
    return jpg_path.exists()

def _convert_heic_with_heifconvert(heic_path, jpg_path):
    subprocess.run(["heif-convert", str(heic_path), str(jpg_path)], check=True, capture_output=True)
    return jpg_path.exists()

def _convert_heic_with_imagemagick(heic_path, jpg_path):
    subprocess.run(["convert", str(heic_path), str(jpg_path)], check=True, capture_output=True)
    return jpg_path.exists()

def _extract_preview_with_exiftool(heic_path, jpg_path):
    """
    Attempt to extract an embedded JPG preview from the HEIC via exiftool:
      exiftool -b -PreviewImage -w .jpg -ext HEIC file.heic
    """
    subprocess.run(
        ["exiftool", "-b", "-PreviewImage", "-w", ".jpg", "-ext", "HEIC", str(heic_path)],
        check=True, capture_output=True
    )
    return jpg_path.exists()

def _convert_heic_with_tifig(heic_path, jpg_path):
    subprocess.run(["tifig", str(heic_path), str(jpg_path)], check=True, capture_output=True)
    return jpg_path.exists()

def _convert_heic_with_ffmpeg(heic_path, jpg_path):
    subprocess.run(["ffmpeg", "-i", str(heic_path), "-q:v", "2", str(jpg_path)], check=True, capture_output=True)
    return jpg_path.exists()

def _convert_heic_with_sips(heic_path, jpg_path):
    subprocess.run(["sips", "-s", "format", "jpeg", str(heic_path), "--out", str(jpg_path)], check=True, capture_output=True)
    return jpg_path.exists()

def verify_image_tags(image_path):
    """Optional verification method, not strictly needed."""
    try:
        with Image.open(image_path) as img:
            # For a robust check, we could call exiftool, but omitted for brevity
            return True
    except:
        return False

def process_image(image_path, server, model, quiet=False, override=False, ollama_restart_cmd=None):
    if not quiet:
        logging.info(f"🔍 Processing image: {image_path}")
    ext_lower = image_path.suffix.lower()

    # For HEIC, if we can't open it, do a conversion first
    if ext_lower in ('.heic', '.heif'):
        try:
            with Image.open(image_path) as img:
                pass  # if this works, we can continue
        except Exception as e:
            # try to convert
            jpg_path = process_heic_file(image_path)
            if jpg_path:
                logging.info(f"🔄 Continuing with converted JPG: {jpg_path}")
                return process_image(jpg_path, server, model, quiet, override, ollama_restart_cmd)
            else:
                logging.error(f"❌ Could not process HEIC file {image_path}")
                return False

    # Check existing tags if override == False (Skipped here, but you can adapt)
    # We no longer rely on piexif to check if XPKeywords exist. Instead you could:
    #   exiftool -XPKeywords image.jpg
    # ... but for brevity, we won't replicate that exact logic.

    image_base64 = encode_image_to_base64(image_path)
    if not image_base64:
        return False
    
    # Ask Ollama for description
    logging.info(f"🤖 Generating AI description for {image_path}...")
    description = get_image_description(
        image_base64, server, model,
        ollama_restart_cmd=ollama_restart_cmd
    )
    if not description:
        logging.warning(f"⏭️ Skipping {image_path} due to API error or timeout.")
        return False
    
    if not quiet:
        logging.info(f"📝 Generated description:\n{description}")

    tags = extract_tags_from_description(description)
    if not quiet and tags:
        logging.info(f"🏷️ Generated tags:\n{', '.join(tags)}")

    result = update_image_metadata(image_path, description, tags)
    if result:
        logging.info(f"✅ Successfully tagged: {image_path}")
    else:
        logging.error(f"❌ Failed to update metadata for: {image_path}")
    return result

def process_directory(input_path, server, model, recursive, quiet, override, ollama_restart_cmd,
                      batch_size=0, batch_delay=5, threads=1):
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif', '.tif', '.tiff')

    # Collect all target files
    if recursive:
        all_files = list(input_path.rglob('*'))
    else:
        all_files = list(input_path.glob('*'))
    image_files = [f for f in all_files if f.suffix.lower() in image_extensions and f.is_file()]
    total_files = len(image_files)
    logging.info(f"Found {total_files} image files to process.")

    success_count = 0
    skip_count = 0
    error_count = 0

    # Batching or threading as optional
    if batch_size > 0:
        batch_files = []
        batch_num = 1
        for idx, file_path in enumerate(image_files):
            batch_files.append(file_path)
            if len(batch_files) >= batch_size:
                logging.info(f"Processing batch {batch_num}...")
                for bf in batch_files:
                    ok = process_image(bf, server, model, quiet, override, ollama_restart_cmd)
                    if ok:
                        success_count += 1
                    else:
                        error_count += 1
                batch_files = []
                batch_num += 1
                if batch_delay > 0 and batch_files:
                    logging.info(f"Pausing for {batch_delay} seconds between batches...")
                    time.sleep(batch_delay)
        # leftover batch
        if batch_files:
            logging.info(f"Processing final batch...")
            for bf in batch_files:
                ok = process_image(bf, server, model, quiet, override, ollama_restart_cmd)
                if ok:
                    success_count += 1
                else:
                    error_count += 1
    else:
        # No batching
        if threads > 1:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
                futures = {}
                for file_path in image_files:
                    future = executor.submit(
                        process_image, file_path, server, model,
                        quiet, override, ollama_restart_cmd
                    )
                    futures[future] = file_path

                for future in concurrent.futures.as_completed(futures):
                    fp = futures[future]
                    try:
                        if future.result():
                            success_count += 1
                        else:
                            error_count += 1
                    except Exception as e:
                        logging.error(f"Exception processing {fp}: {e}")
                        error_count += 1
        else:
            # single-thread
            for idx, file_path in enumerate(image_files):
                if not quiet:
                    percent = (idx / total_files) * 100 if total_files > 0 else 0
                    logging.info(f"Processing file {idx+1}/{total_files} ({percent:.1f}%): {file_path}")
                ok = process_image(file_path, server, model, quiet, override, ollama_restart_cmd)
                if ok:
                    success_count += 1
                else:
                    error_count += 1

    logging.info(f"Processing complete: {success_count} successful, {skip_count} skipped, {error_count} errors")
    return success_count > 0

def main():
    config = load_config()

    parser = argparse.ArgumentParser(
        description='Image-tagger v0.9 (ExifTool version) by HNB. Tag images with AI-generated descriptions.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  image-tagger IMG_3433.HEIC
  image-tagger -r /path/to/images
  image-tagger --override photo.HEIF
"""
    )
    
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
                        help='Override existing tags if present (not fully implemented here)')
    parser.add_argument('--batch-size', type=int, default=0,
                        help='Process files in batches of this size')
    parser.add_argument('--batch-delay', type=int, default=5,
                        help='Seconds to pause between batches')
    parser.add_argument('--dry-run', action='store_true',
                        help='Process without saving changes (not fully implemented here)')
    parser.add_argument('--threads', type=int, default=1,
                        help='Number of parallel threads for processing')

    args = parser.parse_args()
    setup_logging(args.verbose)
    input_path = Path(args.path)

    # Merge CLI arguments with config
    server = args.endpoint if args.endpoint else config.get("server", "http://127.0.0.1:11434")
    model  = args.model    if args.model    else config.get("model", "llama3.2-vision")
    ollama_restart_cmd = config.get("ollama_restart_cmd", None)

    if input_path.is_file():
        process_image(input_path, server, model, args.quiet, args.override, ollama_restart_cmd)
    elif input_path.is_dir():
        process_directory(
            input_path, server, model,
            args.recursive, args.quiet, args.override,
            ollama_restart_cmd, args.batch_size,
            args.batch_delay, args.threads
        )
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
cat << 'EOF' | sudo tee /usr/local/bin/image-tagger > /dev/null
#!/bin/bash
source '/opt/image-tagger/venv/bin/activate'
python '/opt/image-tagger/venv/bin/image-tagger-script.py' "$@"
EOF

check_sudo
sudo chmod +x /usr/local/bin/image-tagger

#######################################################
# Create "image-search" utility (unchanged)
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
import re
import subprocess

# Attempt to import pillow_heif
try:
    import pillow_heif
except ImportError:
    pass

def setup_logging(verbose=False):
    logging.getLogger().handlers = []
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger()
    while logger.hasHandlers():
        logger.removeHandler(logger.handlers[0])
    logging.root.handlers = []
    logger.setLevel(level)
    
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    try:
        fh = logging.FileHandler('/var/log/image-search.log')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except PermissionError:
        logger.error("Permission denied: Unable to write to /var/log/image-search.log.")
    except Exception as e:
        logger.error(f"Failed to set up file logging: {e}")

def get_metadata_text_exiftool(image_path):
    """
    Use exiftool to get textual fields (UserComment, ImageDescription, XPKeywords).
    Return a single lowercased string for searching.
    """
    try:
        cmd = [
            "exiftool",
            "-UserComment",
            "-ImageDescription",
            "-XPKeywords",
            "-s3",
            str(image_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return result.stdout.lower()
        else:
            return ""
    except Exception as e:
        logging.debug(f"Error calling exiftool for {image_path}: {e}")
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
            # Grab the text fields via exiftool
            metadata_str = get_metadata_text_exiftool(file_path)
            if qlower in metadata_str:
                print(str(file_path))
                matches_found += 1
    
    return matches_found

def main():
    parser = argparse.ArgumentParser(
        description='Image-search v0.7 by HNB. Search images by metadata.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  image-search "table"
  image-search -r -p /path "bottle"
  image-search -p /some/dir "woman"
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
cat << 'EOF' | sudo tee /usr/local/bin/image-search > /dev/null
#!/bin/bash
source '/opt/image-tagger/venv/bin/activate'
python '/opt/image-tagger/venv/bin/image-search.py' "$@"
EOF

sudo chmod +x /usr/local/bin/image-search

#######################################################
# (Optional) HEIC-doctor remains the same
#######################################################
print_status "Creating HEIC diagnostic tool..."
cat > "$INSTALL_DIR/venv/bin/heic-doctor.py" << 'EOL'
#!/usr/bin/env python3
import argparse
import logging
import sys
from pathlib import Path
import os
import subprocess

def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s: %(message)s',
        handlers=[logging.StreamHandler()]
    )

def scan_directory(dir_path, recursive=False):
    if recursive:
        files = list(Path(dir_path).rglob("*.HEIC")) + list(Path(dir_path).rglob("*.heic")) + \
                list(Path(dir_path).rglob("*.HEIF")) + list(Path(dir_path).rglob("*.heif"))
    else:
        files = list(Path(dir_path).glob("*.HEIC")) + list(Path(dir_path).glob("*.heic")) + \
                list(Path(dir_path).glob("*.HEIF")) + list(Path(dir_path).glob("*.heif"))
    logging.info(f"Found {len(files)} HEIC/HEIF files to analyze")
    good_files = []
    corrupted_files = []
    placeholders = []
    converted_files = []
    for i, file_path in enumerate(files):
        logging.info(f"Analyzing file {i+1}/{len(files)}: {file_path}")
        result = analyze_heic(file_path)
        if result == "good":
            good_files.append(file_path)
        elif result == "corrupted":
            corrupted_files.append(file_path)
        elif result == "placeholder":
            placeholders.append(file_path)
        elif result == "converted":
            converted_files.append(file_path)
    logging.info("\n--- SUMMARY ---")
    logging.info(f"Total HEIC/HEIF files: {len(files)}")
    logging.info(f"Good files: {len(good_files)}")
    logging.info(f"Successfully converted: {len(converted_files)}")
    logging.info(f"Corrupted files: {len(corrupted_files)}")
    logging.info(f"iCloud placeholders: {len(placeholders)}")
    return {
        "total": len(files),
        "good": good_files,
        "corrupted": corrupted_files,
        "placeholders": placeholders,
        "converted": converted_files
    }

def analyze_heic(file_path):
    try:
        size = os.path.getsize(file_path)
        if size < 20000:
            logging.warning(f"⚠️ {file_path} appears to be a placeholder ({size} bytes)")
            return "placeholder"
        try:
            result = subprocess.run(
                ["exiftool", str(file_path)],
                capture_output=True,
                text=True,
                check=False
            )
            if "Error" in result.stderr or "File format error" in result.stdout:
                logging.warning(f"⚠️ {file_path} appears corrupted according to exiftool")
                return "corrupted"
        except Exception as e:
            logging.debug(f"ExifTool check failed: {e}")
        try:
            jpg_path = file_path.with_suffix('.jpg')
            subprocess.run(
                ["heif-convert", str(file_path), str(jpg_path)],
                capture_output=True,
                check=True,
                timeout=30
            )
            if jpg_path.exists():
                logging.info(f"✓ Successfully converted {file_path} to {jpg_path}")
                return "converted"
        except Exception as e:
            logging.debug(f"Conversion test failed: {e}")
        logging.warning(f"⚠️ {file_path} couldn't be converted but doesn't appear to be a placeholder")
        return "corrupted"
    except Exception as e:
        logging.error(f"❌ Error analyzing {file_path}: {e}")
        return "corrupted"

def main():
    parser = argparse.ArgumentParser(
        description='HEIC Doctor: Diagnose and fix HEIC/HEIF file issues'
    )
    parser.add_argument('path', help='Directory containing HEIC/HEIF files')
    parser.add_argument('-r', '--recursive', action='store_true',
                      help='Process directories recursively')
    parser.add_argument('-v', '--verbose', action='store_true',
                      help='Enable verbose output')
    parser.add_argument('--convert-all', action='store_true',
                      help='Try to convert all HEIC files to JPG')
    parser.add_argument('--fix', action='store_true',
                      help='Attempt to fix corrupted files')
    args = parser.parse_args()
    setup_logging(args.verbose)
    results = scan_directory(args.path, args.recursive)
    if args.convert_all:
        logging.info("\n--- CONVERTING ALL FILES ---")
        for file_path in results["good"]:
            try:
                jpg_path = file_path.with_suffix('.jpg')
                subprocess.run(
                    ["heif-convert", str(file_path), str(jpg_path)],
                    capture_output=True,
                    check=True
                )
                if jpg_path.exists():
                    logging.info(f"✓ Converted: {jpg_path}")
            except Exception as e:
                logging.error(f"❌ Failed to convert {file_path}: {e}")
    if args.fix:
        logging.info("\n--- ATTEMPTING TO FIX CORRUPTED FILES ---")
        logging.warning("This feature is experimental and may not work for all files")
        for file_path in results["corrupted"]:
            try:
                jpg_path = file_path.with_suffix('.jpg')
                subprocess.run(
                    ["exiftool", "-b", "-PreviewImage", "-w", ".jpg", str(file_path)],
                    capture_output=True,
                    check=False
                )
                if jpg_path.exists():
                    logging.info(f"✓ Extracted preview from {file_path} to {jpg_path}")
            except Exception as e:
                logging.error(f"❌ Failed to fix {file_path}: {e}")

if __name__ == "__main__":
    main()
EOL

check_sudo
sudo chmod +x "$INSTALL_DIR/venv/bin/heic-doctor.py"

print_status "Creating wrapper script for 'heic-doctor'..."
cat << 'EOF' | sudo tee /usr/local/bin/heic-doctor > /dev/null
#!/bin/bash
source '/opt/image-tagger/venv/bin/activate'
python '/opt/image-tagger/venv/bin/heic-doctor.py' "$@"
EOF

sudo chmod +x /usr/local/bin/heic-doctor

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
    print_status "${GREEN}Installation of Image-tagger (ExifTool version) and Image-search is successful!${NORMAL}"
    echo
    echo "Default configuration at /etc/image-tagger/config.yml includes Ollama server/model settings."
    echo
    echo "Now, your EXIF timestamps (including sub-second/time-zone) should remain intact, because"
    echo "ExifTool merges only your new fields (Description, UserComment, XPKeywords) and doesn't"
    echo "discard any original metadata."
else
    print_error "Installation failed. Please check error messages above."
    exit 1
fi
