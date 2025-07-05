#!/usr/bin/env python3
"""
Image Tagger CLI Entrypoint
- Uses core logic from image_tagger/core.py
- Provides the same CLI as the old installer-generated script
"""
import sys
import argparse
import logging
from pathlib import Path

# Import core logic
from image_tagger.core import (
    process_image, process_directory, clean_processed_db, load_config,
    check_dependencies, mark_file_as_processed, is_file_processed
)

def setup_logging(quiet=False):
    """Configure logging for the CLI."""
    # Configure logging level
    log_level = logging.WARNING if quiet else logging.INFO
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Remove any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

def main():
    parser = argparse.ArgumentParser(
        description='Image Tagger CLI - Tag images with AI-generated descriptions and tags',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  image-tagger image.jpg
  image-tagger -r /path/to/images
  image-tagger --override image.jpg
  image-tagger -q image.jpg
  image-tagger -h
"""
    )
    parser.add_argument('path', nargs='?', help='Path to image or directory (default: current directory)')
    parser.add_argument('-r', '--recursive', action='store_true', help='Process directories recursively')
    parser.add_argument('-e', '--endpoint', help='Ollama API endpoint (default from config)')
    parser.add_argument('-m', '--model', help='Model name (default from config)')
    parser.add_argument('-q', '--quiet', action='store_true', help='Quiet mode (minimal output)')
    parser.add_argument('--override', action='store_true', help='Override existing tags/descriptions')
    parser.add_argument('--no-file-tracking', action='store_true', help='Disable file tracking (process all files)')
    parser.add_argument('--clean-db', action='store_true', help='Clean tracking database of non-existent files')
    parser.add_argument('--batch-size', type=int, default=0, help='Batch size for processing (default: no batching)')
    parser.add_argument('--batch-delay', type=int, default=5, help='Delay (seconds) between batches')
    parser.add_argument('--restart-on-failure', action='store_true', help='Restart Ollama on API failure (if configured)')
    args = parser.parse_args()

    # Show help if no path provided and no other actions requested
    if args.path is None and not args.clean_db:
        parser.print_help()
        sys.exit(0)

    # Configure logging before doing anything else
    setup_logging(quiet=args.quiet)

    config = load_config()
    # Default to current directory if no path provided
    input_path = Path(args.path if args.path else '.')

    check_dependencies()

    # Merge CLI arguments with config
    server = args.endpoint if args.endpoint else config.get("server", "http://127.0.0.1:11434")
    model  = args.model    if args.model    else config.get("model", "llama3.2-vision")
    ollama_restart_cmd = config.get("ollama_restart_cmd", None)
    restart_on_failure = args.restart_on_failure

    # Log configuration being used
    logging.info(f"🚀 Starting Image Tagger CLI")
    logging.info(f"🔧 Server: {server}")
    logging.info(f"🔧 Model: {model}")
    logging.info(f"📂 Target: {input_path}")

    # Override file tracking if requested via command line
    if args.no_file_tracking:
        config["use_file_tracking"] = False
        logging.info("File tracking disabled via command line")

    # Handle database cleaning if requested
    if args.clean_db:
        logging.info("Cleaning tracking database...")
        removed = clean_processed_db()
        if removed >= 0:
            logging.info(f"Cleaned tracking database: removed {removed} entries for non-existent files")
        else:
            logging.error("Failed to clean tracking database")
        if args.path == '.' and not (input_path.is_file() or args.recursive):
            sys.exit(0)  # Exit if only cleaning was requested with default path

    if input_path.is_file():
        process_image(input_path, server, model, args.quiet, args.override, ollama_restart_cmd, restart_on_failure=restart_on_failure)
    elif input_path.is_dir():
        process_directory(
            input_path, server, model,
            args.recursive, args.quiet, args.override,
            ollama_restart_cmd, args.batch_size,
            args.batch_delay, 1,  # Always use 1 thread
            restart_on_failure=restart_on_failure
        )
    else:
        logging.error(f"Invalid input path: {input_path}")
        sys.exit(1)

if __name__ == "__main__":
    main() 