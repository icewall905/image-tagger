#!/usr/bin/env python3
"""
Image Search CLI Tool
A command-line interface for searching images using the Image Tagger core functionality.
"""

import sys
import argparse
from pathlib import Path

# Add the backend directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

from image_tagger import core

def main():
    parser = argparse.ArgumentParser(
        description="Search for images using AI-generated descriptions and tags",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  image-search "person with dog" /path/to/images
  image-search "outdoor landscape" /path/to/images --recursive
  image-search "red car" /path/to/images --limit 10
        """
    )
    
    parser.add_argument(
        "query",
        help="Search query (text to search for in image descriptions)"
    )
    
    parser.add_argument(
        "path",
        help="Path to directory containing images to search"
    )
    
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Search recursively in subdirectories"
    )
    
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=20,
        help="Maximum number of results to return (default: 20)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # Validate the search path
    search_path = Path(args.path)
    if not search_path.exists():
        print(f"Error: Path '{args.path}' does not exist")
        sys.exit(1)
    
    if not search_path.is_dir():
        print(f"Error: Path '{args.path}' is not a directory")
        sys.exit(1)
    
    try:
        print(f"Searching for '{args.query}' in {args.path}...")
        if args.recursive:
            print("(including subdirectories)")
        
        # Use the core search functionality
        results = core.search_images(
            root_path=str(search_path),
            query=args.query,
            recursive=args.recursive
        )
        
        if not results:
            print("No images found matching your query.")
            return
        
        # Limit results
        results = results[:args.limit]
        
        print(f"\nFound {len(results)} matching images:")
        print("-" * 80)
        
        for i, (image_path, description, tags) in enumerate(results, 1):
            print(f"{i}. {image_path}")
            if description:
                print(f"   Description: {description}")
            if tags:
                print(f"   Tags: {', '.join(tags)}")
            print()
        
        if len(results) == args.limit:
            print(f"(Showing first {args.limit} results)")
            
    except Exception as e:
        print(f"Error during search: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 