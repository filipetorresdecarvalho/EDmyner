# config.py - Configuration and constants
import os
from pathlib import Path

class AppConfig:
    """Application configuration and constants."""
    
    APP_NAME = "Elite Dangerous Material Scanner v7"
    APP_GEOMETRY = "1000x850"
    
    # Elite Dangerous Color Scheme
    COLOR_ED_ORANGE = "#FF7700"
    COLOR_ED_DARK_BG = "#1a1a1a"
    COLOR_ED_DARKER_BG = "#0d0d0d"
    COLOR_ED_LIGHT_GRAY = "#4a4a4a"
    COLOR_ED_TEXT = "#ffffff"
    COLOR_ED_TEXT_DIM = "#cccccc"
    
    # Status colors
    COLOR_SUCCESS = "#00ff00"
    COLOR_ERROR = "#ff0000"
    COLOR_WARNING = "#ffaa00"
    COLOR_INFO = "#00aaff"
    
    # Default paths
    @staticmethod
    def get_default_log_path():
        """Get default Elite Dangerous log path."""
        user_home = os.path.expanduser("~")
        return os.path.join(user_home, "Saved Games", "Frontier Developments", "Elite Dangerous")
    
    # Materials list
    MATERIALS = [
        "Platinum", "Painite", "Osmium", "Low Temperature Diamonds",
        "Rhodplumsite", "Serendibite", "Monazite", "Musgravite",
        "Grandidierite", "Benitoite", "Alexandrite", "Void Opals"
    ]
    
    # Default values
    DEFAULT_SYSTEM = "Unknown"
    DEFAULT_COMMANDER = "Unknown"
    DEFAULT_MIN_PERCENTAGE = "25"
    DEFAULT_SELL_VALUE = "250000"
    DEFAULT_MATERIAL = "Platinum"
    
    # Files
    HISTORY_JSON_FILE = "detection_history.json"
