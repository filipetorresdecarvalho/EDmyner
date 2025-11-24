# mining_stats.py - Mining session statistics tracker
from datetime import datetime

class MiningStats:
    """Track mining session statistics."""
    
    def __init__(self):
        self.mined_count = 0
        self.first_mining_time = None
        self.last_mining_time = None
    
    def add_refined_material(self, timestamp_str=None):
        """Record a refined material."""
        self.mined_count += 1
        
        if timestamp_str:
            try:
                mining_time = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%SZ')
            except:
                mining_time = datetime.now()
        else:
            mining_time = datetime.now()
        
        if self.first_mining_time is None:
            self.first_mining_time = mining_time
        self.last_mining_time = mining_time
    
    def reset(self):
        """Reset all statistics."""
        self.mined_count = 0
        self.first_mining_time = None
        self.last_mining_time = None
    
    def get_hourly_profit(self, sell_value):
        """Calculate estimated hourly profit."""
        if self.mined_count > 0 and self.first_mining_time and self.last_mining_time:
            time_diff_seconds = (self.last_mining_time - self.first_mining_time).total_seconds()
            if time_diff_seconds > 0:
                rocks_per_hour = (self.mined_count / time_diff_seconds) * 3600
                return rocks_per_hour * sell_value
        return 0
    
    def get_session_duration(self):
        """Get session duration in minutes and seconds."""
        if self.mined_count > 0 and self.first_mining_time and self.last_mining_time:
            time_diff_seconds = (self.last_mining_time - self.first_mining_time).total_seconds()
            minutes = int(time_diff_seconds / 60)
            seconds = int(time_diff_seconds % 60)
            return minutes, seconds
        return 0, 0
