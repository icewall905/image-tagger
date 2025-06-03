"""
Configuration management for Image Tagger WebUI
Handles loading and saving configuration from file and environment variables
"""

import os
import configparser
import logging
from pathlib import Path

# Set up logging
logger = logging.getLogger("config")

# Get the current directory
current_dir = Path(__file__).parent.parent
CONFIG_FILE = current_dir / "config.ini"
DEFAULT_CONFIG = {
    "general": {
        "host": "0.0.0.0",
        "port": "8000",
        "debug": "false",
        "log_level": "INFO"
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
        "rate_limit_per_minute": "60"
    }
}

# Create a ConfigParser instance
_parser = configparser.ConfigParser(interpolation=None)

class Config:
    """Configuration management class"""
    
    @classmethod
    def initialize(cls):
        """Initialize configuration from file"""
        # Create default config if it doesn't exist
        if not os.path.exists(CONFIG_FILE):
            cls._create_default_config()
        
        # Load the configuration
        cls.load()
    
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

# Initialize the configuration when the module is imported
Config.initialize()

# For backwards compatibility
def get_config():
    """Get configuration as an object (for backwards compatibility)"""
    class ConfigObj:
        pass
    
    config = ConfigObj()
    config.config_path = CONFIG_FILE
    
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
    
    return config
