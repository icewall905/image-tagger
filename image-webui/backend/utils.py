import logging
import sys
import os
from pathlib import Path
from datetime import datetime
import json
from typing import Optional, Dict, Any

class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging"""
    
    def format(self, record):
        # Create structured log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
        
        return json.dumps(log_entry)

class PerformanceLogger:
    """Utility for tracking performance metrics"""
    
    def __init__(self, logger_name: str = "performance"):
        self.logger = logging.getLogger(logger_name)
        self.metrics = {}
    
    def start_timer(self, operation: str):
        """Start timing an operation"""
        self.metrics[operation] = {
            'start_time': datetime.utcnow(),
            'status': 'running'
        }
    
    def end_timer(self, operation: str, success: bool = True, extra_data: Optional[Dict[str, Any]] = None):
        """End timing an operation and log the result"""
        if operation not in self.metrics:
            self.logger.warning(f"Timer for operation '{operation}' was not started")
            return
        
        start_time = self.metrics[operation]['start_time']
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        log_data = {
            'operation': operation,
            'duration_seconds': round(duration, 3),
            'success': success,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat()
        }
        
        if extra_data:
            log_data.update(extra_data)
        
        if success:
            self.logger.info(f"Performance: {operation} completed in {duration:.3f}s", extra={'extra_fields': log_data})
        else:
            self.logger.error(f"Performance: {operation} failed after {duration:.3f}s", extra={'extra_fields': log_data})
        
        del self.metrics[operation]

def setup_logging(log_level_str: str = "INFO", log_file: Optional[str] = None, 
                 enable_structured_logging: bool = False):
    """
    Configures comprehensive logging for the application.
    
    Args:
        log_level_str: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for file logging
        enable_structured_logging: Whether to use structured JSON logging
    """
    # Handle None or invalid values
    if not log_level_str:
        log_level_str = "INFO"
    
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    
    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Remove any existing handlers to avoid duplicate logs
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Create formatter
    if enable_structured_logging:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Create file handler if specified
    if log_file:
        try:
            # Ensure log directory exists
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
            logging.info(f"File logging enabled: {log_file}")
        except Exception as e:
            logging.error(f"Failed to setup file logging to {log_file}: {e}")
    
    # Create error file handler for errors only
    error_log_file = log_file.replace('.log', '.error.log') if log_file else None
    if error_log_file:
        try:
            error_handler = logging.FileHandler(error_log_file)
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(formatter)
            logger.addHandler(error_handler)
            
            logging.info(f"Error logging enabled: {error_log_file}")
        except Exception as e:
            logging.error(f"Failed to setup error logging to {error_log_file}: {e}")
    
    logging.info(f"Logging configured with level: {logging.getLevelName(log_level)}")

def log_error_with_context(error: Exception, context: Dict[str, Any] = None, 
                          logger_name: str = "error_tracker"):
    """
    Log an error with additional context information.
    
    Args:
        error: The exception that occurred
        context: Additional context information
        logger_name: Name of the logger to use
    """
    logger = logging.getLogger(logger_name)
    
    error_data = {
        'error_type': type(error).__name__,
        'error_message': str(error),
        'error_module': getattr(error, '__module__', 'unknown'),
        'context': context or {}
    }
    
    logger.error(f"Error occurred: {error}", extra={'extra_fields': error_data})

def log_performance_metric(operation: str, duration: float, success: bool = True, 
                          extra_data: Optional[Dict[str, Any]] = None,
                          logger_name: str = "performance"):
    """
    Log a performance metric.
    
    Args:
        operation: Name of the operation
        duration: Duration in seconds
        success: Whether the operation was successful
        extra_data: Additional data to log
        logger_name: Name of the logger to use
    """
    logger = logging.getLogger(logger_name)
    
    metric_data = {
        'operation': operation,
        'duration_seconds': round(duration, 3),
        'success': success,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    if extra_data:
        metric_data.update(extra_data)
    
    if success:
        logger.info(f"Performance: {operation} completed in {duration:.3f}s", 
                   extra={'extra_fields': metric_data})
    else:
        logger.error(f"Performance: {operation} failed after {duration:.3f}s", 
                    extra={'extra_fields': metric_data})

def setup_application_logging(config_log_level: str = "INFO", 
                            config_log_file: Optional[str] = None,
                            enable_structured: bool = False):
    """
    Setup logging based on application configuration.
    
    Args:
        config_log_level: Log level from config
        config_log_file: Log file path from config
        enable_structured: Whether to enable structured logging
    """
    # Determine log file path
    log_file = None
    if config_log_file:
        log_file = config_log_file
    else:
        # Default log file in data directory
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        log_file = str(data_dir / "image-tagger.log")
    
    # Setup logging
    setup_logging(
        log_level_str=config_log_level,
        log_file=log_file,
        enable_structured_logging=enable_structured
    )
    
    # Log startup information
    logging.info("Application logging initialized", extra={
        'extra_fields': {
            'log_level': config_log_level,
            'log_file': log_file,
            'structured_logging': enable_structured
        }
    })

# Global performance logger instance
performance_logger = PerformanceLogger()

# Example of other utility functions that might be here:
# def some_other_utility_function():
#     pass
