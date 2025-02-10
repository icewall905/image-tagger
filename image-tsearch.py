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
        logger.error("Permission denied: Unable to write to /var/log/image-search.log. Please check file permissions.")
    except Exception as e:
        logger.error(f"Failed to set up file logging: {e}")

def get_metadata_text(image_path):
    """
    Retrieve textual metadata from the image (Description + Tags).
    For PNG:  stored in text chunks.
    For JPEG: stored in EXIF, e.g., ImageDescription, UserComment, XPKeywords.
    Returns combined string of all found metadata fields.
    """
    try:
        with Image.open(image_path) as img:
            metadata_parts = []
            
            if str(image_path).lower().endswith('.png'):
                # PIL doesn't have a built-in way to read all PNGInfo easily after load,
                # so we can try reading chunks manually or rely on 'info' property.
                # The 'info' dict has the text if stored in tEXt or iTXt chunks.
                for k, v in img.info.items():
                    # k might be something like "Description" or "Tags"
                    if isinstance(v, str):
                        metadata_parts.append(v.lower())
            else:
                # For JPEG, see if EXIF is available
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
                            # usercomment_bytes can be a special format from piexif.helper.UserComment
                            try:
                                from piexif.helper import UserComment
                                user_comment_str = UserComment.load(usercomment_bytes)
                                if user_comment_str:
                                    metadata_parts.append(user_comment_str.lower())
                            except Exception:
                                pass
                        
                        # XPKeywords (Windows)
                        xpkeywords_bytes = exif_dict['0th'].get(piexif.ImageIFD.XPKeywords)
                        if xpkeywords_bytes:
                            try:
                                # Typically UTF-16-LE
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
    """
    Search images in root_path (recursively if requested) for the query string in metadata.
    Prints matching file paths.
    """
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')
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
    parser = argparse.ArgumentParser(
        description='Image-search v0.5 by HNB. Search images by metadata (Description + Tags).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  image-search "table"                 # Search current directory for images containing "table" in metadata
  image-search -r -p /path "bottle"    # Recursive search of /path for "bottle"
  image-search -p /some/dir "woman"    # Non-recursive search for "woman" in /some/dir
  """)
    
    parser.add_argument('query',
                        help='Search term (case-insensitive, substring match)')
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
