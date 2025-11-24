# detection_history.py - Detection history manager
import json
import os
from datetime import datetime

class DetectionHistory:
    """Manage detection history."""
    
    def __init__(self, json_file):
        self.json_file = json_file
        self.history = []
        self.load()
    
    def add(self, material, percentage, threshold):
        """Add detection to history."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry = {
            "timestamp": timestamp,
            "material": material,
            "percentage": percentage,
            "threshold": threshold
        }
        self.history.append(entry)
        self.save()
        return entry
    
    def clear(self):
        """Clear all history."""
        self.history.clear()
        self.save()
    
    def save(self):
        """Save history to JSON file."""
        try:
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving history: {str(e)}")
    
    def load(self):
        """Load history from JSON file."""
        try:
            if os.path.exists(self.json_file):
                with open(self.json_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
        except Exception as e:
            print(f"Error loading history: {str(e)}")
            self.history = []
