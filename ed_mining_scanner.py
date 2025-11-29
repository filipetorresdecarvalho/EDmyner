#!/usr/bin/env python3
"""
Elite Dangerous Mining Scanner - PySide6 Edition

Modern UI for Elite Dangerous material scanning with proper icon support.

Requirements:
    pip install PySide6 pyttsx3

Architecture:
- Reads data from SQLite database populated by ed_log_reader.py
- Manages log reader process lifecycle (start/stop/restart)
- Provides rich UI for material configuration and detection monitoring

CHANGELOG 2025-11-29 1:32 PM:
- Fixed TTS by running in separate thread to avoid blocking
- Added voice selection dropdown with list of available Windows voices
- Improved TTS announcements to include deepcore information
- Added better error handling for TTS failures
"""

import sys
import os
import sqlite3
import subprocess
import time
import logging
from typing import Optional, List, Dict, Any, Set
from datetime import datetime
from pathlib import Path
from threading import Thread

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QComboBox,
    QProgressBar, QMessageBox, QFileDialog, QGroupBox, QFormLayout,
    QTextEdit, QSplitter
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QIcon, QPalette, QColor, QFont

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Elite Dangerous color scheme
ED_ORANGE = "#FF7700"
ED_DARK = "#0D0D0D"
ED_GRAY = "#4A4A4A"
ED_SUCCESS = "#00FF00"
ED_ERROR = "#FF0000"
ED_WARNING = "#FFAA00"

# Materials list
MATERIALS = [
    "Platinum", "Painite", "Osmium", "Low Temperature Diamonds",
    "Rhodplumsite", "Serendibite", "Monazite", "Musgravite",
    "Grandidierite", "Benitoite", "Alexandrite", "Void Opals",
    "Bromellite", "Tritium"
]


def get_default_log_path() -> str:
    """Get default Elite Dangerous log path."""
    user_home = os.path.expanduser("~")
    return os.path.join(user_home, "Saved Games", "Frontier Developments", "Elite Dangerous")


class TTSHandler:
    """
    Handle text-to-speech functionality.
    
    AI NOTE: Ported from original code, handles Windows SAPI TTS.
    
    FIXED 2025-11-29 1:32 PM:
    - Run TTS in separate thread to avoid blocking UI
    - Added method to get available voices
    - Added voice selection capability
    - Better error handling
    """
    
    def __init__(self):
        """Initialize TTS engine."""
        self.engine = None
        self.enabled = True
        self.current_voice_id = None
        self.available_voices = []
        
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 150)
            self.engine.setProperty('volume', 1.0)
            
            # ADDED 2025-11-29 1:32: Get available voices
            self.available_voices = self.engine.getProperty('voices')
            if self.available_voices:
                self.current_voice_id = self.available_voices[0].id
                logger.info(f"TTS engine initialized with {len(self.available_voices)} voices")
            else:
                logger.warning("TTS engine initialized but no voices found")
                
        except Exception as e:
            logger.error(f"TTS initialization error: {e}")
            self.enabled = False
    
    def get_available_voices(self) -> List[Dict[str, str]]:
        """
        Get list of available TTS voices.
        
        Returns:
            List of dicts with 'id' and 'name' keys
        
        ADDED 2025-11-29 1:32: List available Windows voices
        """
        voices = []
        if self.engine and self.available_voices:
            for voice in self.available_voices:
                # Extract friendly name from voice object
                name = voice.name
                # Remove "Microsoft" prefix and version info for cleaner display
                if "Microsoft" in name:
                    name = name.replace("Microsoft ", "").split(" - ")[0]
                
                voices.append({
                    'id': voice.id,
                    'name': name,
                    'full_name': voice.name
                })
        
        return voices
    
    def set_voice(self, voice_id: str) -> None:
        """
        Set the TTS voice.
        
        Args:
            voice_id: Voice ID from available voices
        
        ADDED 2025-11-29 1:32: Allow voice selection
        """
        if self.engine and self.enabled:
            try:
                self.engine.setProperty('voice', voice_id)
                self.current_voice_id = voice_id
                logger.info(f"TTS voice changed to: {voice_id}")
            except Exception as e:
                logger.error(f"Error setting TTS voice: {e}")
    
    def set_speed(self, speed: int) -> None:
        """Set TTS speed (50-300)."""
        if self.engine and self.enabled:
            try:
                speed = max(50, min(300, speed))
                self.engine.setProperty('rate', speed)
                logger.debug(f"TTS speed set to: {speed}")
            except Exception as e:
                logger.error(f"Error setting TTS speed: {e}")
    
    def speak(self, text: str) -> None:
        """
        Speak the given text in a separate thread.
        
        Args:
            text: Text to speak
        
        FIXED 2025-11-29 1:32: Run in separate thread to avoid blocking UI
        Old code: Ran synchronously with runAndWait(), blocking UI
        New code: Runs in thread, non-blocking
        """
        if not self.engine or not self.enabled:
            logger.info(f"TTS (disabled): {text}")
            return
        
        # MODIFIED 2025-11-29 1:32: Run TTS in separate thread
        # Old code: 
        # try:
        #     self.engine.stop()
        #     self.engine.say(text)
        #     self.engine.runAndWait()
        # except Exception as e:
        #     logger.error(f"TTS error: {e}")
        
        def speak_thread():
            """Thread function to speak text without blocking UI."""
            try:
                # Create a new engine instance for this thread to avoid conflicts
                import pyttsx3
                engine = pyttsx3.init()
                
                # Apply current settings
                engine.setProperty('rate', self.engine.getProperty('rate'))
                engine.setProperty('volume', self.engine.getProperty('volume'))
                
                if self.current_voice_id:
                    try:
                        engine.setProperty('voice', self.current_voice_id)
                    except:
                        pass  # Voice might not be available, use default
                
                # Speak
                engine.say(text)
                engine.runAndWait()
                engine.stop()
                
                logger.debug(f"TTS spoke: {text}")
                
            except Exception as e:
                logger.error(f"TTS thread error: {e}")
        
        # Start thread
        thread = Thread(target=speak_thread, daemon=True)
        thread.start()


class DatabaseReader:
    """
    Read data from SQLite database populated by log reader service.
    
    AI NOTE: This is read-only. The log reader writes, this UI reads.
    SQLite handles concurrent access automatically.
    """
    
    def __init__(self, db_path: str = "ed_mining_data.db"):
        """Initialize database reader."""
        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None
        self._connect()
    
    def _connect(self) -> None:
        """Establish database connection."""
        try:
            self.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=5.0
            )
            self.connection.row_factory = sqlite3.Row
            logger.info("Database reader connected")
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise
    
    def get_game_state(self) -> Dict[str, Any]:
        """Get current game state (commander, system)."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM game_state WHERE id = 1")
            row = cursor.fetchone()
            
            if row:
                return {
                    'commander_name': row['commander_name'],
                    'current_system': row['current_system'],
                    'last_updated': row['last_updated']
                }
            return {'commander_name': 'Unknown', 'current_system': 'Unknown'}
            
        except sqlite3.Error as e:
            logger.error(f"Error reading game state: {e}")
            return {'commander_name': 'Unknown', 'current_system': 'Unknown'}
    
    def get_unprocessed_asteroids(self) -> List[Dict[str, Any]]:
        """Get all unprocessed prospected asteroids."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT * FROM prospected_asteroids 
                WHERE processed = 0 
                ORDER BY id ASC
            """)
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
            
        except sqlite3.Error as e:
            logger.error(f"Error reading prospected asteroids: {e}")
            return []
    
    def mark_asteroid_processed(self, asteroid_id: int) -> None:
        """Mark an asteroid as processed."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                UPDATE prospected_asteroids SET processed = 1 WHERE id = ?
            """, (asteroid_id,))
            self.connection.commit()
        except sqlite3.Error as e:
            logger.error(f"Error marking asteroid processed: {e}")
    
    def get_refined_materials_count(self) -> int:
        """Get count of refined materials in current session."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM refined_materials")
            row = cursor.fetchone()
            return row['count'] if row else 0
        except sqlite3.Error as e:
            logger.error(f"Error reading refined materials: {e}")
            return 0
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get log reader service status."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM service_status WHERE id = 1")
            row = cursor.fetchone()
            
            if row:
                return {
                    'is_running': bool(row['is_running']),
                    'pid': row['pid'],
                    'last_heartbeat': row['last_heartbeat'],
                    'journal_file': row['journal_file']
                }
            return {'is_running': False}
            
        except sqlite3.Error as e:
            logger.error(f"Error reading service status: {e}")
            return {'is_running': False}
    
    def get_material_config(self) -> List[Dict[str, Any]]:
        """Get all material configurations."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM material_config ORDER BY id")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error reading material config: {e}")
            return []
    
    def save_material_config(self, material: str, min_percentage: float,
                            target_price: int, track_surface: bool,
                            track_deepcore: bool) -> None:
        """Save or update material configuration."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO material_config 
                (material_name, min_percentage, target_price, track_surface, track_deepcore, enabled)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (material, min_percentage, target_price, 
                  1 if track_surface else 0, 1 if track_deepcore else 0))
            self.connection.commit()
            logger.info(f"Material config saved: {material}")
        except sqlite3.Error as e:
            logger.error(f"Error saving material config: {e}")
    
    def delete_material_config(self, material: str) -> None:
        """Delete material configuration."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM material_config WHERE material_name = ?", (material,))
            self.connection.commit()
        except sqlite3.Error as e:
            logger.error(f"Error deleting material config: {e}")
    
    def clear_refined_materials(self) -> None:
        """Clear refined materials (reset session)."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM refined_materials")
            self.connection.commit()
        except sqlite3.Error as e:
            logger.error(f"Error clearing refined materials: {e}")
    
    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            try:
                self.connection.close()
                logger.info("Database reader closed")
            except sqlite3.Error as e:
                logger.error(f"Error closing database: {e}")


class LogReaderManager:
    """Manages the log reader background process."""
    
    def __init__(self):
        """Initialize log reader manager."""
        self.process: Optional[subprocess.Popen] = None
        self.log_reader_script = "ed_log_reader.py"
    
    def is_running(self) -> bool:
        """Check if log reader service is running."""
        if self.process and self.process.poll() is None:
            return True
        
        pid_file = "ed_log_reader.pid"
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                try:
                    os.kill(pid, 0)
                    return True
                except OSError:
                    os.remove(pid_file)
                    return False
            except:
                return False
        
        return False
    
    def start(self, log_path: str = None) -> bool:
        """Start the log reader service."""
        try:
            if self.is_running():
                logger.warning("Log reader already running")
                return True
            
            cmd = [sys.executable, self.log_reader_script]
            if log_path:
                cmd.append(log_path)
            
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.process = subprocess.Popen(
                    cmd,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                self.process = subprocess.Popen(cmd)
            
            logger.info(f"Log reader started with PID: {self.process.pid}")
            time.sleep(1)
            return True
            
        except Exception as e:
            logger.error(f"Error starting log reader: {e}")
            return False
    
    def stop(self) -> bool:
        """Stop the log reader service."""
        try:
            if self.process:
                self.process.terminate()
                self.process.wait(timeout=5)
                self.process = None
                logger.info("Log reader stopped")
                return True
            
            pid_file = "ed_log_reader.pid"
            if os.path.exists(pid_file):
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                os.kill(pid, 15)
                os.remove(pid_file)
                logger.info(f"Log reader stopped (PID: {pid})")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error stopping log reader: {e}")
            return False
    
    def restart(self, log_path: str = None) -> bool:
        """Restart the log reader service."""
        self.stop()
        time.sleep(1)
        return self.start(log_path)


class MiningScannerUI(QMainWindow):
    """
    Main UI window for Elite Dangerous Mining Scanner.
    
    CHANGELOG 2025-11-29 1:32 PM:
    - Added voice selection dropdown in Config tab
    - Fixed TTS test button
    - Enhanced TTS announcements with deepcore info
    """
    
    def __init__(self):
        """Initialize the main window."""
        super().__init__()
        
        # State
        self.database = DatabaseReader()
        self.tts = TTSHandler()
        self.log_reader_manager = LogReaderManager()
        self.log_path = get_default_log_path()
        self.tts_speed = 150
        self.last_asteroid_timestamp = None
        
        # Setup UI
        self.setWindowTitle("Elite Dangerous Mining Scanner v8 - PySide6")
        self.setMinimumSize(1200, 800)
        self._setup_theme()
        self._create_ui()
        
        # Setup timer for real-time updates
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_scan_data)
        self.update_timer.start(500)
        
        # Check log reader status on startup
        self._check_log_reader_status()
        
        logger.info("UI initialized successfully")
    
    def _setup_theme(self) -> None:
        """Setup Elite Dangerous themed colors."""
        stylesheet = f"""
            QMainWindow, QWidget {{
                background-color: {ED_DARK};
                color: white;
            }}
            QTabWidget::pane {{
                border: 1px solid {ED_GRAY};
                background-color: {ED_DARK};
            }}
            QTabBar::tab {{
                background-color: {ED_GRAY};
                color: white;
                padding: 10px 20px;
                margin: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: {ED_ORANGE};
            }}
            QTabBar::tab:hover {{
                background-color: #FF9944;
            }}
            QPushButton {{
                background-color: {ED_ORANGE};
                color: white;
                border: none;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #FF9944;
            }}
            QPushButton:pressed {{
                background-color: #CC5500;
            }}
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
                background-color: {ED_GRAY};
                color: white;
                border: 1px solid {ED_ORANGE};
                padding: 5px;
            }}
            QTableWidget {{
                background-color: {ED_DARK};
                alternate-background-color: {ED_GRAY};
                color: white;
                gridline-color: {ED_GRAY};
            }}
            QHeaderView::section {{
                background-color: {ED_ORANGE};
                color: white;
                padding: 5px;
                border: none;
                font-weight: bold;
            }}
            QProgressBar {{
                background-color: {ED_GRAY};
                border: 1px solid {ED_ORANGE};
                text-align: center;
                color: white;
            }}
            QProgressBar::chunk {{
                background-color: {ED_ORANGE};
            }}
            QGroupBox {{
                border: 2px solid {ED_ORANGE};
                margin-top: 10px;
                font-weight: bold;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
        """
        self.setStyleSheet(stylesheet)
    
    def _create_ui(self) -> None:
        """Create the main UI layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        self._create_engine_tab()
        self._create_config_tab()
        self._create_scan_tab()
        self._create_stations_tab()
        self._create_price_tab()
        self._create_web_tools_tab()
    
    def _create_engine_tab(self) -> None:
        """Create Engine tab for log reader control."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        log_group = QGroupBox("🚀 Elite Dangerous Log Path")
        log_layout = QVBoxLayout()
        
        path_layout = QHBoxLayout()
        self.log_path_input = QLineEdit(self.log_path)
        path_layout.addWidget(self.log_path_input)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_log_path)
        path_layout.addWidget(browse_btn)
        
        log_layout.addLayout(path_layout)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        service_group = QGroupBox("⚙️ Log Reader Service Control")
        service_layout = QVBoxLayout()
        
        self.service_status_label = QLabel("Status: Checking...")
        self.service_status_label.setStyleSheet(f"color: {ED_WARNING};")
        service_layout.addWidget(self.service_status_label)
        
        btn_layout = QHBoxLayout()
        
        self.start_service_btn = QPushButton("▶️ Start Service")
        self.start_service_btn.clicked.connect(self._start_log_reader)
        btn_layout.addWidget(self.start_service_btn)
        
        self.stop_service_btn = QPushButton("⏹️ Stop Service")
        self.stop_service_btn.clicked.connect(self._stop_log_reader)
        btn_layout.addWidget(self.stop_service_btn)
        
        self.restart_service_btn = QPushButton("🔄 Restart Service")
        self.restart_service_btn.clicked.connect(self._restart_log_reader)
        btn_layout.addWidget(self.restart_service_btn)
        
        service_layout.addLayout(btn_layout)
        service_group.setLayout(service_layout)
        layout.addWidget(service_group)
        
        state_group = QGroupBox("🎮 Current Game State")
        state_layout = QFormLayout()
        
        self.cmdr_label = QLabel("Unknown")
        self.cmdr_label.setStyleSheet(f"color: {ED_SUCCESS};")
        state_layout.addRow("Commander:", self.cmdr_label)
        
        self.system_label = QLabel("Unknown")
        self.system_label.setStyleSheet(f"color: {ED_SUCCESS};")
        state_layout.addRow("System:", self.system_label)
        
        state_group.setLayout(state_layout)
        layout.addWidget(state_group)
        
        layout.addStretch()
        self.tabs.addTab(widget, "⚙️ Engine")
    
    def _create_config_tab(self) -> None:
        """
        Create Config tab for material configuration.
        
        MODIFIED 2025-11-29 1:32: Added voice selection dropdown
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        header = QLabel("⚙️ Material Configuration")
        header.setStyleSheet(f"color: {ED_ORANGE}; font-size: 16px; font-weight: bold;")
        layout.addWidget(header)
        
        self.config_table = QTableWidget()
        self.config_table.setColumnCount(6)
        self.config_table.setHorizontalHeaderLabels([
            "Material", "Min %", "Target Price (Cr)", "Track Surface", "Track Deepcore", "Actions"
        ])
        self.config_table.horizontalHeader().setStretchLastSection(True)
        self.config_table.setAlternatingRowColors(True)
        
        self.config_table.setColumnWidth(0, 200)
        self.config_table.setColumnWidth(1, 100)
        self.config_table.setColumnWidth(2, 150)
        self.config_table.setColumnWidth(3, 120)
        self.config_table.setColumnWidth(4, 120)
        
        layout.addWidget(self.config_table)
        
        add_btn = QPushButton("➕ Add Material")
        add_btn.clicked.connect(self._add_material_config_row)
        layout.addWidget(add_btn)
        
        # TTS settings
        tts_group = QGroupBox("🔊 Text-to-Speech Settings")
        tts_layout = QVBoxLayout()
        
        # ADDED 2025-11-29 1:32: Voice selection
        voice_layout = QHBoxLayout()
        voice_layout.addWidget(QLabel("Voice:"))
        self.voice_combo = QComboBox()
        
        # Populate voices
        voices = self.tts.get_available_voices()
        if voices:
            for voice in voices:
                self.voice_combo.addItem(voice['name'], voice['id'])
            self.voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        else:
            self.voice_combo.addItem("No voices available")
            self.voice_combo.setEnabled(False)
        
        voice_layout.addWidget(self.voice_combo)
        voice_layout.addStretch()
        tts_layout.addLayout(voice_layout)
        
        # Speed control
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("TTS Speed:"))
        self.tts_speed_spin = QSpinBox()
        self.tts_speed_spin.setRange(50, 300)
        self.tts_speed_spin.setValue(self.tts_speed)
        self.tts_speed_spin.valueChanged.connect(self._on_tts_speed_changed)
        speed_layout.addWidget(self.tts_speed_spin)
        speed_layout.addStretch()
        
        test_btn = QPushButton("🎤 Test Voice")
        test_btn.clicked.connect(self._test_tts)
        speed_layout.addWidget(test_btn)
        
        tts_layout.addLayout(speed_layout)
        tts_group.setLayout(tts_layout)
        layout.addWidget(tts_group)
        
        self._load_material_configs()
        
        self.tabs.addTab(widget, "⚙️ Config")
    
    def _create_scan_tab(self) -> None:
        """Create Scan tab with detection table and statistics."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        header = QLabel("📡 Material Detections")
        header.setStyleSheet(f"color: {ED_ORANGE}; font-size: 16px; font-weight: bold;")
        layout.addWidget(header)
        
        self.detection_table = QTableWidget()
        self.detection_table.setColumnCount(7)
        self.detection_table.setHorizontalHeaderLabels([
            "Timestamp", "Material", "Percentage", "Progress", "Surface", "Deepcore", "Content"
        ])
        self.detection_table.setAlternatingRowColors(True)
        self.detection_table.horizontalHeader().setStretchLastSection(False)
        
        self.detection_table.setColumnWidth(0, 150)
        self.detection_table.setColumnWidth(1, 180)
        self.detection_table.setColumnWidth(2, 100)
        self.detection_table.setColumnWidth(3, 200)
        self.detection_table.setColumnWidth(4, 80)
        self.detection_table.setColumnWidth(5, 80)
        self.detection_table.setColumnWidth(6, 100)
        
        layout.addWidget(self.detection_table)
        
        clear_btn = QPushButton("🗑️ Clear Detections")
        clear_btn.clicked.connect(self._clear_detections)
        layout.addWidget(clear_btn)
        
        stats_group = QGroupBox("📊 Mining Session Statistics")
        stats_layout = QFormLayout()
        
        self.rocks_mined_label = QLabel("0")
        self.rocks_mined_label.setStyleSheet(f"color: {ED_SUCCESS};")
        stats_layout.addRow("⛏️ Rocks Mined:", self.rocks_mined_label)
        
        self.hourly_profit_label = QLabel("0 Cr/hr")
        self.hourly_profit_label.setStyleSheet(f"color: {ED_SUCCESS};")
        stats_layout.addRow("💰 Est. Hourly Profit:", self.hourly_profit_label)
        
        self.session_duration_label = QLabel("0m 0s")
        stats_layout.addRow("⏱️ Session Duration:", self.session_duration_label)
        
        reset_btn = QPushButton("🔄 Reset Statistics")
        reset_btn.clicked.connect(self._reset_statistics)
        stats_layout.addRow("", reset_btn)
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        self.tabs.addTab(widget, "📡 Scan")
    
    def _create_stations_tab(self) -> None:
        """Create Stations tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        header = QLabel("🚉 Stations & Fleet Carriers")
        header.setStyleSheet(f"color: {ED_ORANGE}; font-size: 16px; font-weight: bold;")
        layout.addWidget(header)
        
        info = QLabel("This feature will be implemented in Version 2.\n"
                     "Will display stations and fleet carriers discovered in system.")
        info.setStyleSheet("color: #888888;")
        layout.addWidget(info)
        
        layout.addStretch()
        self.tabs.addTab(widget, "🚉 Stations")
    
    def _create_price_tab(self) -> None:
        """Create Price tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        header = QLabel("💰 Commodity Prices")
        header.setStyleSheet(f"color: {ED_ORANGE}; font-size: 16px; font-weight: bold;")
        layout.addWidget(header)
        
        info = QLabel("This feature will be implemented in Version 2.\n"
                     "Will provide commodity price lookup and best selling locations.")
        info.setStyleSheet("color: #888888;")
        layout.addWidget(info)
        
        layout.addStretch()
        self.tabs.addTab(widget, "💰 Price")
    
    def _create_web_tools_tab(self) -> None:
        """Create Web Tools tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        header = QLabel("🌐 Web Tools")
        header.setStyleSheet(f"color: {ED_ORANGE}; font-size: 16px; font-weight: bold;")
        layout.addWidget(header)
        
        info = QLabel("This feature will be implemented in Version 2.\n"
                     "Will provide quick access to INARA, Spansh, and other ED tools.")
        info.setStyleSheet("color: #888888;")
        layout.addWidget(info)
        
        layout.addStretch()
        self.tabs.addTab(widget, "🌐 Web")
    
    def _get_desired_materials(self) -> Set[str]:
        """Get set of desired material names from config table."""
        desired = set()
        try:
            for row in range(self.config_table.rowCount()):
                material_combo = self.config_table.cellWidget(row, 0)
                if material_combo:
                    material_name = material_combo.currentText()
                    desired.add(material_name)
            logger.debug(f"Desired materials: {desired}")
        except Exception as e:
            logger.error(f"Error getting desired materials: {e}")
        
        return desired
    
    # Event handlers
    
    def _browse_log_path(self) -> None:
        """Browse for log directory."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Elite Dangerous Log Directory",
            self.log_path
        )
        if directory:
            self.log_path = directory
            self.log_path_input.setText(directory)
    
    def _start_log_reader(self) -> None:
        """Start the log reader service."""
        log_path = self.log_path_input.text()
        if self.log_reader_manager.start(log_path):
            self.service_status_label.setText("Status: ✅ Running")
            self.service_status_label.setStyleSheet(f"color: {ED_SUCCESS};")
            self.tts.speak("Log reader started")
        else:
            self.service_status_label.setText("Status: ❌ Failed to start")
            self.service_status_label.setStyleSheet(f"color: {ED_ERROR};")
            QMessageBox.critical(self, "Error", "Failed to start log reader service")
    
    def _stop_log_reader(self) -> None:
        """Stop the log reader service."""
        if self.log_reader_manager.stop():
            self.service_status_label.setText("Status: ⏹️ Stopped")
            self.service_status_label.setStyleSheet(f"color: {ED_WARNING};")
            self.tts.speak("Log reader stopped")
        else:
            QMessageBox.warning(self, "Warning", "Failed to stop log reader service")
    
    def _restart_log_reader(self) -> None:
        """Restart the log reader service."""
        log_path = self.log_path_input.text()
        if self.log_reader_manager.restart(log_path):
            self.service_status_label.setText("Status: ✅ Restarted")
            self.service_status_label.setStyleSheet(f"color: {ED_SUCCESS};")
            self.tts.speak("Log reader restarted")
        else:
            QMessageBox.critical(self, "Error", "Failed to restart log reader service")
    
    def _check_log_reader_status(self) -> None:
        """Check log reader service status."""
        if self.log_reader_manager.is_running():
            self.service_status_label.setText("Status: ✅ Running")
            self.service_status_label.setStyleSheet(f"color: {ED_SUCCESS};")
        else:
            self.service_status_label.setText("Status: ⏹️ Not Running")
            self.service_status_label.setStyleSheet(f"color: {ED_WARNING};")
    
    def _on_voice_changed(self, index: int) -> None:
        """
        Handle voice selection change.
        
        ADDED 2025-11-29 1:32: Handle voice selection
        """
        if index >= 0:
            voice_id = self.voice_combo.itemData(index)
            if voice_id:
                self.tts.set_voice(voice_id)
                logger.info(f"Voice changed to: {self.voice_combo.currentText()}")
    
    def _add_material_config_row(self) -> None:
        """Add a new material configuration row."""
        row = self.config_table.rowCount()
        self.config_table.insertRow(row)
        
        material_combo = QComboBox()
        material_combo.addItems(MATERIALS)
        self.config_table.setCellWidget(row, 0, material_combo)
        
        pct_spin = QDoubleSpinBox()
        pct_spin.setRange(0.1, 99.9)
        pct_spin.setValue(25.0)
        pct_spin.setSuffix("%")
        self.config_table.setCellWidget(row, 1, pct_spin)
        
        price_spin = QSpinBox()
        price_spin.setRange(0, 10000000)
        price_spin.setValue(250000)
        price_spin.setSingleStep(10000)
        self.config_table.setCellWidget(row, 2, price_spin)
        
        surface_check = QCheckBox()
        surface_check.setChecked(True)
        surface_widget = QWidget()
        surface_layout = QHBoxLayout(surface_widget)
        surface_layout.addWidget(surface_check)
        surface_layout.setAlignment(Qt.AlignCenter)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        self.config_table.setCellWidget(row, 3, surface_widget)
        
        deepcore_check = QCheckBox()
        deepcore_check.setChecked(True)
        deepcore_widget = QWidget()
        deepcore_layout = QHBoxLayout(deepcore_widget)
        deepcore_layout.addWidget(deepcore_check)
        deepcore_layout.setAlignment(Qt.AlignCenter)
        deepcore_layout.setContentsMargins(0, 0, 0, 0)
        self.config_table.setCellWidget(row, 4, deepcore_widget)
        
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        
        save_btn = QPushButton("💾")
        save_btn.setMaximumWidth(40)
        save_btn.clicked.connect(lambda: self._save_material_config(row))
        btn_layout.addWidget(save_btn)
        
        delete_btn = QPushButton("🗑️")
        delete_btn.setMaximumWidth(40)
        delete_btn.clicked.connect(lambda: self._delete_material_config(row))
        btn_layout.addWidget(delete_btn)
        
        self.config_table.setCellWidget(row, 5, btn_widget)
    
    def _save_material_config(self, row: int) -> None:
        """Save material configuration from table row."""
        try:
            material_combo = self.config_table.cellWidget(row, 0)
            pct_spin = self.config_table.cellWidget(row, 1)
            price_spin = self.config_table.cellWidget(row, 2)
            surface_widget = self.config_table.cellWidget(row, 3)
            deepcore_widget = self.config_table.cellWidget(row, 4)
            
            material = material_combo.currentText()
            min_pct = pct_spin.value()
            price = price_spin.value()
            surface = surface_widget.findChild(QCheckBox).isChecked()
            deepcore = deepcore_widget.findChild(QCheckBox).isChecked()
            
            self.database.save_material_config(material, min_pct, price, surface, deepcore)
            
            QMessageBox.information(self, "Success", f"Configuration saved for {material}")
            logger.info(f"Material config saved: {material}")
            
        except Exception as e:
            logger.error(f"Error saving material config: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save configuration: {e}")
    
    def _delete_material_config(self, row: int) -> None:
        """Delete material configuration."""
        try:
            material_combo = self.config_table.cellWidget(row, 0)
            material = material_combo.currentText()
            
            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Delete configuration for {material}?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.database.delete_material_config(material)
                self.config_table.removeRow(row)
                logger.info(f"Material config deleted: {material}")
                
        except Exception as e:
            logger.error(f"Error deleting material config: {e}")
            QMessageBox.critical(self, "Error", f"Failed to delete configuration: {e}")
    
    def _load_material_configs(self) -> None:
        """Load existing material configurations from database."""
        try:
            configs = self.database.get_material_config()
            
            for config in configs:
                row = self.config_table.rowCount()
                self.config_table.insertRow(row)
                
                material_combo = QComboBox()
                material_combo.addItems(MATERIALS)
                material_combo.setCurrentText(config['material_name'])
                self.config_table.setCellWidget(row, 0, material_combo)
                
                pct_spin = QDoubleSpinBox()
                pct_spin.setRange(0.1, 99.9)
                pct_spin.setValue(config['min_percentage'])
                pct_spin.setSuffix("%")
                self.config_table.setCellWidget(row, 1, pct_spin)
                
                price_spin = QSpinBox()
                price_spin.setRange(0, 10000000)
                price_spin.setValue(config['target_price'])
                price_spin.setSingleStep(10000)
                self.config_table.setCellWidget(row, 2, price_spin)
                
                surface_check = QCheckBox()
                surface_check.setChecked(bool(config['track_surface']))
                surface_widget = QWidget()
                surface_layout = QHBoxLayout(surface_widget)
                surface_layout.addWidget(surface_check)
                surface_layout.setAlignment(Qt.AlignCenter)
                surface_layout.setContentsMargins(0, 0, 0, 0)
                self.config_table.setCellWidget(row, 3, surface_widget)
                
                deepcore_check = QCheckBox()
                deepcore_check.setChecked(bool(config['track_deepcore']))
                deepcore_widget = QWidget()
                deepcore_layout = QHBoxLayout(deepcore_widget)
                deepcore_layout.addWidget(deepcore_check)
                deepcore_layout.setAlignment(Qt.AlignCenter)
                deepcore_layout.setContentsMargins(0, 0, 0, 0)
                self.config_table.setCellWidget(row, 4, deepcore_widget)
                
                btn_widget = QWidget()
                btn_layout = QHBoxLayout(btn_widget)
                btn_layout.setContentsMargins(0, 0, 0, 0)
                
                save_btn = QPushButton("💾")
                save_btn.setMaximumWidth(40)
                save_btn.clicked.connect(lambda checked, r=row: self._save_material_config(r))
                btn_layout.addWidget(save_btn)
                
                delete_btn = QPushButton("🗑️")
                delete_btn.setMaximumWidth(40)
                delete_btn.clicked.connect(lambda checked, r=row: self._delete_material_config(r))
                btn_layout.addWidget(delete_btn)
                
                self.config_table.setCellWidget(row, 5, btn_widget)
            
            logger.info(f"Loaded {len(configs)} material configurations")
            
        except Exception as e:
            logger.error(f"Error loading material configs: {e}")
    
    def _on_tts_speed_changed(self, value: int) -> None:
        """Handle TTS speed change."""
        self.tts_speed = value
        self.tts.set_speed(value)
    
    def _test_tts(self) -> None:
        """
        Test TTS voice.
        
        FIXED 2025-11-29 1:32: Now works properly with threaded TTS
        """
        self.tts.set_speed(self.tts_speed)
        self.tts.speak("Text to speech test. Platinum found at 75%")
        logger.info("TTS test triggered")
    
    def _update_scan_data(self) -> None:
        """Update scan data from database (called by timer)."""
        try:
            state = self.database.get_game_state()
            self.cmdr_label.setText(state.get('commander_name', 'Unknown'))
            self.system_label.setText(state.get('current_system', 'Unknown'))
            
            asteroids = self.database.get_unprocessed_asteroids()
            
            if asteroids:
                for asteroid in reversed(asteroids):
                    current_timestamp = asteroid.get('journal_timestamp')
                    
                    if (self.last_asteroid_timestamp is not None and 
                        current_timestamp != self.last_asteroid_timestamp and
                        self.detection_table.rowCount() > 0):
                        self._add_separator_row()
                    
                    self._add_detection_to_table(asteroid)
                    
                    self.last_asteroid_timestamp = current_timestamp
                    
                    self.database.mark_asteroid_processed(asteroid['id'])
            
            self._update_mining_stats()
            self._check_log_reader_status()
            
        except Exception as e:
            logger.error(f"Error updating scan data: {e}")
    
    def _add_separator_row(self) -> None:
        """Add an empty separator row to visually separate prospected rocks."""
        try:
            self.detection_table.insertRow(0)
            
            for col in range(self.detection_table.columnCount()):
                empty_item = QTableWidgetItem("")
                empty_item.setBackground(QColor(ED_DARK))
                self.detection_table.setItem(0, col, empty_item)
            
            self.detection_table.setRowHeight(0, 10)
            
            logger.debug("Added separator row")
            
        except Exception as e:
            logger.error(f"Error adding separator row: {e}")
    
    def _add_detection_to_table(self, asteroid: Dict[str, Any]) -> None:
        """
        Add a detection to the scan table.
        
        MODIFIED 2025-11-29 1:32: Enhanced TTS with deepcore info
        """
        try:
            self.detection_table.insertRow(0)
            row = 0
            
            desired_materials = self._get_desired_materials()
            material_name = asteroid['material_name']
            is_desired = material_name in desired_materials
            
            if is_desired:
                font = QFont()
                font.setBold(True)
                font.setPointSize(11)
            
            timestamp_item = QTableWidgetItem(asteroid['journal_timestamp'])
            if is_desired:
                timestamp_item.setFont(font)
            self.detection_table.setItem(row, 0, timestamp_item)
            
            material_item = QTableWidgetItem(material_name)
            if is_desired:
                material_item.setFont(font)
                material_item.setForeground(QColor(ED_ORANGE))
            self.detection_table.setItem(row, 1, material_item)
            
            pct = asteroid['percentage']
            pct_item = QTableWidgetItem(f"{pct:.1f}%")
            if is_desired:
                pct_item.setFont(font)
                pct_item.setForeground(QColor(ED_ORANGE))
            self.detection_table.setItem(row, 2, pct_item)
            
            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(int(pct))
            progress.setFormat(f"{pct:.1f}%")
            self.detection_table.setCellWidget(row, 3, progress)
            
            surface_check = QCheckBox()
            surface_check.setChecked(not asteroid['is_deepcore'])
            surface_widget = QWidget()
            surface_layout = QHBoxLayout(surface_widget)
            surface_layout.addWidget(surface_check)
            surface_layout.setAlignment(Qt.AlignCenter)
            surface_layout.setContentsMargins(0, 0, 0, 0)
            self.detection_table.setCellWidget(row, 4, surface_widget)
            
            deepcore_check = QCheckBox()
            deepcore_check.setChecked(bool(asteroid['is_deepcore']))
            deepcore_widget = QWidget()
            deepcore_layout = QHBoxLayout(deepcore_widget)
            deepcore_layout.addWidget(deepcore_check)
            deepcore_layout.setAlignment(Qt.AlignCenter)
            deepcore_layout.setContentsMargins(0, 0, 0, 0)
            self.detection_table.setCellWidget(row, 5, deepcore_widget)
            
            content_item = QTableWidgetItem(asteroid['content_level'])
            if is_desired:
                content_item.setFont(font)
            self.detection_table.setItem(row, 6, content_item)
            
            # MODIFIED 2025-11-29 1:32: Enhanced TTS with deepcore info
            # Old code: if is_desired and pct >= 25.0:
            # Old code:     self.tts.speak(f"{material_name} found at {int(pct)}%")
            if is_desired and pct >= 25.0:
                # Build TTS message
                tts_message = f"{material_name} found at {int(pct)}%"
                
                # Add location info (surface or deepcore)
                is_deepcore = bool(asteroid['is_deepcore'])
                if is_deepcore:
                    tts_message += " with deepcore"
                else:
                    tts_message += " on the surface"
                
                # Speak
                self.tts.speak(tts_message)
                logger.info(f"TTS: {tts_message}")
            
            logger.debug(f"Added detection: {material_name} at {pct}% (desired: {is_desired}, deepcore: {asteroid['is_deepcore']})")
            
        except Exception as e:
            logger.error(f"Error adding detection to table: {e}")
    
    def _clear_detections(self) -> None:
        """Clear all detections from table."""
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "Clear all detections?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.detection_table.setRowCount(0)
            self.last_asteroid_timestamp = None
    
    def _update_mining_stats(self) -> None:
        """Update mining statistics display."""
        try:
            count = self.database.get_refined_materials_count()
            self.rocks_mined_label.setText(str(count))
            
        except Exception as e:
            logger.error(f"Error updating mining stats: {e}")
    
    def _reset_statistics(self) -> None:
        """Reset mining statistics."""
        reply = QMessageBox.question(
            self,
            "Confirm Reset",
            "Reset mining statistics?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.database.clear_refined_materials()
            self.rocks_mined_label.setText("0")
            self.hourly_profit_label.setText("0 Cr/hr")
            self.session_duration_label.setText("0m 0s")
    
    def closeEvent(self, event) -> None:
        """Handle window close event."""
        self.database.close()
        event.accept()


def main():
    """Main entry point for the application."""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = MiningScannerUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
