#!/usr/bin/env python3
"""
Elite Dangerous Log Reader Service (Singleton)

This is a background service that continuously monitors the Elite Dangerous journal
files and stores relevant data in a SQLite database for other applications to consume.

Architecture Pattern: Singleton with SQLite IPC
- Only ONE instance of this service should run at a time
- Uses SQLite for thread-safe, persistent data storage
- Other apps read from the database without direct coupling

FUTURE VERSION 2 FEATURES TO ADD:
- System tray icon with status indicator
- Auto-start with Windows capability
- Configurable log levels via config file
"""

import os
import sys
import json
import time
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
import threading
import signal

# Configure logging for background service
# AI NOTE: Using file logging since this runs hidden - no console output visible
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ed_log_reader.log'),
        logging.StreamHandler()  # Also log to console for debugging
    ]
)
logger = logging.getLogger(__name__)


def get_default_log_path() -> str:
    """
    Get default Elite Dangerous log path.
    
    Returns:
        str: Path to Elite Dangerous journal directory
    """
    user_home = os.path.expanduser("~")
    return os.path.join(user_home, "Saved Games", "Frontier Developments", "Elite Dangerous")


class DatabaseManager:
    """
    Manages SQLite database for inter-process communication.
    
    AI CONTEXT: This is the core IPC mechanism. The log reader writes to this DB,
    and the UI application reads from it. SQLite handles locking automatically.
    
    Schema Design:
    - game_state: Current commander, system, last update time
    - prospected_asteroids: Real-time asteroid prospecting detections
    - refined_materials: Mining refined events for statistics
    - material_config: User configuration for materials to track
    
    FUTURE V2 ENHANCEMENTS:
    - Add indices for performance
    - Implement data retention policies (delete old records)
    - Add table for log reader health/heartbeat monitoring
    """
    
    def __init__(self, db_path: str = "ed_mining_data.db"):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None
        self._connect()
        self._create_tables()
        logger.info(f"Database initialized at: {db_path}")
    
    def _connect(self) -> None:
        """Establish database connection with proper settings."""
        try:
            # AI NOTE: check_same_thread=False allows multi-threaded access
            # SQLite handles locking internally, so this is safe
            self.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=10.0
            )
            self.connection.row_factory = sqlite3.Row  # Access columns by name
            logger.info("Database connection established")
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise
    
    def _create_tables(self) -> None:
        """
        Create all required tables if they don't exist.
        
        AI NOTE: Using IF NOT EXISTS to safely handle multiple runs.
        """
        try:
            cursor = self.connection.cursor()
            
            # Game state table - stores current commander and system info
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS game_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    commander_name TEXT,
                    current_system TEXT,
                    log_file_path TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert default row if not exists (singleton pattern at DB level)
            cursor.execute("""
                INSERT OR IGNORE INTO game_state (id, commander_name, current_system)
                VALUES (1, 'Unknown', 'Unknown')
            """)
            
            # Prospected asteroids table - stores real-time detections
            # AI NOTE: Each prospecting event creates a new row
            # Content values: Low, Medium, High (from journal's Content_Localised)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prospected_asteroids (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP,
                    journal_timestamp TEXT,
                    material_name TEXT,
                    percentage REAL,
                    is_motherlode INTEGER DEFAULT 0,
                    content_level TEXT,
                    is_surface INTEGER DEFAULT 1,
                    is_deepcore INTEGER DEFAULT 0,
                    remaining REAL,
                    processed INTEGER DEFAULT 0
                )
            """)
            
            # Refined materials table - tracks what was actually mined
            # AI NOTE: This feeds into the mining statistics calculations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS refined_materials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    journal_timestamp TEXT,
                    material_name TEXT,
                    material_type TEXT
                )
            """)
            
            # Material configuration table - user settings for tracking
            # AI NOTE: UI writes to this, log reader reads from it
            # FUTURE V2: Add alerts_enabled, sound_file, etc.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS material_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_name TEXT UNIQUE,
                    min_percentage REAL DEFAULT 25.0,
                    target_price INTEGER DEFAULT 0,
                    track_surface INTEGER DEFAULT 1,
                    track_deepcore INTEGER DEFAULT 1,
                    enabled INTEGER DEFAULT 1
                )
            """)
            
            # Service status table - log reader health monitoring
            # AI NOTE: UI checks this to know if log reader is alive
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS service_status (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    is_running INTEGER DEFAULT 0,
                    pid INTEGER,
                    last_heartbeat TIMESTAMP,
                    journal_file TEXT,
                    scan_interval REAL DEFAULT 0.5
                )
            """)
            
            cursor.execute("""
                INSERT OR IGNORE INTO service_status (id, is_running, last_heartbeat)
                VALUES (1, 0, CURRENT_TIMESTAMP)
            """)
            
            self.connection.commit()
            logger.info("Database tables created successfully")
            
        except sqlite3.Error as e:
            logger.error(f"Error creating tables: {e}")
            raise
    
    def update_game_state(self, commander: str = None, system: str = None, 
                         log_path: str = None) -> None:
        """
        Update current game state.
        
        Args:
            commander: Commander name
            system: Current system name
            log_path: Path to journal log file
        """
        try:
            cursor = self.connection.cursor()
            updates = []
            params = []
            
            if commander:
                updates.append("commander_name = ?")
                params.append(commander)
            if system:
                updates.append("current_system = ?")
                params.append(system)
            if log_path:
                updates.append("log_file_path = ?")
                params.append(log_path)
            
            if updates:
                updates.append("last_updated = CURRENT_TIMESTAMP")
                query = f"UPDATE game_state SET {', '.join(updates)} WHERE id = 1"
                cursor.execute(query, params)
                self.connection.commit()
                logger.debug(f"Game state updated: {commander}, {system}")
                
        except sqlite3.Error as e:
            logger.error(f"Error updating game state: {e}")
    
    def add_prospected_asteroid(self, data: Dict[str, Any]) -> None:
        """
        Add a prospected asteroid detection to database.
        
        Args:
            data: Dictionary containing asteroid data from journal
        
        AI NOTE: This is called for each material in the ProspectedAsteroid event.
        The journal can have multiple materials per asteroid, so we insert one row per material.
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO prospected_asteroids 
                (journal_timestamp, material_name, percentage, is_motherlode, 
                 content_level, is_deepcore, remaining)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get('timestamp'),
                data.get('material_name'),
                data.get('percentage'),
                data.get('is_motherlode', 0),
                data.get('content_level', 'Unknown'),
                data.get('is_deepcore', 0),
                data.get('remaining', 100.0)
            ))
            self.connection.commit()
            logger.debug(f"Prospected asteroid added: {data.get('material_name')} at {data.get('percentage')}%")
            
        except sqlite3.Error as e:
            logger.error(f"Error adding prospected asteroid: {e}")
    
    def add_refined_material(self, journal_timestamp: str, material_name: str, 
                            material_type: str) -> None:
        """
        Add refined material event (actual mining completed).
        
        Args:
            journal_timestamp: Timestamp from journal
            material_name: Material that was refined
            material_type: Material type/category
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO refined_materials (journal_timestamp, material_name, material_type)
                VALUES (?, ?, ?)
            """, (journal_timestamp, material_name, material_type))
            self.connection.commit()
            logger.debug(f"Refined material added: {material_name}")
            
        except sqlite3.Error as e:
            logger.error(f"Error adding refined material: {e}")
    
    def update_service_status(self, is_running: bool, pid: int = None, 
                            journal_file: str = None) -> None:
        """
        Update service status for health monitoring.
        
        Args:
            is_running: Whether service is currently running
            pid: Process ID
            journal_file: Current journal file being monitored
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                UPDATE service_status 
                SET is_running = ?, pid = ?, last_heartbeat = CURRENT_TIMESTAMP,
                    journal_file = ?
                WHERE id = 1
            """, (1 if is_running else 0, pid, journal_file))
            self.connection.commit()
            
        except sqlite3.Error as e:
            logger.error(f"Error updating service status: {e}")
    
    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            try:
                self.connection.close()
                logger.info("Database connection closed")
            except sqlite3.Error as e:
                logger.error(f"Error closing database: {e}")


class JournalReader:
    """
    Reads and monitors Elite Dangerous journal files.
    
    AI CONTEXT: This is the core journal monitoring logic ported from the original code.
    Key changes:
    - Now writes to database instead of keeping in-memory state
    - Detects MotherlodeMaterial for deepcore asteroids
    - Extracts Content level (Low/Medium/High)
    
    FUTURE V2 ENHANCEMENTS:
    - Handle journal file rotation more gracefully
    - Add journal file validation
    - Support reading historical data on startup
    """
    
    def __init__(self, log_path: str, database: DatabaseManager):
        """
        Initialize journal reader.
        
        Args:
            log_path: Path to Elite Dangerous journal directory
            database: Database manager instance
        """
        self.log_path = log_path
        self.database = database
        self.current_file: Optional[str] = None
        self.file_handle: Optional[object] = None
        self.position: int = 0
        self._find_latest_journal()
        logger.info(f"JournalReader initialized for path: {log_path}")
    
    def _find_latest_journal(self) -> None:
        """
        Find the latest journal file in the log directory.
        
        AI NOTE: Journal files are named like: Journal.2025-11-29T123456.01.log
        We sort reverse to get the most recent one.
        """
        try:
            if not os.path.exists(self.log_path):
                raise FileNotFoundError(f"Log path does not exist: {self.log_path}")
            
            journal_files = [
                f for f in os.listdir(self.log_path)
                if f.startswith("Journal.") and f.endswith(".log")
            ]
            
            if not journal_files:
                raise FileNotFoundError(f"No journal files found in: {self.log_path}")
            
            journal_files.sort(reverse=True)
            self.current_file = os.path.join(self.log_path, journal_files[0])
            self.database.update_service_status(True, os.getpid(), self.current_file)
            logger.info(f"Found latest journal: {journal_files[0]}")
            
        except Exception as e:
            logger.error(f"Error finding journal file: {e}")
            raise
    
    def read_initial_state(self) -> None:
        """
        Read initial commander and system from journal on startup.
        
        AI NOTE: This scans the entire current journal file to find the latest
        commander name and system location.
        """
        try:
            with open(self.current_file, 'r', encoding='utf-8') as f:
                commander = None
                system = None
                
                for line in f:
                    try:
                        data = json.loads(line)
                        event = data.get("event", "")
                        
                        # Commander name
                        if event == "Commander":
                            commander = data.get("Name", "Unknown")
                        elif event == "LoadGame":
                            commander = data.get("Commander", "Unknown")
                        
                        # Current system
                        if event in ["Location", "FSDJump", "CarrierJump"]:
                            system = data.get("StarSystem", "Unknown")
                    
                    except json.JSONDecodeError:
                        continue
                
                # Update database with initial state
                if commander or system:
                    self.database.update_game_state(commander, system, self.current_file)
                    logger.info(f"Initial state: CMDR {commander} in {system}")
                    
        except Exception as e:
            logger.error(f"Error reading initial state: {e}")
    
    def get_latest_line(self) -> Optional[str]:
        """
        Get the latest line from journal file (tail -f behavior).
        
        Returns:
            str: Latest line from journal, or None if no new data
        
        AI NOTE: This implements a tail-follow pattern. We keep file position
        and only read new lines as they're appended.
        """
        try:
            # Open file handle if not already open
            if not self.file_handle:
                self.file_handle = open(self.current_file, 'r', encoding='utf-8')
                self.file_handle.seek(0, 2)  # Seek to end of file
                self.position = self.file_handle.tell()
                logger.debug("File handle opened and positioned at end")
            
            # Try to read a new line
            line = self.file_handle.readline()
            if line:
                self.position = self.file_handle.tell()
                return line.strip()
            
            # Check if file was truncated or rotated (new journal file created)
            current_size = os.path.getsize(self.current_file)
            if self.position > current_size:
                logger.warning("Journal file truncated or rotated, reopening...")
                self.file_handle.close()
                self._find_latest_journal()
                self.file_handle = open(self.current_file, 'r', encoding='utf-8')
                self.file_handle.seek(0, 2)
                self.position = self.file_handle.tell()
            
            return None
            
        except Exception as e:
            logger.error(f"Error reading journal line: {e}")
            return None
    
    def close(self) -> None:
        """Close file handle."""
        if self.file_handle:
            try:
                self.file_handle.close()
                logger.info("Journal file handle closed")
            except Exception as e:
                logger.error(f"Error closing file handle: {e}")


class LogReaderService:
    """
    Main log reader service (Singleton pattern).
    
    AI CONTEXT: This is the main service class that orchestrates everything.
    It runs in a loop, reading journal events and writing to the database.
    
    SINGLETON PATTERN: Only one instance should run. We use PID file for enforcement.
    
    FUTURE V2 ENHANCEMENTS:
    - Implement proper daemon/service using python-daemon library
    - Add system tray icon with pystray
    - Support configuration file for scan interval, log level, etc.
    - Add command-line arguments for control (start/stop/status)
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern implementation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the log reader service."""
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.running = False
        self.database: Optional[DatabaseManager] = None
        self.journal_reader: Optional[JournalReader] = None
        self.scan_interval = 0.5  # Default scan interval in seconds
        self.pid_file = "ed_log_reader.pid"
        logger.info("LogReaderService singleton initialized")
    
    def _create_pid_file(self) -> None:
        """
        Create PID file to prevent multiple instances.
        
        AI NOTE: This is a simple file-based mutex. If the file exists and
        the process is still running, we refuse to start.
        """
        try:
            if os.path.exists(self.pid_file):
                with open(self.pid_file, 'r') as f:
                    old_pid = int(f.read().strip())
                
                # Check if process is still running (Windows-compatible)
                try:
                    os.kill(old_pid, 0)
                    raise RuntimeError(f"Another instance is already running (PID: {old_pid})")
                except OSError:
                    # Process doesn't exist, safe to remove stale PID file
                    logger.warning(f"Removing stale PID file (PID {old_pid} not running)")
                    os.remove(self.pid_file)
            
            # Write current PID
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
            
            logger.info(f"PID file created: {self.pid_file}")
            
        except Exception as e:
            logger.error(f"Error creating PID file: {e}")
            raise
    
    def _remove_pid_file(self) -> None:
        """Remove PID file on shutdown."""
        try:
            if os.path.exists(self.pid_file):
                os.remove(self.pid_file)
                logger.info("PID file removed")
        except Exception as e:
            logger.error(f"Error removing PID file: {e}")
    
    def start(self, log_path: str = None) -> None:
        """
        Start the log reader service.
        
        Args:
            log_path: Path to Elite Dangerous journal directory
        """
        try:
            logger.info("=" * 60)
            logger.info("Starting Elite Dangerous Log Reader Service")
            logger.info("=" * 60)
            
            # Create PID file to prevent multiple instances
            self._create_pid_file()
            
            # Initialize database
            self.database = DatabaseManager()
            
            # Initialize journal reader
            if not log_path:
                log_path = get_default_log_path()
            
            self.journal_reader = JournalReader(log_path, self.database)
            
            # Read initial state from journal
            self.journal_reader.read_initial_state()
            
            # Update service status
            self.database.update_service_status(True, os.getpid(), 
                                              self.journal_reader.current_file)
            
            # Start main loop
            self.running = True
            self._main_loop()
            
        except Exception as e:
            logger.error(f"Fatal error starting service: {e}", exc_info=True)
            self.stop()
            raise
    
    def _main_loop(self) -> None:
        """
        Main service loop - continuously monitors journal.
        
        AI NOTE: This is the heart of the service. It runs forever (until stopped)
        reading new journal lines and processing events.
        """
        logger.info("Entering main service loop")
        
        while self.running:
            try:
                # Update heartbeat
                self.database.update_service_status(True, os.getpid(),
                                                   self.journal_reader.current_file)
                
                # Read latest journal line
                line = self.journal_reader.get_latest_line()
                
                if line:
                    self._process_journal_line(line)
                
                # Sleep for configured interval
                time.sleep(self.scan_interval)
                
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(2)  # Prevent tight error loop
    
    def _process_journal_line(self, line: str) -> None:
        """
        Process a single journal line.
        
        Args:
            line: JSON line from journal
        
        AI NOTE: This is where we parse journal events and extract data.
        Key events we care about:
        - ProspectedAsteroid: Material detection with MotherlodeMaterial for deepcore
        - MiningRefined: Actual material collection
        - FSDJump/Location: System changes
        - Commander/LoadGame: Commander name
        """
        try:
            data = json.loads(line)
            event = data.get("event", "")
            
            # ProspectedAsteroid - The key event for material scanning
            if event == "ProspectedAsteroid":
                self._handle_prospected_asteroid(data)
            
            # MiningRefined - Material actually collected
            elif event == "MiningRefined":
                self._handle_mining_refined(data)
            
            # System location updates
            elif event in ["Location", "FSDJump", "CarrierJump"]:
                system = data.get("StarSystem", "Unknown")
                self.database.update_game_state(system=system)
                logger.info(f"System updated: {system}")
            
            # Commander name updates
            elif event == "Commander":
                commander = data.get("Name", "Unknown")
                self.database.update_game_state(commander=commander)
                logger.info(f"Commander updated: {commander}")
            
            elif event == "LoadGame":
                commander = data.get("Commander", "Unknown")
                self.database.update_game_state(commander=commander)
                logger.info(f"Commander updated: {commander}")
        
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in journal line: {e}")
        except Exception as e:
            logger.error(f"Error processing journal line: {e}", exc_info=True)
    
    def _handle_prospected_asteroid(self, data: Dict[str, Any]) -> None:
        """
        Handle ProspectedAsteroid event.
        
        Args:
            data: Journal event data
        
        AI NOTE: KEY LOGIC FOR DEEPCORE DETECTION
        If "MotherlodeMaterial" exists, this is a deepcore/motherlode asteroid.
        The MotherlodeMaterial field tells us which material is in the core.
        
        Example from user's journal:
        {
            "timestamp": "2025-11-29T11:59:51Z",
            "event": "ProspectedAsteroid",
            "Materials": [
                {"Name": "Platinum", "Proportion": 51.662041},
                {"Name": "Praseodymium", "Proportion": 11.502447}
            ],
            "MotherlodeMaterial": "Painite",
            "Content": "$AsteroidMaterialContent_Medium;",
            "Content_Localised": "Material Content: Medium",
            "Remaining": 100.000000
        }
        
        In this case:
        - Platinum and Praseodymium are surface materials
        - Painite is the deepcore material (from MotherlodeMaterial)
        """
        try:
            timestamp = data.get("timestamp", "")
            materials = data.get("Materials", [])
            motherlode_material = data.get("MotherlodeMaterial", None)
            content = data.get("Content_Localised", "Unknown")
            remaining = data.get("Remaining", 100.0)
            
            # Extract content level (Low/Medium/High)
            content_level = "Unknown"
            if "Low" in content:
                content_level = "Low"
            elif "Medium" in content:
                content_level = "Medium"
            elif "High" in content:
                content_level = "High"
            
            # Process each material in the asteroid
            for material in materials:
                material_name = material.get("Name_Localised", material.get("Name", "Unknown"))
                proportion = material.get("Proportion", 0.0)
                
                # AI NOTE: Proportion in journal is already 0-100, not 0-1
                # The original code had a bug multiplying by 100
                
                asteroid_data = {
                    'timestamp': timestamp,
                    'material_name': material_name,
                    'percentage': proportion,
                    'is_motherlode': 0,  # This is a surface material
                    'content_level': content_level,
                    'is_deepcore': 0,
                    'remaining': remaining
                }
                
                self.database.add_prospected_asteroid(asteroid_data)
            
            # If there's a motherlode material, add it separately
            # AI NOTE: This is the deepcore material detection
            if motherlode_material:
                motherlode_data = {
                    'timestamp': timestamp,
                    'material_name': motherlode_material,
                    'percentage': 100.0,  # Motherlode is always 100% of core
                    'is_motherlode': 1,
                    'content_level': content_level,
                    'is_deepcore': 1,
                    'remaining': remaining
                }
                self.database.add_prospected_asteroid(motherlode_data)
                logger.info(f"Motherlode detected: {motherlode_material} (Deepcore)")
        
        except Exception as e:
            logger.error(f"Error handling prospected asteroid: {e}", exc_info=True)
    
    def _handle_mining_refined(self, data: Dict[str, Any]) -> None:
        """
        Handle MiningRefined event (material collection).
        
        Args:
            data: Journal event data
        """
        try:
            timestamp = data.get("timestamp", "")
            material_name = data.get("Type_Localised", data.get("Type", "Unknown"))
            material_type = data.get("Type", "Unknown")
            
            self.database.add_refined_material(timestamp, material_name, material_type)
            logger.info(f"Material refined: {material_name}")
            
        except Exception as e:
            logger.error(f"Error handling mining refined: {e}", exc_info=True)
    
    def stop(self) -> None:
        """Stop the log reader service."""
        logger.info("Stopping log reader service...")
        self.running = False
        
        # Update service status
        if self.database:
            self.database.update_service_status(False, None, None)
            self.database.close()
        
        # Close journal reader
        if self.journal_reader:
            self.journal_reader.close()
        
        # Remove PID file
        self._remove_pid_file()
        
        logger.info("Log reader service stopped")
    
    def signal_handler(self, signum, frame):
        """Handle termination signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)


def main():
    """Main entry point for log reader service."""
    try:
        # Setup signal handlers for graceful shutdown
        service = LogReaderService()
        signal.signal(signal.SIGINT, service.signal_handler)
        signal.signal(signal.SIGTERM, service.signal_handler)
        
        # Start service
        log_path = get_default_log_path()
        if len(sys.argv) > 1:
            log_path = sys.argv[1]
        
        service.start(log_path)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
