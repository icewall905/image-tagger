#!/usr/bin/env python3
import os
import sys
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
import hashlib
from pathlib import Path
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from datetime import datetime

# Attempt to import pillow_heif (for HEIC)
try:
    import pillow_heif
    # Register HEIF opener with Pillow
    pillow_heif.register_heif_opener()
    HEIC_SUPPORT = True
    logging.info("✅ HEIC/HEIF support enabled via pillow_heif")
except ImportError:
    HEIC_SUPPORT = False
    logging.warning("⚠️ pillow_heif not available. HEIC/HEIF files may not be processed correctly.")
    logging.warning("Install with: pip install pillow-heif")

def detect_actual_image_format(file_path):
    """
    Detect the actual image format by reading file headers, regardless of extension.
    Returns the detected format or None if not a valid image.
    """
    try:
        with Image.open(file_path) as img:
            actual_format = img.format
            if actual_format:
                return actual_format.lower()
    except Exception:
        pass
    return None

def load_config():
    """Load configuration from YAML file or return defaults."""
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    
    default_config = {
        "server": "http://127.0.0.1:11434",
        "model": "qwen2.5vl:latest",
        "max_retries": 5,
        "metadata_max_retries": 5,
        "use_file_tracking": True,
        "tracking_db_path": "/var/log/image-tagger.db",
        "process_newest_first": True,
        "enable_fallback_methods": True,
        "max_file_size_mb": 50,
        "supported_formats": ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif', '.tif', '.tiff', '.webp']
    }
    
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                file_config = yaml.safe_load(f) or {}
                default_config.update(file_config)
        except Exception as e:
            logging.warning(f"Error loading config file: {e}")
    
    return default_config

def get_file_checksum(file_path):
    """Calculate SHA256 checksum of a file."""
    try:
        with open(file_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        logging.error(f"Error calculating checksum for {file_path}: {e}")
        return None

def extract_tags_from_description(description):
    """Extract relevant tags from AI-generated description."""
    if not description:
        return []
    
    # Convert to lowercase for processing
    desc_lower = description.lower()
    
    # Common object and scene tags
    object_tags = [
        'person', 'people', 'man', 'woman', 'child', 'baby', 'animal', 'dog', 'cat', 'bird', 'fish',
        'car', 'truck', 'bike', 'bicycle', 'boat', 'plane', 'train', 'building', 'house', 'tree',
        'flower', 'mountain', 'ocean', 'lake', 'river', 'beach', 'forest', 'desert', 'city', 'street',
        'road', 'bridge', 'sky', 'cloud', 'sun', 'moon', 'star', 'night', 'day', 'sunset', 'sunrise',
        'indoor', 'outdoor', 'nature', 'urban', 'rural', 'landscape', 'portrait', 'group', 'family',
        'food', 'drink', 'furniture', 'clothing', 'shoe', 'hat', 'bag', 'phone', 'computer', 'book'
    ]
    
    # Scene and mood tags
    scene_tags = [
        'bright', 'dark', 'colorful', 'black and white', 'vintage', 'modern', 'classic', 'artistic',
        'professional', 'casual', 'formal', 'informal', 'busy', 'quiet', 'empty', 'crowded', 'peaceful',
        'chaotic', 'organized', 'messy', 'clean', 'dirty', 'new', 'old', 'worn', 'pristine'
    ]
    
    # Extract tags that appear in the description
    found_tags = []
    
    # Check for object tags
    for tag in object_tags:
        if tag in desc_lower:
            found_tags.append(tag)
    
    # Check for scene tags
    for tag in scene_tags:
        if tag in desc_lower:
            found_tags.append(tag)
    
    # Extract color mentions
    colors = ['red', 'blue', 'green', 'yellow', 'orange', 'purple', 'pink', 'brown', 'black', 'white', 'gray', 'grey']
    for color in colors:
        if color in desc_lower:
            found_tags.append(color)
    
    # Extract time of day
    time_tags = ['morning', 'afternoon', 'evening', 'night', 'dawn', 'dusk', 'midday', 'midnight']
    for time_tag in time_tags:
        if time_tag in desc_lower:
            found_tags.append(time_tag)
    
    # Extract weather conditions
    weather_tags = ['sunny', 'cloudy', 'rainy', 'snowy', 'foggy', 'stormy', 'clear', 'overcast']
    for weather_tag in weather_tags:
        if weather_tag in desc_lower:
            found_tags.append(weather_tag)
    
    # Remove duplicates and limit to reasonable number
    unique_tags = list(set(found_tags))
    return unique_tags[:15]  # Limit to 15 tags max

def encode_image_to_base64_fallback(image_path, method="pillow"):
    """
    Convert image to base64 string using different fallback methods.
    
    Args:
        image_path: Path to the image file
        method: Processing method ("pillow", "convert", "ffmpeg")
    
    Returns:
        Base64 encoded string or None on failure
    """
    try:
        if method == "pillow":
            return encode_image_to_base64_pillow(image_path)
        elif method == "convert":
            return encode_image_to_base64_convert(image_path)
        elif method == "ffmpeg":
            return encode_image_to_base64_ffmpeg(image_path)
        else:
            logging.error(f"Unknown encoding method: {method}")
            return None
    except Exception as e:
        logging.error(f"Error with {method} encoding for {image_path}: {e}")
        return None

def encode_image_to_base64_pillow(image_path):
    """Convert image to base64 using Pillow (primary method)."""
    try:
        image_path = Path(image_path)
        ext = image_path.suffix.lower()
        
        # Early validation - check if file can be opened as an image
        try:
            with Image.open(image_path) as test_img:
                actual_format = test_img.format
                if not actual_format:
                    logging.error(f"File {image_path} is not a valid image format")
                    return None
        except Exception as e:
            logging.error(f"Cannot open {image_path} as image: {e}")
            return None
        
        # Special handling for potentially problematic HEIC files
        if ext in ('.heic', '.heif'):
            if not HEIC_SUPPORT:
                logging.error(f"HEIC support not available for {image_path}")
                return None
            
            # Detect actual file format to catch misnamed files
            actual_format = detect_actual_image_format(image_path)
            if actual_format and actual_format not in ('heic', 'heif'):
                logging.warning(f"File {image_path} has .heic extension but is actually {actual_format.upper()}")
            elif not actual_format:
                logging.error(f"Invalid or corrupted HEIC file {image_path}")
                return None
        
        # Open and process the image
        with Image.open(image_path) as img:
            # Handle different color modes
            if img.mode in ('RGBA', 'LA'):
                # Convert transparency to white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[-1])
                else:  # LA mode
                    background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode == 'P':
                # Convert palette mode to RGB (fixes GIF issue)
                img = img.convert('RGB')
            elif img.mode not in ('RGB', 'L'):
                # Convert any other mode to RGB
                img = img.convert('RGB')
            
            # Resize if image is extremely large (to prevent memory issues)
            max_dimension = 2048
            if max(img.size) > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                logging.info(f"Resized large image {image_path} for processing")
            
            # Convert to JPEG bytes
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=85)
            img_byte_arr = img_byte_arr.getvalue()
            return base64.b64encode(img_byte_arr).decode('utf-8')
            
    except Exception as e:
        ext = image_path.suffix.lower()
        if ext in ('.heic', '.heif'):
            logging.error(f"HEIC format error with {image_path}: {e}")
            logging.error(f"Try installing pillow-heif: pip install pillow-heif")
        else:
            logging.error(f"Error encoding image {image_path}: {e}")
        return None

def encode_image_to_base64_convert(image_path):
    """Convert image to base64 using ImageMagick convert command."""
    try:
        # Use ImageMagick convert to resize and convert to JPEG
        cmd = [
            "convert", str(image_path),
            "-resize", "2048x2048>",  # Resize if larger than 2048px
            "-quality", "85",
            "-format", "jpeg",
            "jpeg:-"  # Output to stdout
        ]
        
        result = subprocess.run(cmd, capture_output=True, check=True)
        if result.returncode == 0:
            return base64.b64encode(result.stdout).decode('utf-8')
        else:
            logging.error(f"ImageMagick convert failed: {result.stderr}")
            return None
            
    except subprocess.CalledProcessError as e:
        logging.error(f"ImageMagick convert error: {e}")
        return None
    except FileNotFoundError:
        logging.error("ImageMagick convert not found. Install with: apt install imagemagick")
        return None

def encode_image_to_base64_ffmpeg(image_path):
    """Convert image to base64 using FFmpeg."""
    try:
        # Use FFmpeg to convert image to JPEG
        cmd = [
            "ffmpeg", "-i", str(image_path),
            "-vf", "scale=2048:2048:force_original_aspect_ratio=decrease",
            "-q:v", "2",  # High quality
            "-f", "image2",
            "-vcodec", "mjpeg",
            "-"  # Output to stdout
        ]
        
        result = subprocess.run(cmd, capture_output=True, check=True)
        if result.returncode == 0:
            return base64.b64encode(result.stdout).decode('utf-8')
        else:
            logging.error(f"FFmpeg failed: {result.stderr}")
            return None
            
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg error: {e}")
        return None
    except FileNotFoundError:
        logging.error("FFmpeg not found. Install with: apt install ffmpeg")
        return None

def encode_image_to_base64(image_path):
    """Convert image to base64 string with multiple fallback methods."""
    config = load_config()
    enable_fallbacks = config.get("enable_fallback_methods", True)
    
    # Try primary method (Pillow)
    result = encode_image_to_base64_fallback(image_path, "pillow")
    if result:
        return result
    
    if not enable_fallbacks:
        return None
    
    # Try fallback methods
    fallback_methods = ["convert", "ffmpeg"]
    
    for method in fallback_methods:
        logging.info(f"Trying fallback method: {method} for {image_path}")
        result = encode_image_to_base64_fallback(image_path, method)
        if result:
            logging.info(f"Successfully encoded {image_path} using {method}")
            return result
    
    logging.error(f"All encoding methods failed for {image_path}")
    return None

def get_metadata_text_exiftool(file_path):
    """
    Use exiftool to extract text metadata from a file.
    Returns a lowercase string containing all text metadata
    fields concatenated together for easy searching.
    """
    try:
        cmd = ["exiftool", "-s", "-UserComment", "-ImageDescription", "-XPKeywords", str(file_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.lower()
        else:
            logging.error(f"Exiftool error: {result.stderr}")
            return ""
    except Exception as e:
        logging.error(f"Error getting metadata: {e}")
        return ""

def is_image_already_processed_in_db(image_path, db_session=None):
    """
    Check if image is already processed in the database.
    This is the primary method for deduplication.
    """
    try:
        # If no db_session provided, we can't check the database
        if db_session is None:
            return False
        
        # Check if image exists in database with a description
        from ..models import Image
        existing_image = db_session.query(Image).filter_by(path=str(image_path)).first()
        
        if existing_image:
            # Check if image is already processed
            if existing_image.is_processed:
                logging.debug(f"Image already processed in database: {image_path}")
                return True
            
            # Check if file modification time has changed (indicating file was updated)
            try:
                current_mtime = datetime.fromtimestamp(image_path.stat().st_mtime)
                if existing_image.file_modified_at and current_mtime > existing_image.file_modified_at:
                    logging.info(f"File modified since last processing: {image_path}")
                    return False  # File was modified, should reprocess
            except Exception as e:
                logging.warning(f"Could not check file modification time for {image_path}: {e}")
        
        return False
        
    except Exception as e:
        logging.error(f"Error checking database for {image_path}: {e}")
        return False

def is_file_processed(image_path):
    """Checks if a file has already been processed by checking its checksum in the database."""
    config = load_config()
    if not config.get("use_file_tracking", True):
        return False  # Skip tracking if disabled in config
        
    db_path = get_processed_db_path()
    if not db_path.exists():
        return False

    checksum = get_file_checksum(image_path)
    if not checksum:
        return False

    try:
        with open(db_path, 'r') as f:
            for line in f:
                if line.strip() == f"{image_path}:{checksum}":
                    return True
    except IOError as e:
        logging.error(f"Error reading processed file DB: {e}")
    return False

def mark_file_as_processed(image_path):
    """Adds a file and its checksum to the processed database."""
    config = load_config()
    if not config.get("use_file_tracking", True):
        return  # Skip tracking if disabled in config
        
    checksum = get_file_checksum(image_path)
    if not checksum:
        return

    db_path = get_processed_db_path()
    try:
        # Ensure directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(db_path, 'a') as f:
            f.write(f"{image_path}:{checksum}\n")
    except IOError as e:
        logging.error(f"Error writing to processed file DB: {e}")

def update_image_processing_status(image_path, status, error_message=None, db_session=None):
    """
    Update the processing status of an image in the database.
    
    Args:
        image_path: Path to the image file
        status: Processing status (pending, processing, completed, failed, skipped)
        error_message: Error message if status is failed
        db_session: Database session
    """
    try:
        if db_session is None:
            return
        
        from ..models import Image
        image = db_session.query(Image).filter_by(path=str(image_path)).first()
        
        if image:
            image.processing_status = status
            image.last_processing_attempt = datetime.utcnow()
            image.processing_attempts += 1
            
            if error_message:
                image.processing_error = error_message
            
            # Update file metadata if available
            try:
                stat = image_path.stat()
                image.file_modified_at = datetime.fromtimestamp(stat.st_mtime)
                image.file_size = stat.st_size
            except Exception as e:
                logging.warning(f"Could not update file metadata for {image_path}: {e}")
            
            db_session.commit()
            logging.debug(f"Updated processing status for {image_path}: {status}")
        
    except Exception as e:
        logging.error(f"Error updating processing status for {image_path}: {e}")
        if db_session:
            db_session.rollback()

def process_image(image_path, server, model, quiet=False, is_override=False, 
                 ollama_restart_cmd=None, restart_on_failure=False, return_data=False, db_session=None):
    """Process a single image with the vision model and update its metadata.
    
    Args:
        image_path: Path to the image file
        server: Ollama server URL (http://host:port)
        model: Model name to use (e.g., "llava" or "bakllava")
        quiet: Suppress non-error output
        is_override: Force override existing metadata
        ollama_restart_cmd: Command to restart Ollama (if needed)
        restart_on_failure: Whether to restart Ollama on certain failures
        return_data: Whether to return the description and tags instead of just True/False
        db_session: Database session for checking processing status
        
    Returns:
        If return_data is False:
            True on success, False on error, or "skipped" if skipped
        If return_data is True:
            (description, tags) tuple on success, (False, None) on error
    """
    image_path = Path(image_path)
    config = load_config()
    
    # DEBUG: Log which server is being used
    logging.info(f"🔧 DEBUG: process_image called with server={server}, model={model}")
    logging.info(f"🔧 DEBUG: config loaded server={config.get('server')}, model={config.get('model')}")
    
    try:
        max_retries = config.get("max_retries", 5)
        metadata_max_retries = config.get("metadata_max_retries", 5)
        max_file_size_mb = config.get("max_file_size_mb", 50)
        
        # Update processing status to "processing"
        update_image_processing_status(image_path, "processing", db_session=db_session)
        
        # Check file size
        try:
            file_size_mb = image_path.stat().st_size / (1024 * 1024)
            if file_size_mb > max_file_size_mb:
                error_msg = f"File too large ({file_size_mb:.1f}MB > {max_file_size_mb}MB)"
                update_image_processing_status(image_path, "failed", error_msg, db_session=db_session)
                logging.warning(f"{error_msg}: {image_path}")
                return (False, None) if return_data else False
        except Exception as e:
            error_msg = f"Error checking file size: {e}"
            update_image_processing_status(image_path, "failed", error_msg, db_session=db_session)
            logging.error(f"{error_msg} for {image_path}")
            return (False, None) if return_data else False
        
        # Check if already processed (database check first, then file tracking)
        if not is_override:
            # Primary check: database
            if is_image_already_processed_in_db(image_path, db_session):
                update_image_processing_status(image_path, "skipped", db_session=db_session)
                if not quiet:
                    logging.info(f"🔄 Skipping already processed file (database): {image_path}")
                return ("skipped", None) if return_data else "skipped"
            
            # Secondary check: file tracking
            if is_file_processed(image_path):
                update_image_processing_status(image_path, "skipped", db_session=db_session)
                if not quiet:
                    logging.info(f"🔄 Skipping already processed file (tracking): {image_path}")
                return ("skipped", None) if return_data else "skipped"
        
        # Get Base64 encoded image with fallback methods
        base64_image = encode_image_to_base64(image_path)
        if not base64_image:
            error_msg = "Failed to encode image"
            update_image_processing_status(image_path, "failed", error_msg, db_session=db_session)
            logging.error(f"❌ {error_msg}: {image_path}")
            return (False, None) if return_data else False
        
        # Call Ollama API
        for attempt in range(max_retries):
            try:
                # Check if Ollama server is available
                try:
                    # DEBUG: Log the exact server URL being used for health check
                    logging.info(f"🔧 DEBUG: Health check to server: {server}")
                    health_check = requests.get(f"{server}/api/tags", timeout=5)
                    if health_check.status_code != 200:
                        logging.error(f"Ollama server health check failed with status code: {health_check.status_code}")
                        if attempt == max_retries - 1:
                            error_msg = f"Ollama server health check failed: {health_check.status_code}"
                            update_image_processing_status(image_path, "failed", error_msg, db_session=db_session)
                            if return_data:
                                return (False, None)
                            return False
                        time.sleep(5)
                        continue
                except requests.exceptions.RequestException as e:
                    logging.error(f"Ollama server is not available: {e}")
                    if attempt == max_retries - 1:
                        error_msg = f"Ollama server not available: {e}"
                        update_image_processing_status(image_path, "failed", error_msg, db_session=db_session)
                        if return_data:
                            return (False, None)
                        return False
                    time.sleep(5)
                    continue
                
                # Create the API request payload
                payload = {
                    "model": model,
                    "prompt": "Describe this image in a single paragraph with specific details. Mention what is shown, the setting, and any notable features.",
                    "stream": False,
                    "options": {"temperature": 0.1},
                    "images": [base64_image]
                }
                
                # DEBUG: Log the exact server URL being used for generation
                logging.info(f"🔧 DEBUG: Sending generation request to server: {server}")
                response = requests.post(f"{server}/api/generate", 
                                        json=payload,
                                        timeout=300)  # Much longer timeout for vision models (5 minutes)
                
                if response.status_code == 200:
                    try:
                        response_json = response.json()
                        description = response_json.get('response', '').strip()
                        if not description:
                            raise ValueError("Empty description received")
                        
                        # Extract tags from the description
                        tags = extract_tags_from_description(description)
                        
                        if not quiet:
                            logging.info(f"✅ Generated description for {image_path}")
                            logging.info(f"📝 Description: {description}")
                            logging.info(f"🏷️ Tags: {', '.join(tags)}")
                        
                        # Update image metadata
                        result = update_image_metadata(image_path, description, tags, is_override, metadata_max_retries)
                        
                        if result:
                            mark_file_as_processed(image_path)
                            update_image_processing_status(image_path, "completed", db_session=db_session)
                            if return_data:
                                return (description, tags)
                            return True
                        else:
                            error_msg = "Failed to update metadata"
                            update_image_processing_status(image_path, "failed", error_msg, db_session=db_session)
                            logging.error(f"❌ {error_msg} for {image_path}")
                            if return_data:
                                return (False, None)
                            return False
                            
                    except Exception as e:
                        logging.error(f"Error processing API response: {e}")
                        time.sleep(2)  # Brief pause before retry
                else:
                    error_msg = f"API error (HTTP {response.status_code})"
                    try:
                        error_json = response.json()
                        if 'error' in error_json:
                            error_msg = f"API error: {error_json['error']}"
                    except:
                        pass
                    
                    logging.error(f"{error_msg} for {image_path}")
                    
                    # Check for specific errors that might warrant an Ollama restart
                    if restart_on_failure and ollama_restart_cmd:
                        if response.status_code in (500, 503) or "out of memory" in error_msg.lower():
                            logging.warning(f"Critical API error. Attempting to restart Ollama...")
                            try:
                                subprocess.run(ollama_restart_cmd, shell=True, check=True)
                                logging.info(f"Ollama restart requested. Waiting 30 seconds...")
                                time.sleep(30)  # Wait for Ollama to restart
                            except Exception as e:
                                logging.error(f"Failed to restart Ollama: {e}")
                    
                    time.sleep(3)  # Longer pause on API errors
            
            except requests.exceptions.RequestException as e:
                logging.error(f"Request error on attempt {attempt+1}/{max_retries}: {e}")
                time.sleep(5)  # Even longer pause on connection errors
        
        error_msg = f"Failed after {max_retries} attempts"
        update_image_processing_status(image_path, "failed", error_msg, db_session=db_session)
        logging.error(f"❌ {error_msg} for {image_path}")
        return (False, None) if return_data else False
        
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        update_image_processing_status(image_path, "failed", error_msg, db_session=db_session)
        logging.error(f"❌ {error_msg} processing {image_path}")
        return (False, None) if return_data else False

def process_directory(input_path, server, model, recursive=True, quiet=False, 
                    override=False, ollama_restart_cmd=None, batch_size=0, 
                    batch_delay=5, threads=1, restart_on_failure=False, return_data=False):
    """
    Process all images in a directory, tagging them with AI-generated descriptions.
    
    Args:
        input_path: Directory containing images
        server: Ollama server URL (http://host:port)
        model: Model name to use (e.g., "llava")
        recursive: Whether to recurse into subdirectories
        quiet: Suppress non-error output
        override: Force override existing metadata
        ollama_restart_cmd: Command to restart Ollama if needed
        batch_size: Process images in batches of this size (0 = no batching)
        batch_delay: Seconds to pause between batches
        threads: Number of threads to use (currently ignored)
        restart_on_failure: Whether to restart Ollama on certain failures
        return_data: Whether to return descriptions and tags
        
    Returns:
        If return_data is False:
            Dictionary with counts of successes, skips, and errors
        If return_data is True:
            List of (path, description, tags) tuples for successfully processed images
    """
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif', '.tif', '.tiff')
    input_path = Path(input_path)

    # Collect all target files
    if recursive:
        all_files = list(input_path.rglob('*'))
    else:
        all_files = list(input_path.glob('*'))
        
    image_files = [f for f in all_files if f.suffix.lower() in image_extensions and f.is_file()]
    total_files = len(image_files)
    logging.info(f"Found {total_files} image files to process.")
    
    # Sort files by modification time, newest first
    image_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    logging.info("Files sorted by modification time, processing newest first")

    success_count = 0
    skip_count = 0
    tracked_skip_count = 0  # Count files skipped due to tracking DB
    error_count = 0
    
    results = [] if return_data else None

    # Batching option (still useful for rate limiting even in single thread)
    if batch_size > 0:
        batch_files = []
        batch_num = 1
        for idx, file_path in enumerate(image_files):
            batch_files.append(file_path)
            if len(batch_files) >= batch_size:
                logging.info(f"Processing batch {batch_num}...")
                for bf in batch_files:
                    if return_data:
                        result, tags = process_image(bf, server, model, quiet, override, 
                                                   ollama_restart_cmd, restart_on_failure, 
                                                   return_data=True)
                        if result is True:
                            success_count += 1
                            if results is not None:
                                results.append((bf, result, tags))
                        elif result == "skipped":
                            skip_count += 1
                        else:
                            error_count += 1
                    else:
                        ok = process_image(bf, server, model, quiet, override, 
                                         ollama_restart_cmd, restart_on_failure)
                        if ok is True:
                            success_count += 1
                        elif ok == "skipped":
                            skip_count += 1
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
                if return_data:
                    result, tags = process_image(bf, server, model, quiet, override, 
                                               ollama_restart_cmd, restart_on_failure, 
                                               return_data=True)
                    if result is True:
                        success_count += 1
                        if results is not None:
                            results.append((bf, result, tags))
                    elif result == "skipped":
                        skip_count += 1
                    else:
                        error_count += 1
                else:
                    ok = process_image(bf, server, model, quiet, override, 
                                     ollama_restart_cmd, restart_on_failure)
                    if ok is True:
                        success_count += 1
                    elif ok == "skipped":
                        skip_count += 1
                    else:
                        error_count += 1
    else:
        # Process without batching
        for file_path in image_files:
            if return_data:
                result, tags = process_image(file_path, server, model, quiet, override, 
                                           ollama_restart_cmd, restart_on_failure, 
                                           return_data=True)
                if result is True:
                    success_count += 1
                    if results is not None:
                        results.append((file_path, result, tags))
                elif result == "skipped":
                    skip_count += 1
                else:
                    error_count += 1
            else:
                ok = process_image(file_path, server, model, quiet, override, 
                                 ollama_restart_cmd, restart_on_failure)
                if ok is True:
                    success_count += 1
                elif ok == "skipped":
                    skip_count += 1
                else:
                    error_count += 1

    logging.info(f"Processing complete: {success_count} tagged, {skip_count} skipped, {error_count} errors")
    
    if return_data:
        return results
    else:
        return {
            "success_count": success_count,
            "skip_count": skip_count,
            "error_count": error_count,
            "total_files": total_files
        }

def search_images(root_path, query, recursive=False):
    """
    Search images in a directory for metadata containing the query string.
    
    Args:
        root_path: Directory to search in
        query: Text to search for in image metadata
        recursive: Whether to search subdirectories
        
    Returns:
        List of file paths that match the query
    """
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif', '.tif', '.tiff')
    root_path = Path(root_path)
    
    if recursive:
        files = root_path.rglob('*')
    else:
        files = root_path.glob('*')
    
    matches = []
    qlower = query.lower()
    
    for file_path in files:
        if file_path.suffix.lower() in image_extensions and file_path.is_file():
            # Grab the text fields via exiftool
            metadata_str = get_metadata_text_exiftool(file_path)
            if qlower in metadata_str:
                matches.append(str(file_path))
    
    return matches

# The following functions implement file tracking and metadata updating
def get_processed_db_path():
    """Returns the path to the processed files database from config."""
    config = load_config()
    return Path(config.get("tracking_db_path", "/var/log/image-tagger.db"))

def update_image_metadata(image_path, description, tags, is_override, max_retries):
    """Update image metadata with description and tags using exiftool."""
    image_path = Path(image_path)
    
    # Detect actual file format regardless of extension
    actual_format = detect_actual_image_format(image_path)
    file_extension = image_path.suffix.lower()
    
    # Log format detection for debugging
    if actual_format and actual_format != file_extension.lstrip('.'):
        logging.info(f"📝 File {image_path} has {file_extension} extension but is actually {actual_format.upper()}")
    
    for attempt in range(max_retries):
        try:
            # Prepare exiftool command
            cmd = ["exiftool", "-overwrite_original"]
            
            # Add description
            if description:
                cmd.extend([f"-ImageDescription={description}"])
                
            # Add tags as keywords
            if tags:
                for tag in tags:
                    cmd.extend([f"-Keywords+={tag}"])
            
            # Add the file path
            cmd.append(str(image_path))
            
            # Execute the command
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logging.info(f"✅ Updated metadata for: {image_path}")
                return True
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logging.error(f"❌ exiftool failed (attempt {attempt + 1}/{max_retries}): {error_msg}")
                
                # If it's a PNG file that's actually a JPEG, try with JPEG format
                if (file_extension == '.png' and actual_format == 'jpeg' and 
                    'Not a valid PNG' in error_msg and 'looks more like a JPEG' in error_msg):
                    logging.info(f"🔄 Retrying with JPEG format for {image_path}")
                    # Try again with explicit JPEG format
                    jpeg_cmd = ["exiftool", "-overwrite_original", "-FileType=JPEG"]
                    if description:
                        jpeg_cmd.extend([f"-ImageDescription={description}"])
                    if tags:
                        for tag in tags:
                            jpeg_cmd.extend([f"-Keywords+={tag}"])
                    jpeg_cmd.append(str(image_path))
                    
                    jpeg_result = subprocess.run(jpeg_cmd, capture_output=True, text=True)
                    if jpeg_result.returncode == 0:
                        logging.info(f"✅ Updated metadata for JPEG file with PNG extension: {image_path}")
                        return True
                    else:
                        jpeg_error = jpeg_result.stderr.strip() if jpeg_result.stderr else "Unknown error"
                        logging.error(f"❌ JPEG format retry failed: {jpeg_error}")
                
                if attempt < max_retries - 1:
                    time.sleep(1)  # Wait before retry
                    
        except subprocess.SubprocessError as e:
            logging.error(f"❌ Subprocess error updating metadata (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)  # Wait before retry
        except Exception as e:
            logging.error(f"❌ Unexpected error updating metadata (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)  # Wait before retry
    
    logging.error(f"❌ Failed to update metadata after {max_retries} attempts: {image_path}")
    return False

# --- CLI/Utility Functions ---
def clean_processed_db():
    """Remove entries for files that no longer exist from the tracking database."""
    db_path = get_processed_db_path()
    if not db_path.exists():
        logging.info("No tracking database found to clean.")
        return 0
    try:
        # Read all entries
        with open(db_path, 'r') as f:
            entries = f.readlines()
        # Filter to keep only entries for files that still exist
        valid_entries = []
        removed_count = 0
        for entry in entries:
            parts = entry.strip().split(':', 1)
            if len(parts) != 2:
                continue
            file_path = parts[0]
            if Path(file_path).exists():
                valid_entries.append(entry)
            else:
                removed_count += 1
        # Write back only valid entries
        with open(db_path, 'w') as f:
            f.writelines(valid_entries)
        return removed_count
    except Exception as e:
        logging.error(f"Error cleaning tracking database: {e}")
        return -1

def check_dependencies():
    """Verify that required external tools are available."""
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
