# journal_reader.py - Fixed to properly read StarSystem
import os
import json
import glob
from datetime import datetime

class JournalReader:
    """Read and parse Elite Dangerous journal files."""
    
    def __init__(self, log_path):
        self.log_path = log_path
        self.last_line = ""
    
    def get_latest_journal(self):
        """Find the most recently modified journal log file."""
        try:
            journal_pattern = os.path.join(self.log_path, "Journal.*.log")
            journals = glob.glob(journal_pattern)
            if not journals:
                return None
            return max(journals, key=os.path.getctime)
        except Exception as e:
            print(f"Error finding journal: {str(e)}")
            return None
    
    def read_commander(self):
        """Read commander name from journal."""
        journal_file = self.get_latest_journal()
        if not journal_file:
            return None
        
        try:
            with open(journal_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if '"event":"Commander"' in line:
                        data = json.loads(line)
                        return data.get("Name", "Unknown")
            return None
        except Exception as e:
            print(f"Error reading commander: {str(e)}")
            return None
    
    def read_current_system(self):
        """Read current system from journal (most recent Location/FSDJump event)."""
        journal_file = self.get_latest_journal()
        if not journal_file:
            return None
        
        try:
            with open(journal_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Search backwards for most recent Location or FSDJump
            for line in reversed(lines):
                if '"event":"Location"' in line or '"event":"FSDJump"' in line:
                    try:
                        data = json.loads(line)
                        star_system = data.get("StarSystem")
                        if star_system:
                            print(f"Found system: {star_system}")
                            return star_system
                    except Exception as e:
                        print(f"Error parsing line: {str(e)}")
                        continue
            return None
        except Exception as e:
            print(f"Error reading system: {str(e)}")
            return None
    
    def read_all_stations(self):
        """Read all stations and fleet carriers from journal."""
        journal_file = self.get_latest_journal()
        if not journal_file:
            return []
        
        stations = []
        try:
            with open(journal_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if '"event":"FSSSignalDiscovered"' in line and '"IsStation":true' in line:
                        try:
                            data = json.loads(line)
                            signal_name = data.get("SignalName")
                            signal_type = data.get("SignalType", "Unknown")
                            if signal_name:
                                display_type = "Fleet Carrier" if "FleetCarrier" in signal_type else "Station"
                                stations.append((display_type, signal_name))
                        except:
                            continue
        except Exception as e:
            print(f"Error reading stations: {str(e)}")
        
        return stations
    
    def get_latest_line(self):
        """Get the latest line from journal (for real-time monitoring)."""
        journal_file = self.get_latest_journal()
        if not journal_file:
            return None
        
        try:
            with open(journal_file, 'r', encoding='utf-8') as f:
                f.seek(0, os.SEEK_END)
                if f.tell() == 0:
                    return None
                f.seek(max(0, f.tell() - 2048), 0)  # Read last 2KB
                lines = f.readlines()
            
            current_last_line = lines[-1].strip() if lines else ""
            if current_last_line and current_last_line != self.last_line:
                self.last_line = current_last_line
                return current_last_line
            return None
        except Exception as e:
            print(f"Error reading latest line: {str(e)}")
            return None
