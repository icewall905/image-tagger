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
from pathlib import Path
from PIL import Image
import piexif
from piexif import helper
from PIL.PngImagePlugin import PngInfo

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
    # 1. Apply regex patterns to extract multi-word tags
    for pattern in patterns:
        matches = re.findall(pattern, description.lower())
        for match in matches:
            tag = match.strip()
            if tag and tag not in stop_words:
                tags.add(tag)

    # 2. Simple keyword extraction: split description into words, exclude stop words, collect unique words
    words = re.findall(r'\b\w+\b', description.lower())
    for word in words:
        if word not in stop_words and len(word) > 2:
            tags.add(word)

    # 3. Final cleaning: remove duplicates and sort
    return sorted(tags)

def encode_image_to_base64(image_path):
    """Convert image to base64 string."""
    try:
        with Image.open(image_path) as img:
            if img.mode in ('RGBA', 'LA'):
                img = img.convert('RGB')
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG')
            img_byte_arr = img_byte_arr.getvalue()
            return base64.b64encode(img_byte_arr).decode('utf-8')
    except Exception as e:
        logging.error(f"Error encoding image {image_path}: {str(e)}")
        return None

def get_image_description(image_base64, ollama_endpoint):
    """Get image description from Ollama API using streaming response."""
    headers = {
        'Content-Type': 'application/json',
    }
    
    payload = {
        "model": "llama3.2-vision",
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
            f"{ollama_endpoint.rstrip('/')}/api/chat",
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

def update_image_metadata(image_path, description, tags):
    """Update image metadata with the description and tags."""
    try:
        img = Image.open(image_path)
        tags_str = ", ".join(tags)
        
        # Handle different image formats
        if str(image_path).lower().endswith('.png'):
            # PNG metadata
            metadata = PngInfo()
            metadata.add_text("Description", description)
            metadata.add_text("Tags", tags_str)
            img.save(str(image_path), pnginfo=metadata)
        
        else:
            # JPEG/TIFF metadata
            if 'exif' not in img.info:
                exif_dict = {'0th': {}, 'Exif': {}, 'GPS': {}, '1st': {}, 'thumbnail': None}
            else:
                try:
                    exif_dict = piexif.load(img.info['exif'])
                except Exception:
                    exif_dict = {'0th': {}, 'Exif': {}, 'GPS': {}, '1st': {}, 'thumbnail': None}
            
            # Add description and tags to multiple fields for better compatibility
            try:
                user_comment = helper.UserComment.dump(f"{description}\nTags: {tags_str}")
                exif_dict['Exif'][piexif.ExifIFD.UserComment] = user_comment
            except Exception:
                pass
            try:
                exif_dict['0th'][piexif.ImageIFD.ImageDescription] = description.encode('utf-8')
            except Exception:
                pass
            
            # Add tags to XPKeywords field (Windows compatible)
            try:
                if '0th' not in exif_dict:
                    exif_dict['0th'] = {}
                exif_dict['0th'][piexif.ImageIFD.XPKeywords] = tags_str.encode('utf-16le')
            except Exception:
                pass
            
            try:
                exif_bytes = piexif.dump(exif_dict)
                img.save(str(image_path), exif=exif_bytes)
            except Exception as e:
                logging.warning(f"Error saving EXIF data, attempting fallback: {str(e)}")
                img.save(str(image_path))
        
        logging.info(f"✓ Updated metadata for: {image_path}")
        if tags:
            logging.info(f"Tags: {tags_str}")
        return True
    except Exception as e:
        logging.error(f"✗ Error updating metadata for {image_path}: {str(e)}")
        return False

def process_image(image_path, ollama_endpoint, quiet=False, override=False):
    """Process a single image and update its metadata."""
    if not quiet:
        logging.info(f"Processing image: {image_path}")
    
    # Check for existing tags if override is False
    if not override:
        try:
            with Image.open(image_path) as img:
                # Check PNG metadata
                if str(image_path).lower().endswith('.png'):
                    if 'Tags' in img.info:
                        if not quiet:
                            logging.info(f"Skipping {image_path}: already has tags")
                        return True
                # Check JPEG/TIFF metadata
                else:
                    if 'exif' in img.info:
                        exif_dict = piexif.load(img.info['exif'])
                        if piexif.ImageIFD.XPKeywords in exif_dict['0th']:
                            if not quiet:
                                logging.info(f"Skipping {image_path}: already has tags")
                            return True
        except Exception as e:
            logging.debug(f"Error checking existing tags: {str(e)}")
    
    image_base64 = encode_image_to_base64(image_path)
    if not image_base64:
        return False
    
    description = get_image_description(image_base64, ollama_endpoint)
    if not description:
        return False
    

    if not quiet:
        logging.info(f"Generated description:\n{description}")
    
    tags = extract_tags_from_description(description)
    if not quiet and tags:
        logging.info(f"Generated tags:\n{', '.join(tags)}")
    
    return update_image_metadata(image_path, description, tags)

def main():
    parser = argparse.ArgumentParser(
        description='Image-tagger v0.5 by HNB. Tag images with AI-generated searchable descriptions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                     # Process all images in current directory
  %(prog)s image.jpg           # Process a single image
  %(prog)s /path/to/images     # Process all images in specified directory
  %(prog)s -r /path/to/images  # Process images recursively
  %(prog)s -e http://localhost:11434 image.jpg  # Use custom Ollama endpoint
  """)
    
    parser.add_argument('path', nargs='?', default='.',
                        help='Path to image or directory (default: current directory)')
    parser.add_argument('-r', '--recursive', action='store_true',
                        help='Process directories recursively')
    parser.add_argument('-e', '--endpoint', default='http://10.0.10.23:11434',
                        help='Ollama API endpoint (default: http://10.0.10.23:11434)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose output')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Minimal output')
    parser.add_argument('--override', action='store_true',
                        help='Override existing tags if present')
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    input_path = Path(args.path)
    
    if input_path.is_file():
        process_image(input_path, args.endpoint, args.quiet, args.override)
    elif input_path.is_dir():
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')
        if args.recursive:
            files = input_path.rglob('*')
        else:
            files = input_path.glob('*')
        for file_path in files:
            if file_path.suffix.lower() in image_extensions:
                process_image(file_path, args.endpoint, args.quiet, args.override)
    else:
        logging.error(f"Invalid input path: {input_path}")
        sys.exit(1)

if __name__ == "__main__":
    main()
