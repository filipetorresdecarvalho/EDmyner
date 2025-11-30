#!/usr/bin/env python3
"""
Centralized Database Manager for ED Mining Suite
- All paths (DATA_DIR, DB_PATH, CONFIG_PATH, LOG paths)
- Config JSON load/save with defaults
- SQLite wrapper with all query methods used across the app
- No SQLAlchemy (keeping it simple with raw sqlite3 like original)
"""

import os
import json
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================================
# CENTRALIZED PATHS - Import these everywhere
# ============================================================================
DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "ed_mining_data.db"
CONFIG_PATH = DATA_DIR / "ed_mining_config.json"
LOG_READER_LOG = DATA_DIR / "ed_log_reader.log"

# Default config structure
DEFAULT_CONFIG = {
    "colors": {
        "ed_orange": "#FF7700",
        "ed_dark": "#0D0D0D",
        "ed_gray": "#4A4A4A",
        "ed_success": "#00FF00",
        "ed_error": "#FF0000",
        "ed_warning": "#FFAA00"
    },
    "ui_settings": {
        "update_interval_ms": 1000,
        "window_width": 1200,
        "window_height": 800
    },
    "mining_settings": {
        "default_min_percentage": 25.0,
        "default_target_price": 250000,
        "track_surface_default": True,
        "track_deepcore_default": True
    },
    "tts_settings": {
        "enabled": True,
        "speed": 200,
        "volume": 1.0
    },
    "chat_settings": {
        "poll_interval_ms": 2000,
        "auto_clear_on_start": True
    }
}

# ============================================================================
# CONFIG FILE MANAGEMENT
# ============================================================================
def load_config() -> Dict[str, Any]:
    """Load config from JSON, create with defaults if missing."""
    DATA_DIR.mkdir(exist_ok=True)
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        logger.info(f"Created default config at {CONFIG_PATH}")
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
            # Merge with defaults to ensure all keys exist
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            return config
    except Exception as e:
        logger.error(f"Error loading config: {e}, using defaults")
        return DEFAULT_CONFIG.copy()

def save_config(config: Dict[str, Any]) -> bool:
    """Save config to JSON."""
    try:
        DATA_DIR.mkdir(exist_ok=True)
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"Config saved to {CONFIG_PATH}")
        return True
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False

# ============================================================================
# DATABASE MANAGER CLASS
# ============================================================================
class DatabaseManager:
    """
    Centralized database operations for all ED apps.
    Replaces duplicated DatabaseReader/DatabaseManager classes.
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection."""
        self.db_path = str(db_path or DB_PATH)
        self.connection: Optional[sqlite3.Connection] = None
        self._connect()
        self._create_tables()
        logger.info(f"DatabaseManager initialized: {self.db_path}")

    def _connect(self) -> None:
        """Establish database connection with proper settings."""
        try:
            DATA_DIR.mkdir(exist_ok=True)
            self.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=10.0
            )
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA busy_timeout=5000")
            logger.info("Database connection established")
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise

    def _create_tables(self) -> None:
        """Create all required tables (idempotent)."""
        try:
            cursor = self.connection.cursor()

            # Game state table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS game_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    commander_name TEXT,
                    current_system TEXT,
                    log_file_path TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                INSERT OR IGNORE INTO game_state (id, commander_name, current_system)
                VALUES (1, 'Unknown', 'Unknown')
            """)

            # Ship status table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ship_status (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    cargo_capacity INTEGER DEFAULT 0,
                    cargo_count INTEGER DEFAULT 0,
                    limpet_count INTEGER DEFAULT 0,
                    commander_credits INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("INSERT OR IGNORE INTO ship_status (id) VALUES (1)")

            # Fleet carriers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fleet_carriers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_name TEXT UNIQUE,
                    system_address INTEGER,
                    system_name TEXT,
                    discovered_timestamp TEXT,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # FSS signals table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fss_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_name TEXT,
                    signal_type TEXT,
                    is_station INTEGER,
                    system_address INTEGER,
                    system_name TEXT,
                    journal_timestamp TEXT,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Prospected asteroids table
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

            # Refined materials table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS refined_materials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    journal_timestamp TEXT,
                    material_name TEXT,
                    material_type TEXT
                )
            """)

            # Material configuration table
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

            # Service status table
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

            # Location history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS location_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    journal_timestamp TEXT,
                    system_name TEXT,
                    full_json TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Chat messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    journal_timestamp TEXT,
                    channel TEXT,
                    from_localised TEXT,
                    message_localised TEXT,
                    subtype TEXT DEFAULT 'other',
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            self.connection.commit()
            logger.info("All database tables created/verified")
        except sqlite3.Error as e:
            logger.error(f"Error creating tables: {e}")
            raise

    # ========================================================================
    # GAME STATE METHODS
    # ========================================================================
    def get_game_state(self) -> Dict[str, Any]:
        """Get current game state."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM game_state WHERE id = 1")
        row = cursor.fetchone()
        return dict(row) if row else {}

    def update_game_state(self, **kwargs) -> None:
        """Update game state fields."""
        cursor = self.connection.cursor()
        updates = ', '.join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values())
        cursor.execute(f"""
            UPDATE game_state SET {updates}, last_updated = CURRENT_TIMESTAMP
            WHERE id = 1
        """, values)
        self.connection.commit()

    # ========================================================================
    # SHIP STATUS METHODS
    # ========================================================================
    def get_ship_status(self) -> Dict[str, Any]:
        """Get current ship status."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM ship_status WHERE id = 1")
        row = cursor.fetchone()
        return dict(row) if row else {}

    def update_ship_status(self, **kwargs) -> None:
        """Update ship status fields."""
        cursor = self.connection.cursor()
        updates = ', '.join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values())
        cursor.execute(f"""
            UPDATE ship_status SET {updates}, last_updated = CURRENT_TIMESTAMP
            WHERE id = 1
        """, values)
        self.connection.commit()

    # ========================================================================
    # FLEET CARRIER METHODS
    # ========================================================================
    def get_fleet_carriers(self) -> List[Dict[str, Any]]:
        """Get all fleet carriers."""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM fleet_carriers 
            ORDER BY last_seen DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

    def add_fleet_carrier(self, signal_name: str, system_address: int, 
                         system_name: str, discovered_timestamp: str) -> None:
        """Add or update fleet carrier."""
        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO fleet_carriers 
            (signal_name, system_address, system_name, discovered_timestamp, last_seen)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (signal_name, system_address, system_name, discovered_timestamp))
        self.connection.commit()

    # ========================================================================
    # FSS SIGNALS / STATIONS METHODS
    # ========================================================================
    def get_stations(self) -> List[Dict[str, Any]]:
        """Get all station signals (excluding fleet carriers)."""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM fss_signals 
            WHERE is_station = 1 AND signal_type != 'FleetCarrier'
            ORDER BY last_seen DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

    def add_fss_signal(self, signal_name: str, signal_type: str, is_station: bool,
                       system_address: int, system_name: str, journal_timestamp: str) -> None:
        """Add FSS signal."""
        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO fss_signals 
            (signal_name, signal_type, is_station, system_address, system_name, journal_timestamp, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (signal_name, signal_type, int(is_station), system_address, system_name, journal_timestamp))
        self.connection.commit()

    # ========================================================================
    # PROSPECTED ASTEROIDS METHODS
    # ========================================================================
    def get_unprocessed_asteroids(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get unprocessed asteroid scans."""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM prospected_asteroids 
            WHERE processed = 0 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def mark_asteroid_processed(self, asteroid_id: int) -> None:
        """Mark asteroid as processed."""
        cursor = self.connection.cursor()
        cursor.execute("""
            UPDATE prospected_asteroids SET processed = 1 WHERE id = ?
        """, (asteroid_id,))
        self.connection.commit()

    def clear_asteroids(self) -> None:
        """Clear all asteroid records."""
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM prospected_asteroids")
        self.connection.commit()

    # ========================================================================
    # REFINED MATERIALS METHODS
    # ========================================================================
    def get_refined_materials_count(self, material_name: Optional[str] = None) -> int:
        """Get count of refined materials."""
        cursor = self.connection.cursor()
        if material_name:
            cursor.execute("""
                SELECT COUNT(*) as count FROM refined_materials 
                WHERE material_name = ?
            """, (material_name,))
        else:
            cursor.execute("SELECT COUNT(*) as count FROM refined_materials")
        return cursor.fetchone()['count']

    def clear_refined_materials(self) -> None:
        """Clear refined materials."""
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM refined_materials")
        self.connection.commit()

    # ========================================================================
    # MATERIAL CONFIG METHODS
    # ========================================================================
    def get_material_config(self, material_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get material configurations."""
        cursor = self.connection.cursor()
        if material_name:
            cursor.execute("""
                SELECT * FROM material_config WHERE material_name = ?
            """, (material_name,))
            row = cursor.fetchone()
            return [dict(row)] if row else []
        else:
            cursor.execute("SELECT * FROM material_config ORDER BY material_name")
            return [dict(row) for row in cursor.fetchall()]

    def save_material_config(self, material_name: str, min_percentage: float,
                            target_price: int, track_surface: bool, 
                            track_deepcore: bool, enabled: bool = True) -> None:
        """Save or update material configuration."""
        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO material_config 
            (material_name, min_percentage, target_price, track_surface, track_deepcore, enabled)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (material_name, min_percentage, target_price, 
              int(track_surface), int(track_deepcore), int(enabled)))
        self.connection.commit()

    def delete_material_config(self, material_name: str) -> None:
        """Delete material configuration."""
        cursor = self.connection.cursor()
        cursor.execute("""
            DELETE FROM material_config WHERE material_name = ?
        """, (material_name,))
        self.connection.commit()

    # ========================================================================
    # SERVICE STATUS METHODS
    # ========================================================================
    def get_service_status(self) -> Dict[str, Any]:
        """Get log reader service status."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM service_status WHERE id = 1")
        row = cursor.fetchone()
        return dict(row) if row else {}

    def update_service_status(self, **kwargs) -> None:
        """Update service status."""
        cursor = self.connection.cursor()
        updates = ', '.join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values())
        cursor.execute(f"""
            UPDATE service_status SET {updates} WHERE id = 1
        """, values)
        self.connection.commit()

    # ========================================================================
    # CHAT MESSAGES METHODS
    # ========================================================================
    def get_new_chat_messages(self, since_ts: str = "1970-01-01") -> List[Dict[str, Any]]:
        """Get chat messages since timestamp."""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM chat_messages 
            WHERE journal_timestamp > ? 
            ORDER BY journal_timestamp ASC
        """, (since_ts,))
        return [dict(row) for row in cursor.fetchall()]

    def add_chat_message(self, data: Dict[str, Any]) -> None:
        """Add chat message from journal."""
        cursor = self.connection.cursor()
        channel = data.get("Channel", "unknown").lower()
        from_loc = data.get("From_Localised", "Unknown")
        msg_loc = data.get("Message_Localised", "")
        ts = data.get("timestamp", "")

        # Determine subtype (sec, pirate, system, squad, friends, other)
        subtype = "other"
        msg_lower = msg_loc.lower()
        if "security" in from_loc.lower() or "system defence" in from_loc.lower():
            subtype = "sec"
        elif "pirate" in from_loc.lower() or "wing" in from_loc.lower():
            subtype = "pirate"
        elif channel in ["system", "local"]:
            subtype = "system"
        elif channel == "squadron":
            subtype = "sq"
        elif channel == "friend":
            subtype = "friends"

        cursor.execute("""
            INSERT INTO chat_messages 
            (journal_timestamp, channel, from_localised, message_localised, subtype, last_seen)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (ts, channel, from_loc, msg_loc, subtype))
        self.connection.commit()

    def clear_chat_messages(self) -> None:
        """Clear all chat messages."""
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM chat_messages")
        self.connection.commit()

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ============================================================================
# CONVENIENCE FUNCTIONS - Quick access without instantiating class
# ============================================================================
_db_instance = None

def get_db() -> DatabaseManager:
    """Get singleton database manager instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance

def init_db() -> DatabaseManager:
    """Initialize database (creates tables, seeds defaults)."""
    return get_db()
