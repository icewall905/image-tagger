"""
Configuration management for Image Tagger WebUI
Handles loading and saving configuration from file and environment variables
"""

import os
import configparser
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union
import json

# Set up logging
logger = logging.getLogger("config")

# Get the current directory
current_dir = Path(__file__).parent.parent
# System-wide config takes precedence if it exists
SYSTEM_CONFIG_FILE = Path("/etc/image-tagger/config.ini")
LOCAL_CONFIG_FILE = current_dir / "config.ini"
CONFIG_FILE = SYSTEM_CONFIG_FILE if SYSTEM_CONFIG_FILE.exists() else LOCAL_CONFIG_FILE
DEFAULT_CONFIG = {
    "general": {
        "host": "0.0.0.0",
        "port": "8491",
        "debug": "false",
        "log_level": "INFO",
        "log_file": "data/image-tagger.log",
        "enable_structured_logging": "false"
    },
    "database": {
        "path": "sqlite:///data/image_tagger.db"
    },
    "ollama": {
        "server": "http://127.0.0.1:11434",
        "model": "qwen2.5vl",
        "timeout": "180",
        "temperature": "0.3"
    },
    "processing": {
        "max_workers": "4",
        "batch_size": "10",
        "background_processing": "true"
    },
    "storage": {
        "thumbnail_dir": "data/thumbnails",
        "thumbnail_max_size": "300",
        "thumbnail_quality": "85",
        "max_cache_size_mb": "1000"
    },
    "ui": {
        "items_per_page": "50",
        "dark_theme": "true",
        "default_sort": "date",
        "show_advanced": "false"
    },
    "security": {
        "enable_cors": "true",
        "cors_origins": "*",
        "enable_rate_limiting": "false",
        "rate_limit_per_minute": "60",
        "enable_security_headers": "true"
    },
    "tracking": {
        "db_path": "data/image-tagger-tracking.db",
        "use_file_tracking": "true"
    }
}

# Environment variable mappings
ENV_MAPPINGS = {
    "GENERAL_HOST": ("general", "host"),
    "GENERAL_PORT": ("general", "port"),
    "GENERAL_DEBUG": ("general", "debug"),
    "GENERAL_LOG_LEVEL": ("general", "log_level"),
    "GENERAL_LOG_FILE": ("general", "log_file"),
    "GENERAL_ENABLE_STRUCTURED_LOGGING": ("general", "enable_structured_logging"),
    "DATABASE_PATH": ("database", "path"),
    "OLLAMA_SERVER": ("ollama", "server"),
    "OLLAMA_MODEL": ("ollama", "model"),
    "OLLAMA_TIMEOUT": ("ollama", "timeout"),
    "OLLAMA_TEMPERATURE": ("ollama", "temperature"),
    "PROCESSING_MAX_WORKERS": ("processing", "max_workers"),
    "PROCESSING_BATCH_SIZE": ("processing", "batch_size"),
    "PROCESSING_BACKGROUND_PROCESSING": ("processing", "background_processing"),
    "STORAGE_THUMBNAIL_DIR": ("storage", "thumbnail_dir"),
    "STORAGE_THUMBNAIL_MAX_SIZE": ("storage", "thumbnail_max_size"),
    "STORAGE_THUMBNAIL_QUALITY": ("storage", "thumbnail_quality"),
    "STORAGE_MAX_CACHE_SIZE_MB": ("storage", "max_cache_size_mb"),
    "UI_ITEMS_PER_PAGE": ("ui", "items_per_page"),
    "UI_DARK_THEME": ("ui", "dark_theme"),
    "UI_DEFAULT_SORT": ("ui", "default_sort"),
    "UI_SHOW_ADVANCED": ("ui", "show_advanced"),
    "SECURITY_ENABLE_CORS": ("security", "enable_cors"),
    "SECURITY_CORS_ORIGINS": ("security", "cors_origins"),
    "SECURITY_ENABLE_RATE_LIMITING": ("security", "enable_rate_limiting"),
    "SECURITY_RATE_LIMIT_PER_MINUTE": ("security", "rate_limit_per_minute"),
    "SECURITY_ENABLE_SECURITY_HEADERS": ("security", "enable_security_headers"),
    "TRACKING_DB_PATH": ("tracking", "db_path"),
    "TRACKING_USE_FILE_TRACKING": ("tracking", "use_file_tracking")
}

# Create a ConfigParser instance
_parser = configparser.ConfigParser(interpolation=None)

class Config:
    """Configuration management class"""
    
    @classmethod
    def initialize(cls):
        """Initialize configuration from file and environment variables"""
        # Create default config if it doesn't exist
        if not os.path.exists(CONFIG_FILE):
            cls._create_default_config()
        
        # Load the configuration
        cls.load()
        
        # Apply environment variable overrides
        cls._apply_environment_overrides()
        
        logger.info("Configuration initialized successfully")
    
    @classmethod
    def load(cls):
        """Load configuration from file"""
        try:
            # Read the configuration file
            _parser.read(CONFIG_FILE)
            logger.info(f"Configuration loaded from {CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            # Fallback to defaults
            cls._create_default_config()
    
    @classmethod
    def save(cls):
        """Save configuration to file"""
        try:
            with open(CONFIG_FILE, 'w') as configfile:
                _parser.write(configfile)
            logger.info(f"Configuration saved to {CONFIG_FILE}")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {str(e)}")
            return False
    
    @classmethod
    def _create_default_config(cls):
        """Create default configuration file"""
        try:
            # Create the minimum required sections and settings
            for section, options in DEFAULT_CONFIG.items():
                _parser.add_section(section)
                for key, value in options.items():
                    _parser.set(section, key, value)
            
            # Save the default configuration
            cls.save()
            logger.info(f"Default configuration created at {CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Error creating default configuration: {str(e)}")
    
    @classmethod
    def _apply_environment_overrides(cls):
        """Apply environment variable overrides to configuration"""
        for env_var, (section, key) in ENV_MAPPINGS.items():
            env_value = os.environ.get(env_var)
            if env_value is not None:
                if not _parser.has_section(section):
                    _parser.add_section(section)
                _parser.set(section, key, env_value)
                logger.debug(f"Environment override: {env_var}={env_value}")
    
    @classmethod
    def get(cls, section, key, fallback=None):
        """Get a configuration value"""
        try:
            return _parser.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback
    
    @classmethod
    def getboolean(cls, section, key, fallback=None):
        """Get a boolean configuration value"""
        try:
            return _parser.getboolean(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback
    
    @classmethod
    def getint(cls, section, key, fallback=None):
        """Get an integer configuration value"""
        try:
            return _parser.getint(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback
    
    @classmethod
    def getfloat(cls, section, key, fallback=None):
        """Get a float configuration value"""
        try:
            return _parser.getfloat(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback
    
    @classmethod
    def set(cls, section, key, value):
        """Set a configuration value"""
        try:
            if not _parser.has_section(section):
                _parser.add_section(section)
            _parser.set(section, key, str(value))
            return True
        except Exception as e:
            logger.error(f"Error setting configuration value: {str(e)}")
            return False
    
    @classmethod
    def sections(cls):
        """Get all configuration sections"""
        return _parser.sections()
    
    @classmethod
    def items(cls, section):
        """Get all items in a section"""
        try:
            return _parser.items(section)
        except configparser.NoSectionError:
            return []
    
    @classmethod
    def has_section(cls, section):
        """Check if a section exists"""
        return _parser.has_section(section)
    
    @classmethod
    def add_section(cls, section):
        """Add a new configuration section"""
        try:
            if not _parser.has_section(section):
                _parser.add_section(section)
                return True
            return True  # Section already exists
        except Exception as e:
            logger.error(f"Error adding configuration section: {str(e)}")
            return False
    
    @classmethod
    def validate_config(cls) -> Dict[str, Any]:
        """Validate configuration and return validation results"""
        validation_results = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        try:
            # Validate required sections
            required_sections = ["general", "database", "ollama"]
            for section in required_sections:
                if not cls.has_section(section):
                    validation_results["errors"].append(f"Missing required section: {section}")
                    validation_results["valid"] = False
            
            # Validate database path
            db_path = cls.get("database", "path")
            if db_path:
                try:
                    # Test if we can create a database engine
                    from sqlalchemy import create_engine
                    engine = create_engine(db_path)
                    engine.dispose()
                except Exception as e:
                    validation_results["errors"].append(f"Invalid database path: {e}")
                    validation_results["valid"] = False
            
            # Validate Ollama settings
            ollama_server = cls.get("ollama", "server")
            if ollama_server and not ollama_server.startswith(("http://", "https://")):
                validation_results["warnings"].append("Ollama server should start with http:// or https://")
            
            # Validate port number
            try:
                port = cls.getint("general", "port", 8491)
                if port < 1 or port > 65535:
                    validation_results["errors"].append("Port must be between 1 and 65535")
                    validation_results["valid"] = False
            except ValueError:
                validation_results["errors"].append("Port must be a valid integer")
                validation_results["valid"] = False
            
            # Validate cache size
            try:
                cache_size = cls.getfloat("storage", "max_cache_size_mb", 1000.0)
                if cache_size < 0:
                    validation_results["errors"].append("Cache size must be positive")
                    validation_results["valid"] = False
            except ValueError:
                validation_results["errors"].append("Cache size must be a valid number")
                validation_results["valid"] = False
                
        except Exception as e:
            validation_results["errors"].append(f"Validation error: {str(e)}")
            validation_results["valid"] = False
        
        return validation_results
    
    @classmethod
    def export_config(cls) -> Dict[str, Any]:
        """Export configuration as dictionary"""
        config_dict = {}
        for section in cls.sections():
            config_dict[section] = dict(cls.items(section))
        return config_dict
    
    @classmethod
    def import_config(cls, config_dict: Dict[str, Any]) -> bool:
        """Import configuration from dictionary"""
        try:
            for section, items in config_dict.items():
                if not cls.has_section(section):
                    cls.add_section(section)
                for key, value in items.items():
                    cls.set(section, key, value)
            return True
        except Exception as e:
            logger.error(f"Error importing configuration: {str(e)}")
            return False

# Initialize the configuration when the module is imported
Config.initialize()

# For backwards compatibility
def get_config():
    """Get configuration as an object (for backwards compatibility)"""
    from typing import Dict, Any, Union, Callable
    
    class ConfigObj:
        """Configuration object with dynamic attributes"""
        config_path: str
        database: Dict[str, Any]
        general: Dict[str, Any]
        db_path: str
        log_level: str
        get: Callable[[str, str, Any], Any]
        
        def __init__(self):
            # Initialize basic structure
            self.database = {}
            self.general = {}
    
    config = ConfigObj()
    config.config_path = str(CONFIG_FILE)
    
    # Copy all configuration values as attributes
    for section in Config.sections():
        setattr(config, section, {})
        for key, value in Config.items(section):
            # Try to convert to appropriate types
            if value.lower() in ['true', 'false']:
                value = value.lower() == 'true'
            elif value.isdigit():
                value = int(value)
            elif value.replace('.', '', 1).isdigit() and value.count('.') == 1:
                value = float(value)
                
            # Set as attribute
            setattr(config, key, value)
            getattr(config, section)[key] = value
    
    # Special attributes accessed directly
    if hasattr(config, 'database') and 'path' in config.database:
        config.db_path = config.database['path']
    else:
        config.db_path = "sqlite:///data/image_tagger.db"
    
    if hasattr(config, 'general') and 'log_level' in config.general:
        config.log_level = config.general['log_level']
    else:
        config.log_level = "INFO"
    
    # Add convenience method for accessing config values
    def get_config_value(section: str, key: str, fallback: Any = None) -> Any:
        return getattr(config, section).get(key, fallback) if hasattr(config, section) else fallback
    
    config.get = get_config_value
    
    return config
