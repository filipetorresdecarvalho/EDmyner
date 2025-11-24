# event_processor.py - Process Elite Dangerous events
import json

class EventProcessor:
    """Process Elite Dangerous journal events."""
    
    def __init__(self, on_asteroid_found, on_material_refined, on_docked, on_station_found):
        self.on_asteroid_found = on_asteroid_found
        self.on_material_refined = on_material_refined
        self.on_docked = on_docked
        self.on_station_found = on_station_found
    
    def process_line(self, line, target_material, min_percentage):
        """Process a journal line."""
        try:
            # ProspectedAsteroid event
            if '"event":"ProspectedAsteroid"' in line:
                self._process_prospected_asteroid(line, target_material, min_percentage)
            
            # MiningRefined event
            elif '"event":"MiningRefined"' in line:
                self._process_mining_refined(line, target_material)
            
            # Docked event
            elif '"event":"Docked"' in line:
                self.on_docked()
            
            # FSSSignalDiscovered event
            elif '"event":"FSSSignalDiscovered"' in line and '"IsStation":true' in line:
                self._process_station_discovered(line)
        
        except Exception as e:
            print(f"Error processing line: {str(e)}")
    
    def _process_prospected_asteroid(self, line, target_material, min_percentage):
        """Process ProspectedAsteroid event."""
        try:
            data = json.loads(line)
            if data.get("Remaining") != 100.0:
                return
            
            materials = data.get("Materials", [])
            for mat in materials:
                if mat.get("Name") == target_material:
                    proportion = mat.get("Proportion", 0)
                    timestamp = data.get("timestamp")
                    self.on_asteroid_found(target_material, proportion, min_percentage, timestamp)
                    return
        except Exception as e:
            print(f"Error processing asteroid: {str(e)}")
    
    def _process_mining_refined(self, line, target_material):
        """Process MiningRefined event."""
        try:
            data = json.loads(line)
            type_localised = data.get("Type_Localised", "")
            if target_material in type_localised:
                timestamp = data.get("timestamp")
                self.on_material_refined(target_material, timestamp)
        except Exception as e:
            print(f"Error processing refined: {str(e)}")
    
    def _process_station_discovered(self, line):
        """Process FSSSignalDiscovered event for stations."""
        try:
            data = json.loads(line)
            signal_name = data.get("SignalName")
            signal_type = data.get("SignalType", "Unknown")
            if signal_name:
                display_type = "Fleet Carrier" if "FleetCarrier" in signal_type else "Station"
                self.on_station_found(display_type, signal_name)
        except Exception as e:
            print(f"Error processing station: {str(e)}")
