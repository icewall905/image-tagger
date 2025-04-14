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
ollama_restart_cooldown: 60
skip_heic_errors: true
heic_conversion_quality: 90
max_retries: 5
metadata_max_retries: 5
find_similar_jpgs: true
delete_failed_conversions: false
preserve_metadata: true
create_backups: true
verify_date_preservation: true
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
import shutil
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
        "ollama_restart_cooldown": 60,  # Wait 60 seconds before restarting
        "skip_heic_errors": True,
        "max_retries": 3,
        "metadata_max_retries": 5,  # More retries for metadata operations
        "preserve_metadata": True,
        "create_backups": True,
        "verify_date_preservation": True
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
    # Clear ALL existing handlers first
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Set up basic configuration
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    
    # File handler - only add if we can create/write to the file
    try:
        file_handler = logging.FileHandler('/var/log/image-tagger.log')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except (PermissionError, IOError) as e:
        logging.warning(f"Cannot write to log file: {e}")

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
            # Provide detailed troubleshooting for HEIC files
            if 'libheif' in str(e) or 'cannot identify' in str(e):
                logging.error(
                    f"❌ Cannot process HEIC/HEIF file {image_path}:\n"
                    f"   Error: {str(e)}\n"
                    f"   This likely requires libheif installation or update:\n"
                    f"   - Ubuntu: 'apt install libheif-dev libheif-examples'\n"
                    f"   - macOS: 'brew install libheif'"
                )
            else:
                logging.error(f"❌ Cannot process HEIC/HEIF file {image_path}: {str(e)}")
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
    import time
    
    # Get configs
    config = load_config()
    cooldown_period = config.get("ollama_restart_cooldown", 60)  # Default to 60s if not specified

    headers = {'Content-Type': 'application/json'}
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Please start with a short summary description of the image. Then:\n"
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
    
    # Store the last restart time
    last_restart_time = [0]  # Using list as mutable container
    
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
    
    current_time = time.time()
    time_since_last_restart = current_time - last_restart_time[0]
    
    if thread.is_alive():
        logging.error(f"⚠️ TIMEOUT: API request timed out after {total_timeout_seconds} s. Skipping.")
        
        # Only restart if enough time has passed since the last restart
        if ollama_restart_cmd and time_since_last_restart > cooldown_period:
            logging.warning(f"⚙️ Restarting Ollama using command: '{ollama_restart_cmd}'")
            logging.info(f"Cooldown period: {cooldown_period}s. Time since last restart: {time_since_last_restart:.1f}s")
            restart_result = os.system(ollama_restart_cmd)
            if restart_result == 0:
                logging.info("✓ Ollama restart successful")
                last_restart_time[0] = current_time  # Update last restart time
            else:
                logging.error(f"❌ Failed to restart Ollama (exit code: {restart_result})")
        else:
            if ollama_restart_cmd:
                logging.info(f"Skipping Ollama restart - cooldown period active ({cooldown_period}s). "
                            f"Time since last restart: {time_since_last_restart:.1f}s")
        return None
    
    if not result["completed"] or result["error"]:
        error_msg = result["error"] if result["error"] else "Unknown error"
        logging.error(f"❌ Error calling Ollama API: {error_msg}")
        
        # Only restart if enough time has passed since the last restart
        if ollama_restart_cmd and time_since_last_restart > cooldown_period:
            logging.warning(f"⚙️ Restarting Ollama using command: '{ollama_restart_cmd}'")
            logging.info(f"Cooldown period: {cooldown_period}s. Time since last restart: {time_since_last_restart:.1f}s")
            restart_result = os.system(ollama_restart_cmd)
            if restart_result == 0:
                logging.info("✓ Ollama restart successful")
                last_restart_time[0] = current_time  # Update last restart time
            else:
                logging.error(f"❌ Failed to restart Ollama (exit code: {restart_result})")
        else:
            if ollama_restart_cmd:
                logging.info(f"Skipping Ollama restart - cooldown period active ({cooldown_period}s). "
                            f"Time since last restart: {time_since_last_restart:.1f}s")
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
    Always preserves all timestamp metadata.
    """
    # Get config for retries
    config = load_config()
    max_retries = config.get("metadata_max_retries", 5)  # More retries for metadata operations
    
    # Create backup directory if it doesn't exist
    backup_dir = ensure_backup_dir(image_path)
    backup_file = backup_dir / f"{Path(image_path).name}.metadata.json"
    
    # Create a backup of the metadata
    try:
        # Backup metadata to JSON file using exiftool
        backup_cmd = [
            "exiftool",
            "-j",
            str(image_path)
        ]
        with open(backup_file, 'w') as f:
            subprocess.run(backup_cmd, stdout=f, check=True)
        logging.debug(f"Metadata backup created at {backup_file}")
    except Exception as e:
        logging.warning(f"Failed to create metadata backup: {e}")
    
    # Get original file modification times before any changes
    try:
        orig_stat = os.stat(image_path)
        orig_atime = orig_stat.st_atime
        orig_mtime = orig_stat.st_mtime
    except Exception as e:
        logging.warning(f"Could not get original file times: {e}")
        orig_atime = None
        orig_mtime = None
    
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
            
            # Restore original modification times
            if orig_mtime and orig_atime:
                os.utime(image_path, (orig_atime, orig_mtime))
                
            logging.info(f"✓ Updated metadata (PNG) for: {image_path}")
            return True
        except Exception as e:
            logging.error(f"Error updating PNG metadata for {image_path}: {e}")
            return False

    # For JPEG, TIFF, HEIC, etc.: use exiftool with maximum metadata preservation
    for attempt in range(max_retries):
        try:
            desc_plus_tags = f"{description}\nTags: {tags_str}"
            
            # First, read all existing dates to ensure we preserve them
            date_fields = get_all_date_fields(image_path)
            
            # Build exiftool command with timestamp preservation as priority
            cmd = [
                "exiftool",
                "-P",  # Preserve file modification date/time
                "-overwrite_original",
                f"-UserComment={desc_plus_tags}",
                f"-ImageDescription={description}",
                f"-XPKeywords={tags_str}",
                "-tagsFromFile", "@",  # Copy tags from original file
                "-time:all",  # Preserve all time-related metadata
            ]
            
            # Add commands to explicitly preserve each date field
            for field, value in date_fields.items():
                if value:
                    cmd.append(f"-{field}={value}")
            
            # Add the image path at the end
            cmd.append(str(image_path))
            
            logging.debug(f"Running ExifTool: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                # Verify date metadata preservation
                if verify_date_preservation(image_path, backup_file):
                    logging.info(f"✓ Successfully updated metadata with verified date preservation: {image_path}")
                    
                    # Double-check OS-level file times
                    if orig_mtime and orig_atime:
                        os.utime(image_path, (orig_atime, orig_mtime))
                        
                    return True
                else:
                    logging.warning(f"⚠️ Date metadata verification failed, restoring from backup (attempt {attempt+1}/{max_retries})")
                    
                    # Try to restore from backup
                    restore_from_backup(image_path, backup_file)
                    
                    # Wait before retrying with increased delay
                    time.sleep(2 ** attempt)  # Exponential backoff
            else:
                err = result.stderr.strip() if result.stderr else "Unknown error"
                logging.error(f"ExifTool failed (attempt {attempt+1}/{max_retries}) for {image_path}: {err}")
                
                # Check if file was corrupted
                if not Path(image_path).exists() or os.path.getsize(image_path) == 0:
                    logging.error(f"❌ File appears corrupted after ExifTool operation: {image_path}")
                    # Try to restore from the original backup if it exists
                    original_backup = backup_dir / f"{Path(image_path).name}.original"
                    if original_backup.exists():
                        shutil.copy(str(original_backup), str(image_path))
                        logging.info(f"✓ Restored original file from backup")
                        
                        # Restore original modification times
                        if orig_mtime and orig_atime:
                            os.utime(image_path, (orig_atime, orig_mtime))
                
                # Wait before retrying with increased delay
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                
        except Exception as e:
            logging.error(f"Error running ExifTool (attempt {attempt+1}/{max_retries}) for {image_path}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
    
    # If we get here, all attempts failed
    logging.error(f"❌ Failed to update metadata after {max_retries} attempts for {image_path}")
    return False

def get_all_date_fields(image_path):
    """Get all date-related fields from an image to ensure preservation"""
    date_fields = {
        "DateTimeOriginal": None, "CreateDate": None, "ModifyDate": None,
        "GPSDateStamp": None, "DateCreated": None, "SubSecCreateDate": None,
        "SubSecDateTimeOriginal": None, "SubSecModifyDate": None,
        "FileModifyDate": None, "FileCreateDate": None
    }
    
    try:
        # Read all date fields
        cmd = ["exiftool", "-j"] + [f"-{field}" for field in date_fields.keys()] + [str(image_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                if data and isinstance(data, list) and len(data) > 0:
                    for field in date_fields.keys():
                        if field in data[0]:
                            date_fields[field] = data[0][field]
            except json.JSONDecodeError:
                logging.debug(f"Could not parse date fields JSON output")
    except Exception as e:
        logging.debug(f"Error getting date fields: {e}")
        
    return date_fields

def restore_from_backup(image_path, backup_file):
    """Attempt to restore metadata from backup JSON file"""
    if not Path(backup_file).exists():
        logging.warning(f"No backup file found at {backup_file}")
        return False
        
    try:
        # Use exiftool to restore from JSON backup
        cmd = [
            "exiftool", 
            "-j=%s" % str(backup_file),  # JSON import
            "-overwrite_original",
            "-P",  # Preserve file modification date/time
            str(image_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            logging.info(f"✓ Successfully restored metadata from backup")
            return True
        else:
            err = result.stderr.strip() if result.stderr else "Unknown error"
            logging.error(f"Failed to restore metadata from backup: {err}")
            return False
    except Exception as e:
        logging.error(f"Error restoring from backup: {e}")
        return False

# Enhance date verification to check more date fields
def verify_date_preservation(image_path, backup_file):
    """Verify that all date-related metadata was preserved"""
    date_fields = [
        "CreateDate", "DateTimeOriginal", "ModifyDate", 
        "GPSDateStamp", "DateCreated", "SubSecCreateDate",
        "SubSecDateTimeOriginal", "SubSecModifyDate"
    ]
    
    # Get original date values
    orig_dates = {}
    try:
        with open(backup_file, 'r') as f:
            backup_data = json.load(f)
            for item in backup_data:
                for field in date_fields:
                    if field in item:
                        orig_dates[field] = item[field]
    except Exception as e:
        logging.warning(f"Could not read date information from backup: {e}")
        return False
    
    # Get current date values
    current_dates = {}
    cmd = ["exiftool", "-j"] + [f"-{field}" for field in date_fields] + [str(image_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            for item in data:
                for field in date_fields:
                    if field in item:
                        current_dates[field] = item[field]
    except Exception as e:
        logging.warning(f"Could not read current date information: {e}")
        return False
    
    # Compare values
    preserved = True
    for field in orig_dates:
        if field in current_dates:
            if orig_dates[field] != current_dates[field]:
                logging.warning(f"Date field {field} changed: {orig_dates[field]} → {current_dates[field]}")
                preserved = False
        else:
            logging.warning(f"Date field {field} was lost")
            preserved = False
    
    return preserved

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
    
    # If JPG already exists, use it
    if jpg_path.exists():
        logging.info(f"✓ Found existing JPG version: {jpg_path}")
        return jpg_path
        
    # Validate HEIC file first
    valid, reason = validate_heic_file(image_path)
    if not valid:
        logging.error(f"❌ Invalid HEIC file: {reason}")
        if config.get("skip_heic_errors", True):
            return None
        raise RuntimeError(f"Invalid HEIC file: {reason}")
    
    # Platform-specific and availability-based conversion methods
    methods = []
    
    # Only add methods that are available on the system
    if 'pillow_heif' in sys.modules:
        methods.append(("pillow_heif", lambda: _convert_heic_with_pil(image_path, jpg_path)))
    
    # Check for heif-convert
    if shutil.which("heif-convert"):
        methods.append(("heif-convert", lambda: _convert_heic_with_heifconvert(image_path, jpg_path)))
    
    # Check for convert (ImageMagick)
    if shutil.which("convert"):
        methods.append(("imagemagick", lambda: _convert_heic_with_imagemagick(image_path, jpg_path)))
    
    # Check for ExifTool
    if shutil.which("exiftool"):
        methods.append(("exiftool_preview", lambda: _extract_preview_with_exiftool(image_path, jpg_path)))
    
    # Check for tifig (Linux-specific)
    if shutil.which("tifig"):
        methods.append(("tifig", lambda: _convert_heic_with_tifig(image_path, jpg_path)))
    
    # Check for ffmpeg
    if shutil.which("ffmpeg"):
        methods.append(("ffmpeg", lambda: _convert_heic_with_ffmpeg(image_path, jpg_path)))
    
    # Only add sips if on macOS
    if sys.platform == "darwin" and shutil.which("sips"):
        methods.append(("sips", lambda: _convert_heic_with_sips(image_path, jpg_path)))
    
    # Try each method with detailed error logging
    for method_name, method_func in methods:
        try:
            logging.info(f"Trying {method_name} for HEIC conversion...")
            if method_func():
                logging.info(f"✓ Converted {image_path} to {jpg_path} via {method_name}")
                return jpg_path
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            logging.warning(f"⚠️ {method_name} conversion failed: {error_msg}")
        except Exception as e:
            logging.warning(f"⚠️ {method_name} conversion failed: {str(e)}")
    
    # Look for similar JPGs as fallback
    if config.get("find_similar_jpgs", True):
        try:
            parent_dir = image_path.parent
            base_name = image_path.stem
            # Look for files that share the same prefix
            similar_jpgs = list(parent_dir.glob(f"{base_name.split('_')[0]}*.jpg"))
            if similar_jpgs:
                logging.info(f"Found similar JPG: {similar_jpgs[0]}")
                return similar_jpgs[0]
        except Exception as e:
            logging.debug(f"Error finding similar JPGs: {e}")
    
    logging.error(f"❌ All HEIC conversion methods failed for {image_path}")
    if config.get("skip_heic_errors", True):
        return None
    else:
        raise RuntimeError(f"Failed to convert HEIC file: {image_path}")

# Conversion helpers
def _convert_heic_with_pil(heic_path, jpg_path):
    with Image.open(heic_path) as heic_img:
        heic_img.save(str(jpg_path), format="JPEG", quality=90)
    # Add timestamp preservation
    subprocess.run([
        "exiftool", "-overwrite_original", 
        "-P", "-tagsFromFile", str(heic_path), 
        "-time:all", str(jpg_path)
    ], check=True, capture_output=True)
    return jpg_path.exists()

def _convert_heic_with_heifconvert(heic_path, jpg_path):
    subprocess.run(["heif-convert", str(heic_path), str(jpg_path)], check=True, capture_output=True)
    # Add timestamp preservation
    subprocess.run([
        "exiftool", "-overwrite_original", 
        "-P", "-tagsFromFile", str(heic_path), 
        "-time:all", str(jpg_path)
    ], check=True, capture_output=True)
    return jpg_path.exists()

def _convert_heic_with_imagemagick(heic_path, jpg_path):
    subprocess.run(["convert", str(heic_path), str(jpg_path)], check=True, capture_output=True)
    # Add timestamp preservation
    subprocess.run([
        "exiftool", "-overwrite_original", 
        "-P", "-tagsFromFile", str(heic_path), 
        "-time:all", str(jpg_path)
    ], check=True, capture_output=True)
    return jpg_path.exists()

# Fix the _extract_preview_with_exiftool function which appears to be incorrect in the original
def _extract_preview_with_exiftool(heic_path, jpg_path):
    subprocess.run(
        ["exiftool", "-b", "-PreviewImage", "-w", ".jpg", "-ext", "HEIC", str(heic_path)],
        check=True, capture_output=True
    )
    # Add timestamp preservation
    subprocess.run([
        "exiftool", "-overwrite_original", 
        "-P", "-tagsFromFile", str(heic_path), 
        "-time:all", str(jpg_path)
    ], check=True, capture_output=True)
    return jpg_path.exists()

def _convert_heic_with_tifig(heic_path, jpg_path):
    subprocess.run(["tifig", str(heic_path), str(jpg_path)], check=True, capture_output=True)
    # Add timestamp preservation
    subprocess.run([
        "exiftool", "-overwrite_original", 
        "-P", "-tagsFromFile", str(heic_path), 
        "-time:all", str(jpg_path)
    ], check=True, capture_output=True)
    return jpg_path.exists()

def _convert_heic_with_ffmpeg(heic_path, jpg_path):
    subprocess.run(["ffmpeg", "-i", str(heic_path), "-q:v", "2", str(jpg_path)], check=True, capture_output=True)
    # Add timestamp preservation
    subprocess.run([
        "exiftool", "-overwrite_original", 
        "-P", "-tagsFromFile", str(heic_path), 
        "-time:all", str(jpg_path)
    ], check=True, capture_output=True)
    return jpg_path.exists()

def _convert_heic_with_sips(heic_path, jpg_path):
    subprocess.run(["sips", "-s", "format", "jpeg", str(heic_path), "--out", str(jpg_path)], check=True, capture_output=True)
    # Add timestamp preservation
    subprocess.run([
        "exiftool", "-overwrite_original", 
        "-P", "-tagsFromFile", str(heic_path), 
        "-time:all", str(jpg_path)
    ], check=True, capture_output=True)
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

    # Create backup directory if it doesn't exist
    backup_dir = ensure_backup_dir(image_path)
    
    # Create full file backup before modification
    try:
        shutil.copy2(image_path, backup_dir / f"{Path(image_path).name}.original")
        logging.debug(f"Created full file backup at {backup_dir / f'{Path(image_path).name}.original'}")
    except Exception as e:
        logging.warning(f"Failed to create file backup: {e}")

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

    # Check if image already has metadata and respect the override flag
    if not override:
        check_cmd = ["exiftool", "-s", "-UserComment", "-ImageDescription", "-XPKeywords", str(image_path)]
        result = subprocess.run(check_cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            # If any metadata fields exist, skip this image
            logging.info(f"⏭️ Skipping {image_path} - already has metadata (use --override to force)")
            return True  # Return success since we're respecting the user's choice

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

    # Batching option (still useful for rate limiting even in single thread)
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
                if batch_delay > 0 and idx < total_files - 1:
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
        # No batching, simple single-threaded loop
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

def check_dependencies():
    """Verify that required external tools are available"""
    missing = []
    for cmd in ["exiftool"]:
        try:
            subprocess.run([cmd, "-ver"], capture_output=True, check=False)
        except FileNotFoundError:
            missing.append(cmd)
    
    if missing:
        logging.error(f"❌ Missing required dependencies: {', '.join(missing)}")
        logging.error("Please install them before continuing.")
        if "exiftool" in missing:
            logging.error("  - macOS: brew install exiftool")
            logging.error("  - Linux: apt install libimage-exiftool-perl")
        sys.exit(1)

def ensure_backup_dir(image_path):
    """Create and secure backup directory"""
    backup_dir = Path(image_path).parent / ".metadata_backups"
    backup_dir.mkdir(exist_ok=True)
    
    # Set appropriate permissions (only owner can access)
    try:
        # 0o700 = read/write/execute for owner only
        os.chmod(backup_dir, 0o700)
    except Exception as e:
        logging.warning(f"Could not set permissions on backup directory: {e}")
    
    return backup_dir

# Add this function to check HEIC file validity

def validate_heic_file(file_path):
    """Check if HEIC file is valid before attempting conversion"""
    try:
        # Check file size - tiny files are usually placeholder/corrupted
        file_size = os.path.getsize(file_path)
        if file_size < 20000:
            logging.warning(f"⚠️ {file_path} is likely a placeholder file ({file_size} bytes)")
            return False, f"File too small ({file_size} bytes), likely a placeholder"
        
        # Check for magic bytes
        with open(file_path, 'rb') as f:
            header = f.read(12)
            if b'ftyp' not in header:
                logging.warning(f"⚠️ {file_path} is missing expected HEIC format markers")
                hex_header = ' '.join(f'{b:02x}' for b in header)
                return False, f"Missing HEIC format markers. Header: {hex_header}"
        
        # Check if exiftool can read it
        result = subprocess.run(
            ["exiftool", "-FileType", "-S", str(file_path)],
            capture_output=True, text=True, check=False
        )
        if "HEIC" not in result.stdout and "HEIF" not in result.stdout:
            logging.warning(f"⚠️ {file_path} not recognized as HEIC/HEIF by ExifTool")
            return False, f"ExifTool validation failed: {result.stderr.strip() or 'Unknown type returned'}"
            
        return True, "File appears valid"
    except Exception as e:
        return False, f"Validation error: {str(e)}"

# Replace the argument parser section to remove the --threads option

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
                        help='Override existing tags if present')
    parser.add_argument('--batch-size', type=int, default=0,
                        help='Process files in batches of this size')
    parser.add_argument('--batch-delay', type=int, default=5,
                        help='Seconds to pause between batches')
    parser.add_argument('--dry-run', action='store_true',
                        help='Process without saving changes')

    args = parser.parse_args()
    setup_logging(args.verbose)
    input_path = Path(args.path)

    check_dependencies()

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
            args.batch_delay, 1  # Always use 1 thread
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
  image-search -p /some/dir
"""
    )
    
    parser.add_argument('query', help='Search query (case-insensitive)')
    parser.add_argument('-p', '--path', default='.', help='Path to search (default: current directory)')
    parser.add_argument('-r', '--recursive', action='store_true', help='Search directories recursively')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    root_path = Path(args.path)
    if not root_path.exists():
        logging.error(f"Invalid path: {root_path}")
        sys.exit(1)
    
    matches = search_images(root_path, args.query, args.recursive)
    if matches == 0:
        logging.info("No matches found.")
    else:
        logging.info(f"Found {matches} matches.")

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

check_sudo
sudo chmod +x /usr/local/bin/image-search

print_status "Installation complete. You can now use 'image-tagger' and 'image-search' commands."
