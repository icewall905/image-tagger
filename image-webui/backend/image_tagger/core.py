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
        "model": "llama3.2-vision",
        "ollama_restart_cmd": "docker restart ollama",
        "ollama_restart_enabled": False,  # Disabled by default
        "ollama_restart_cooldown": 120,  # Default 2-minute cooldown
        "skip_heic_errors": True,
        "max_retries": 5,
        "metadata_max_retries": 5,  # More retries for metadata operations
        "preserve_metadata": True,
        "create_backups": True,
        "verify_date_preservation": True,
        "use_file_tracking": True,
        "tracking_db_path": "/var/log/image-tagger.db"
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

def get_file_checksum(file_path):
    """Calculates the SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            # Read and update hash in chunks of 4K
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except IOError as e:
        logging.error(f"Error reading file for checksum: {e}")
        return None

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
            logging.error(f"HEIC format error with {image_path}: {e}")
            return None
        else:
            logging.error(f"Error encoding image {image_path}: {e}")
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

def process_image(image_path, server, model, quiet=False, is_override=False, 
                 ollama_restart_cmd=None, restart_on_failure=False, return_data=False):
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
        
    Returns:
        If return_data is False:
            True on success, False on error, or "skipped" if skipped
        If return_data is True:
            (description, tags) tuple on success, (False, None) on error
    """
    image_path = Path(image_path)
    config = load_config()
    
    try:
        max_retries = config.get("max_retries", 5)
        metadata_max_retries = config.get("metadata_max_retries", 5)
        
        # Skip files that have already been processed (unless override)
        if not is_override and is_file_processed(image_path):
            if not quiet:
                logging.info(f"🔄 Skipping already processed file: {image_path}")
            return ("skipped", None) if return_data else "skipped"
        
        # Get Base64 encoded image
        base64_image = encode_image_to_base64(image_path)
        if not base64_image:
            logging.error(f"❌ Failed to encode image: {image_path}")
            return (False, None) if return_data else False
        
        # Call Ollama API
        for attempt in range(max_retries):
            try:
                # Check if Ollama server is available
                try:
                    health_check = requests.get(f"{server}/api/tags", timeout=5)
                    if health_check.status_code != 200:
                        logging.error(f"Ollama server health check failed with status code: {health_check.status_code}")
                        if attempt == max_retries - 1:
                            if return_data:
                                return (False, None)
                            return False
                        time.sleep(5)
                        continue
                except requests.exceptions.RequestException as e:
                    logging.error(f"Ollama server is not available: {e}")
                    if attempt == max_retries - 1:
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
                            if return_data:
                                return (description, tags)
                            return True
                        else:
                            logging.error(f"❌ Failed to update metadata for {image_path}")
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
        
        logging.error(f"❌ Failed after {max_retries} attempts for {image_path}")
        return (False, None) if return_data else False
        
    except Exception as e:
        logging.error(f"❌ Unexpected error processing {image_path}: {e}")
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

def get_file_checksum(file_path):
    """Calculates the SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            # Read and update hash in chunks of 4K
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except IOError as e:
        logging.error(f"Error reading file for checksum: {e}")
        return None

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

def update_image_metadata(image_path, description, tags, is_override, max_retries):
    """Update image metadata with description and tags using exiftool."""
    image_path = Path(image_path)
    
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
                logging.error(f"❌ exiftool failed (attempt {attempt + 1}/{max_retries}): {result.stderr}")
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
