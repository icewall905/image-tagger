import logging
import sys

def setup_logging(log_level_str: str = "INFO"):
    """
    Configures basic logging for the application.
    """
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    
    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Remove any existing handlers to avoid duplicate logs
    # This is important if this function is called multiple times or by different modules
    if logger.hasHandlers():
        logger.handlers.clear()
        
    # Create a handler for stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    
    # Create a formatter and set it for the handler
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    
    # Add the handler to the logger
    logger.addHandler(handler)
    
    logging.info(f"Logging configured with level: {logging.getLevelName(log_level)}")

# Example of other utility functions that might be here:
# def some_other_utility_function():
#     pass
