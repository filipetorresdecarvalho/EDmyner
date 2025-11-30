#!/usr/bin/env python3
"""
Elite Dangerous Mining Scanner - Refactored with centralized managers.
Inherits from EDBaseWindow, uses database_manager for all DB operations.

Features:
- Real-time asteroid detection from journal
- Material configuration with min %, price, surface/deepcore tracking
- Ship status panel (cargo, limpets, credits)
- Fleet carrier selection
- Stations and Fleet Carriers tabs
- Log reader service management
- Session statistics
- TTS announcements
"""

import sys
import os
import subprocess
import time
import logging
from typing import Optional, List, Dict, Any, Set
from datetime import datetime
from pathlib import Path
import urllib.parse

from core.core_ui import QApplication, QMainWindow, QMessageBox, QMdiArea, Qt

from core.core_database import get_db
from utilities.util_tts import TTSHandler




logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================
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


# ============================================================================
# LOG READER MANAGER
# ============================================================================
class LogReaderManager:
    """Manages the log reader background process."""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.script_path = "ed_log_reader.py"

    def is_running(self) -> bool:
        """Check if log reader is running via database."""
        try:
            db = get_db()
            status = db.get_service_status()
            return bool(status.get('is_running', 0))
        except Exception as e:
            logger.error(f"Error checking service status: {e}")
            return False

    def start(self, log_path: str = None) -> bool:
        """Start the log reader service."""
        try:
            if self.is_running():
                logger.warning("Log reader already running")
                return True

            cmd = [sys.executable, self.script_path]
            if log_path:
                cmd.append(log_path)

            if sys.platform == 'win32':
                self.process = subprocess.Popen(
                    cmd,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                self.process = subprocess.Popen(cmd)

            logger.info(f"Log reader started (PID: {self.process.pid})")
            time.sleep(1)
            return True
        except Exception as e:
            logger.error(f"Error starting log reader: {e}")
            return False

    def stop(self) -> bool:
        """Stop the log reader service."""
        try:
            db = get_db()
            db.update_service_status(is_running=0)

            if self.process:
                self.process.terminate()
                self.process.wait(timeout=5)
                self.process = None

            logger.info("Log reader stopped")
            return True
        except Exception as e:
            logger.error(f"Error stopping log reader: {e}")
            return False

    def restart(self, log_path: str = None) -> bool:
        """Restart the log reader service."""
        self.stop()
        time.sleep(1)
        return self.start(log_path)


# ============================================================================
# MINING SCANNER UI
# ============================================================================
class MiningScannerUI(EDBaseWindow):
    """
    Main mining scanner window with tabs for scan, config, engine, stations, etc.
    """

    def __init__(self):
        # Load config for window settings
        config = load_config()
        update_interval = config.get("ui_settings", {}).get("update_interval_ms", 500)

        # Initialize base window
        super().__init__(
            app_name="Mining Scanner",
            window_size=(1400, 800),
            update_interval_ms=update_interval
        )

        # State
        self.db = get_db()
        self.config = config
        self.tts = TTSHandler()
        self.log_reader_manager = LogReaderManager()
        self.log_path = get_default_log_path()
        self.last_asteroid_timestamp = None

        # TTS settings
        tts_speed = self.config.get("tts_settings", {}).get("speed", 150)
        self.tts.set_speed(tts_speed)

        # Create UI
        self._create_ui()

        # Load material configs
        self._load_material_configs()

        # Check log reader
        self._check_log_reader_status()

        # Start update timer
        self.start_updates()

        # Stations/FC refresh timer (5 min)
        self.stations_timer = QTimer(self)
        self.stations_timer.timeout.connect(self._refresh_stations_tables)
        stations_interval = self.config.get("ui_settings", {}).get("stations_interval_ms", 300000)
        self.stations_timer.start(stations_interval)
        self._refresh_stations_tables()

        logger.info("Mining Scanner initialized")

    def _create_ui(self):
        """Create main UI with sidebar and tabs."""
        # Central widget
        central = QWidget()
        main_layout = QHBoxLayout(central)

        # Ship status sidebar
        self._create_ship_status_panel()
        main_layout.addWidget(self.ship_status_panel)

        # Tab widget
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Set stretch (sidebar 1, tabs 4)
        main_layout.setStretch(0, 1)
        main_layout.setStretch(1, 4)

        # Create tabs
        self._create_scan_tab()
        self._create_config_tab()
        self._create_engine_tab()
        self._create_stations_tab()
        self._create_fc_tab()

        self.setCentralWidget(central)

    # ========================================================================
    # SHIP STATUS SIDEBAR
    # ========================================================================
    def _create_ship_status_panel(self):
        """Create ship status sidebar with system, credits, cargo, limpets."""
        self.ship_status_panel = QWidget()
        self.ship_status_panel.setMinimumWidth(300)
        self.ship_status_panel.setMaximumWidth(350)

        layout = QVBoxLayout(self.ship_status_panel)

        # Header
        header = QLabel("🚀 Ship Status")
        header.setStyleSheet(f"color: {ED_ORANGE}; font-size: 18px; font-weight: bold;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # System group
        system_group = QGroupBox("🌌 System")
        system_layout = QVBoxLayout()

        system_row = QHBoxLayout()
        self.clipboard_btn = QPushButton("📋")
        self.clipboard_btn.setFixedSize(30, 25)
        self.clipboard_btn.clicked.connect(self._copy_system_to_clipboard)
        system_row.addWidget(self.clipboard_btn)

        self.system_sidebar_label = QLabel("Unknown")
        self.system_sidebar_label.setStyleSheet(f"color: {ED_SUCCESS}; font-size: 14px; font-weight: bold;")
        system_row.addWidget(self.system_sidebar_label)
        system_row.addStretch()
        system_layout.addLayout(system_row)

        # Web links row
        links_row = QHBoxLayout()
        self.inara_btn = QPushButton("Inara")
        self.inara_btn.setFixedSize(50, 25)
        self.inara_btn.clicked.connect(self._open_inara)

        self.spansh_btn = QPushButton("Spansh")
        self.spansh_btn.setFixedSize(55, 25)
        self.spansh_btn.clicked.connect(self._open_spansh)

        self.edsm_btn = QPushButton("EDSM")
        self.edsm_btn.setFixedSize(45, 25)
        self.edsm_btn.clicked.connect(self._open_edsm)

        links_row.addWidget(self.inara_btn)
        links_row.addWidget(self.spansh_btn)
        links_row.addWidget(self.edsm_btn)
        links_row.addStretch()
        system_layout.addLayout(links_row)

        system_group.setLayout(system_layout)
        layout.addWidget(system_group)

        # Credits group
        credits_group = QGroupBox("💰 Credits")
        credits_layout = QVBoxLayout()
        self.credits_label = QLabel("0 Cr")
        self.credits_label.setStyleSheet(f"color: {ED_SUCCESS}; font-size: 20px; font-weight: bold;")
        self.credits_label.setAlignment(Qt.AlignCenter)
        credits_layout.addWidget(self.credits_label)
        credits_group.setLayout(credits_layout)
        layout.addWidget(credits_group)

        # Cargo group
        cargo_group = QGroupBox("📦 Cargo Hold")
        cargo_layout = QVBoxLayout()
        self.cargo_label = QLabel("0 / 0 (0%)")
        self.cargo_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.cargo_label.setAlignment(Qt.AlignCenter)
        cargo_layout.addWidget(self.cargo_label)

        self.cargo_progress = create_ed_progress_bar(parent=self)
        cargo_layout.addWidget(self.cargo_progress)
        cargo_group.setLayout(cargo_layout)
        layout.addWidget(cargo_group)

        # Limpets group
        limpets_group = QGroupBox("🤖 Limpets")
        limpets_layout = QVBoxLayout()
        self.limpets_label = QLabel("0 remaining")
        self.limpets_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.limpets_label.setAlignment(Qt.AlignCenter)
        limpets_layout.addWidget(self.limpets_label)

        self.limpets_progress = create_ed_progress_bar(parent=self)
        limpets_layout.addWidget(self.limpets_progress)
        limpets_group.setLayout(limpets_layout)
        layout.addWidget(limpets_group)

        layout.addStretch()

    def _copy_system_to_clipboard(self):
        """Copy current system name to clipboard."""
        system_name = self.system_sidebar_label.text()
        if system_name and system_name != "Unknown":
            QApplication.clipboard().setText(system_name)
            logger.info(f"Copied system to clipboard: {system_name}")

    def _open_inara(self):
        """Open current system in Inara."""
        system_name = self.system_sidebar_label.text()
        if system_name and system_name != "Unknown":
            url = f"https://inara.cz/elite/starsystem/?search={urllib.parse.quote(system_name)}"
            QDesktopServices.openUrl(QUrl(url))

    def _open_spansh(self):
        """Open current system in Spansh."""
        system_name = self.system_sidebar_label.text()
        if system_name and system_name != "Unknown":
            url = f"https://spansh.co.uk/search/{urllib.parse.quote(system_name)}"
            QDesktopServices.openUrl(QUrl(url))

    def _open_edsm(self):
        """Open current system in EDSM."""
        system_name = self.system_sidebar_label.text()
        if system_name and system_name != "Unknown":
            url = f"https://www.edsm.net/en/system?systemName={urllib.parse.quote(system_name)}"
            QDesktopServices.openUrl(QUrl(url))

    # ========================================================================
    # SCAN TAB
    # ========================================================================
    def _create_scan_tab(self):
        """Create scan tab with detection table and statistics."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header = QLabel("📡 Material Detections")
        header.setStyleSheet(f"color: {ED_ORANGE}; font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        # Detection table
        self.detection_table = create_ed_table(
            column_count=7,
            headers=["Timestamp", "Material", "%", "Progress", "Surface", "Deepcore", "Content"],
            parent=self
        )
        self.detection_table.setColumnWidth(0, 150)
        self.detection_table.setColumnWidth(1, 180)
        self.detection_table.setColumnWidth(2, 80)
        self.detection_table.setColumnWidth(3, 200)
        self.detection_table.setColumnWidth(4, 80)
        self.detection_table.setColumnWidth(5, 80)
        layout.addWidget(self.detection_table)

        # Clear button
        clear_btn = create_ed_button("🗑️ Clear Detections", parent=self)
        clear_btn.clicked.connect(self._clear_detections)
        layout.addWidget(clear_btn)

        # Statistics group
        stats_group = QGroupBox("📊 Session Statistics")
        stats_layout = QFormLayout()

        self.rocks_mined_label = QLabel("0")
        self.rocks_mined_label.setStyleSheet(f"color: {ED_SUCCESS};")
        stats_layout.addRow("⛏️ Rocks Refined:", self.rocks_mined_label)

        self.hourly_profit_label = QLabel("0 Cr/hr")
        self.hourly_profit_label.setStyleSheet(f"color: {ED_SUCCESS};")
        stats_layout.addRow("💰 Est. Hourly Profit:", self.hourly_profit_label)

        self.session_duration_label = QLabel("0m 0s")
        stats_layout.addRow("⏱️ Session Duration:", self.session_duration_label)

        reset_btn = create_ed_button("🔄 Reset Statistics", parent=self)
        reset_btn.clicked.connect(self._reset_statistics)
        stats_layout.addRow("", reset_btn)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        self.tabs.addTab(widget, "📡 Scan")

    @Slot()
    def _clear_detections(self):
        """Clear detection table and reset processed asteroids."""
        try:
            # Clear from database (mark all processed)
            asteroids = self.db.get_unprocessed_asteroids()
            for asteroid in asteroids:
                self.db.mark_asteroid_processed(asteroid['id'])

            # Clear table
            self.detection_table.setRowCount(0)
            logger.info("Detections cleared")
        except Exception as e:
            logger.error(f"Error clearing detections: {e}")

    @Slot()
    def _reset_statistics(self):
        """Reset session statistics."""
        try:
            self.db.clear_refined_materials()
            self.rocks_mined_label.setText("0")
            self.hourly_profit_label.setText("0 Cr/hr")
            logger.info("Statistics reset")
        except Exception as e:
            logger.error(f"Error resetting statistics: {e}")

    # ========================================================================
    # CONFIG TAB
    # ========================================================================
    def _create_config_tab(self):
        """Create config tab for material configuration and settings."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header = QLabel("⚙️ Material Configuration")
        header.setStyleSheet(f"color: {ED_ORANGE}; font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        # Material config table
        self.config_table = create_ed_table(
            column_count=6,
            headers=["Material", "Min %", "Target Price", "Surface", "Deepcore", "Actions"],
            parent=self
        )
        self.config_table.setColumnWidth(0, 200)
        self.config_table.setColumnWidth(1, 100)
        self.config_table.setColumnWidth(2, 150)
        self.config_table.setColumnWidth(3, 100)
        self.config_table.setColumnWidth(4, 100)
        layout.addWidget(self.config_table)

        # Add material button
        add_btn = create_ed_button("➕ Add Material", parent=self)
        add_btn.clicked.connect(self._add_material_config_row)
        layout.addWidget(add_btn)

        # Fleet carrier group
        carrier_group = QGroupBox("🚢 Your Fleet Carrier")
        carrier_layout = QHBoxLayout()
        carrier_layout.addWidget(QLabel("Select carrier:"))

        self.carrier_combo = QComboBox()
        self.carrier_combo.addItem("None", None)
        self.carrier_combo.currentIndexChanged.connect(self._on_carrier_changed)
        carrier_layout.addWidget(self.carrier_combo)

        refresh_carriers_btn = create_ed_button("🔄 Refresh", parent=self)
        refresh_carriers_btn.clicked.connect(self._refresh_carriers)
        carrier_layout.addWidget(refresh_carriers_btn)
        carrier_layout.addStretch()

        carrier_group.setLayout(carrier_layout)
        layout.addWidget(carrier_group)

        # TTS settings group
        tts_group = QGroupBox("🔊 Text-to-Speech")
        tts_layout = QVBoxLayout()

        # Voice selection
        voice_layout = QHBoxLayout()
        voice_layout.addWidget(QLabel("Voice:"))
        self.voice_combo = QComboBox()
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

        # Speed setting
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Speed:"))
        self.tts_speed_spin = QSpinBox()
        self.tts_speed_spin.setRange(50, 300)
        self.tts_speed_spin.setValue(self.config.get("tts_settings", {}).get("speed", 150))
        self.tts_speed_spin.valueChanged.connect(self._on_tts_speed_changed)
        speed_layout.addWidget(self.tts_speed_spin)
        speed_layout.addStretch()

        test_btn = create_ed_button("🎤 Test", parent=self)
        test_btn.clicked.connect(self._test_tts)
        speed_layout.addWidget(test_btn)
        tts_layout.addLayout(speed_layout)

        tts_group.setLayout(tts_layout)
        layout.addWidget(tts_group)

        self.tabs.addTab(widget, "⚙️ Config")

    @Slot()
    def _add_material_config_row(self):
        """Add new material configuration row."""
        row = self.config_table.rowCount()
        self.config_table.insertRow(row)

        # Material combo
        material_combo = QComboBox()
        material_combo.addItems(MATERIALS)
        self.config_table.setCellWidget(row, 0, material_combo)

        # Min % spin
        pct_spin = QDoubleSpinBox()
        pct_spin.setRange(0.1, 99.9)
        pct_spin.setValue(25.0)
        pct_spin.setSuffix("%")
        self.config_table.setCellWidget(row, 1, pct_spin)

        # Target price spin
        price_spin = QSpinBox()
        price_spin.setRange(0, 10000000)
        price_spin.setValue(250000)
        price_spin.setSingleStep(10000)
        self.config_table.setCellWidget(row, 2, price_spin)

        # Surface checkbox
        surface_check = QCheckBox()
        surface_check.setChecked(True)
        surface_widget = QWidget()
        surface_layout = QHBoxLayout(surface_widget)
        surface_layout.addWidget(surface_check)
        surface_layout.setAlignment(Qt.AlignCenter)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        self.config_table.setCellWidget(row, 3, surface_widget)

        # Deepcore checkbox
        deepcore_check = QCheckBox()
        deepcore_check.setChecked(True)
        deepcore_widget = QWidget()
        deepcore_layout = QHBoxLayout(deepcore_widget)
        deepcore_layout.addWidget(deepcore_check)
        deepcore_layout.setAlignment(Qt.AlignCenter)
        deepcore_layout.setContentsMargins(0, 0, 0, 0)
        self.config_table.setCellWidget(row, 4, deepcore_widget)

        # Action buttons
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

    def _save_material_config(self, row: int):
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

            self.db.save_material_config(material, min_pct, price, surface, deepcore)
            QMessageBox.information(self, "Success", f"Configuration saved for {material}")
            logger.info(f"Material config saved: {material}")
        except Exception as e:
            logger.error(f"Error saving material config: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def _delete_material_config(self, row: int):
        """Delete material configuration."""
        try:
            material_combo = self.config_table.cellWidget(row, 0)
            material = material_combo.currentText()

            reply = QMessageBox.question(
                self, "Confirm Delete",
                f"Delete configuration for {material}?",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.db.delete_material_config(material)
                self.config_table.removeRow(row)
                logger.info(f"Material config deleted: {material}")
        except Exception as e:
            logger.error(f"Error deleting material config: {e}")

    def _load_material_configs(self):
        """Load existing material configurations from database."""
        try:
            configs = self.db.get_material_config()
            for config in configs:
                row = self.config_table.rowCount()
                self.config_table.insertRow(row)

                # Material
                material_combo = QComboBox()
                material_combo.addItems(MATERIALS)
                material_combo.setCurrentText(config['material_name'])
                self.config_table.setCellWidget(row, 0, material_combo)

                # Min %
                pct_spin = QDoubleSpinBox()
                pct_spin.setRange(0.1, 99.9)
                pct_spin.setValue(config['min_percentage'])
                pct_spin.setSuffix("%")
                self.config_table.setCellWidget(row, 1, pct_spin)

                # Price
                price_spin = QSpinBox()
                price_spin.setRange(0, 10000000)
                price_spin.setValue(config['target_price'])
                price_spin.setSingleStep(10000)
                self.config_table.setCellWidget(row, 2, price_spin)

                # Surface
                surface_check = QCheckBox()
                surface_check.setChecked(bool(config['track_surface']))
                surface_widget = QWidget()
                surface_layout = QHBoxLayout(surface_widget)
                surface_layout.addWidget(surface_check)
                surface_layout.setAlignment(Qt.AlignCenter)
                surface_layout.setContentsMargins(0, 0, 0, 0)
                self.config_table.setCellWidget(row, 3, surface_widget)

                # Deepcore
                deepcore_check = QCheckBox()
                deepcore_check.setChecked(bool(config['track_deepcore']))
                deepcore_widget = QWidget()
                deepcore_layout = QHBoxLayout(deepcore_widget)
                deepcore_layout.addWidget(deepcore_check)
                deepcore_layout.setAlignment(Qt.AlignCenter)
                deepcore_layout.setContentsMargins(0, 0, 0, 0)
                self.config_table.setCellWidget(row, 4, deepcore_widget)

                # Action buttons
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

    def _refresh_carriers(self):
        """Refresh fleet carriers list."""
        try:
            carriers = self.db.get_fleet_carriers()
            current_carrier = self.config.get("fleet_carrier")

            self.carrier_combo.clear()
            self.carrier_combo.addItem("None", None)

            for carrier in carriers:
                signal_name = carrier['signal_name']
                self.carrier_combo.addItem(signal_name, signal_name)

            # Restore selection
            if current_carrier:
                index = self.carrier_combo.findData(current_carrier)
                if index >= 0:
                    self.carrier_combo.setCurrentIndex(index)

            logger.info(f"Loaded {len(carriers)} fleet carriers")
        except Exception as e:
            logger.error(f"Error refreshing carriers: {e}")

    def _on_carrier_changed(self, index: int):
        """Handle fleet carrier selection change."""
        if index >= 0:
            carrier_name = self.carrier_combo.itemData(index)
            self.config["fleet_carrier"] = carrier_name
            save_config(self.config)
            logger.info(f"Fleet carrier set to: {carrier_name}")

    def _on_voice_changed(self, index: int):
        """Handle TTS voice change."""
        if index >= 0:
            voice_id = self.voice_combo.itemData(index)
            if voice_id:
                self.tts.set_voice(voice_id)
                logger.info(f"Voice changed to: {self.voice_combo.currentText()}")

    def _on_tts_speed_changed(self, value: int):
        """Handle TTS speed change."""
        self.tts.set_speed(value)
        # Save to config
        if "tts_settings" not in self.config:
            self.config["tts_settings"] = {}
        self.config["tts_settings"]["speed"] = value
        save_config(self.config)

    @Slot()
    def _test_tts(self):
        """Test TTS voice."""
        self.tts.speak("Text to speech test. Platinum found at seventy-five percent.")

    # ========================================================================
    # ENGINE TAB
    # ========================================================================
    def _create_engine_tab(self):
        """Create engine tab for log reader control."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Log path group
        log_group = QGroupBox("🚀 Elite Dangerous Log Path")
        log_layout = QVBoxLayout()

        path_layout = QHBoxLayout()
        self.log_path_input = QLineEdit(self.log_path)
        path_layout.addWidget(self.log_path_input)

        browse_btn = create_ed_button("Browse...", parent=self)
        browse_btn.clicked.connect(self._browse_log_path)
        path_layout.addWidget(browse_btn)

        log_layout.addLayout(path_layout)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # Service control group
        service_group = QGroupBox("⚙️ Log Reader Service")
        service_layout = QVBoxLayout()

        self.service_status_label = QLabel("Status: Checking...")
        self.service_status_label.setStyleSheet(f"color: {ED_WARNING};")
        service_layout.addWidget(self.service_status_label)

        btn_layout = QHBoxLayout()
        self.start_service_btn = create_ed_button("▶️ Start", parent=self)
        self.start_service_btn.clicked.connect(self._start_log_reader)
        btn_layout.addWidget(self.start_service_btn)

        self.stop_service_btn = create_ed_button("⏹️ Stop", parent=self)
        self.stop_service_btn.clicked.connect(self._stop_log_reader)
        btn_layout.addWidget(self.stop_service_btn)

        self.restart_service_btn = create_ed_button("🔄 Restart", parent=self)
        self.restart_service_btn.clicked.connect(self._restart_log_reader)
        btn_layout.addWidget(self.restart_service_btn)

        service_layout.addLayout(btn_layout)
        service_group.setLayout(service_layout)
        layout.addWidget(service_group)

        # Game state group
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

    @Slot()
    def _browse_log_path(self):
        """Browse for log directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Elite Dangerous Log Directory", self.log_path
        )
        if directory:
            self.log_path = directory
            self.log_path_input.setText(directory)

    @Slot()
    def _start_log_reader(self):
        """Start log reader service."""
        log_path = self.log_path_input.text()
        if self.log_reader_manager.start(log_path):
            self.service_status_label.setText("Status: ✅ Running")
            self.service_status_label.setStyleSheet(f"color: {ED_SUCCESS};")
            self.tts.speak("Log reader started")
        else:
            self.service_status_label.setText("Status: ❌ Failed to start")
            self.service_status_label.setStyleSheet(f"color: {ED_ERROR};")
            QMessageBox.critical(self, "Error", "Failed to start log reader")

    @Slot()
    def _stop_log_reader(self):
        """Stop log reader service."""
        if self.log_reader_manager.stop():
            self.service_status_label.setText("Status: ⏹️ Stopped")
            self.service_status_label.setStyleSheet(f"color: {ED_WARNING};")
            self.tts.speak("Log reader stopped")
        else:
            QMessageBox.warning(self, "Warning", "Failed to stop log reader")

    @Slot()
    def _restart_log_reader(self):
        """Restart log reader service."""
        log_path = self.log_path_input.text()
        if self.log_reader_manager.restart(log_path):
            self.service_status_label.setText("Status: ✅ Restarted")
            self.service_status_label.setStyleSheet(f"color: {ED_SUCCESS};")
            self.tts.speak("Log reader restarted")
        else:
            QMessageBox.critical(self, "Error", "Failed to restart log reader")

    def _check_log_reader_status(self):
        """Check log reader service status."""
        if self.log_reader_manager.is_running():
            self.service_status_label.setText("Status: ✅ Running")
            self.service_status_label.setStyleSheet(f"color: {ED_SUCCESS};")
        else:
            self.service_status_label.setText("Status: ⏹️ Not Running")
            self.service_status_label.setStyleSheet(f"color: {ED_WARNING};")

    # ========================================================================
    # STATIONS TAB
    # ========================================================================
    def _create_stations_tab(self):
        """Create stations tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        header = QLabel("🚉 Stations")
        header.setStyleSheet(f"color: {ED_ORANGE}; font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        self.stations_table = create_ed_table(
            column_count=4,
            headers=["Name", "Type", "Address", "Last Seen"],
            parent=self
        )
        layout.addWidget(self.stations_table)

        self.tabs.addTab(widget, "🚉 Stations")

    # ========================================================================
    # FLEET CARRIERS TAB
    # ========================================================================
    def _create_fc_tab(self):
        """Create fleet carriers tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        header = QLabel("🚢 Fleet Carriers")
        header.setStyleSheet(f"color: {ED_ORANGE}; font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        self.fc_table = create_ed_table(
            column_count=4,
            headers=["Name", "Address", "Last Seen", "Discovered"],
            parent=self
        )
        layout.addWidget(self.fc_table)

        self.tabs.addTab(widget, "🚢 FC")

    def _refresh_stations_tables(self):
        """Refresh stations and FC tables."""
        try:
            # Fleet carriers
            carriers = self.db.get_fleet_carriers()
            self.fc_table.setRowCount(len(carriers))
            for i, carrier in enumerate(carriers):
                self.fc_table.setItem(i, 0, QTableWidgetItem(carrier.get('signal_name', '')))
                self.fc_table.setItem(i, 1, QTableWidgetItem(str(carrier.get('system_address', ''))))
                self.fc_table.setItem(i, 2, QTableWidgetItem(carrier.get('last_seen', '')))
                self.fc_table.setItem(i, 3, QTableWidgetItem(carrier.get('discovered_timestamp', '')))

            # Stations
            stations = self.db.get_stations()
            self.stations_table.setRowCount(len(stations))
            for i, station in enumerate(stations):
                self.stations_table.setItem(i, 0, QTableWidgetItem(station.get('signal_name', '')))
                self.stations_table.setItem(i, 1, QTableWidgetItem(station.get('signal_type', '')))
                self.stations_table.setItem(i, 2, QTableWidgetItem(str(station.get('system_address', ''))))
                self.stations_table.setItem(i, 3, QTableWidgetItem(station.get('last_seen', '')))

            logger.info(f"Refreshed: {len(stations)} stations, {len(carriers)} fleet carriers")
        except Exception as e:
            logger.error(f"Error refreshing stations/FC: {e}")

    # ========================================================================
    # UPDATE DATA (CALLED BY TIMER)
    # ========================================================================
    @Slot()
    def _update_data(self):
        """Update all data from database (called by timer)."""
        try:
            # Update game state
            state = self.db.get_game_state()
            self.cmdr_label.setText(state.get('commander_name', 'Unknown'))
            self.system_label.setText(state.get('current_system', 'Unknown'))
            self.system_sidebar_label.setText(state.get('current_system', 'Unknown'))

            # Update ship status
            self._update_ship_status()

            # Update asteroids
            self._update_asteroids()

            # Update statistics
            self._update_statistics()
        except Exception as e:
            logger.error(f"Error updating data: {e}")

    def _update_ship_status(self):
        """Update ship status (cargo, limpets, credits)."""
        try:
            status = self.db.get_ship_status()

            # Credits
            credits = status.get('commander_credits', 0)
            self.credits_label.setText(format_credits(credits))

            # Cargo
            capacity = status.get('cargo_capacity', 0)
            count = status.get('cargo_count', 0)
            cargo_pct = (count / max(1, capacity)) * 100

            self.cargo_label.setText(f"{count} / {capacity} ({cargo_pct:.0f}%)")
            self.cargo_progress.setValue(int(cargo_pct))

            # Color code cargo bar
            if cargo_pct >= 90:
                color = ED_ERROR
            elif cargo_pct >= 75:
                color = ED_WARNING
            else:
                color = ED_SUCCESS
            self.cargo_progress.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }}")

            # Limpets
            limpets = status.get('limpet_count', 0)
            self.limpets_label.setText(f"{limpets} remaining")

            # Assume max 100 limpets for progress bar
            limpet_pct = min(100, (limpets / 100) * 100)
            self.limpets_progress.setValue(int(limpet_pct))

            # Color code limpets
            if limpets < 10:
                color = ED_ERROR
            elif limpets < 25:
                color = ED_WARNING
            else:
                color = ED_SUCCESS
            self.limpets_progress.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }}")
        except Exception as e:
            logger.error(f"Error updating ship status: {e}")

    def _update_asteroids(self):
        """Update asteroid detections."""
        try:
            asteroids = self.db.get_unprocessed_asteroids()

            # Get desired materials from config
            desired_materials = self._get_desired_materials()

            for asteroid in asteroids:
                material = asteroid.get('material_name', '')
                percentage = asteroid.get('percentage', 0.0)

                # Check if material is in desired list and meets min %
                should_display = False
                for config_row in range(self.config_table.rowCount()):
                    material_combo = self.config_table.cellWidget(config_row, 0)
                    pct_spin = self.config_table.cellWidget(config_row, 1)

                    if material_combo and material_combo.currentText() == material:
                        if percentage >= pct_spin.value():
                            should_display = True
                            break

                if should_display or not desired_materials:
                    # Add to table
                    row = self.detection_table.rowCount()
                    self.detection_table.insertRow(row)

                    # Timestamp
                    ts = asteroid.get('timestamp', '')
                    self.detection_table.setItem(row, 0, QTableWidgetItem(str(ts)))

                    # Material
                    mat_item = QTableWidgetItem(material)
                    mat_item.setForeground(QColor(ED_ORANGE))
                    self.detection_table.setItem(row, 1, mat_item)

                    # Percentage
                    pct_item = QTableWidgetItem(f"{percentage:.1f}%")
                    if percentage >= 50:
                        pct_item.setForeground(QColor(ED_SUCCESS))
                    self.detection_table.setItem(row, 2, pct_item)

                    # Progress bar
                    progress_widget = QWidget()
                    progress_layout = QHBoxLayout(progress_widget)
                    progress_layout.setContentsMargins(0, 0, 0, 0)
                    progress_bar = QProgressBar()
                    progress_bar.setRange(0, 100)
                    progress_bar.setValue(int(percentage))
                    progress_layout.addWidget(progress_bar)
                    self.detection_table.setCellWidget(row, 3, progress_widget)

                    # Surface/Deepcore
                    self.detection_table.setItem(row, 4, QTableWidgetItem("✓" if asteroid.get('is_surface') else ""))
                    self.detection_table.setItem(row, 5, QTableWidgetItem("✓" if asteroid.get('is_deepcore') else ""))

                    # Content level
                    content = asteroid.get('content_level', '')
                    self.detection_table.setItem(row, 6, QTableWidgetItem(content))

                    # TTS announcement
                    if percentage >= 50:
                        self.tts.speak(f"{material} found at {int(percentage)} percent")

                # Mark as processed
                self.db.mark_asteroid_processed(asteroid['id'])
        except Exception as e:
            logger.error(f"Error updating asteroids: {e}")

    def _get_desired_materials(self) -> Set[str]:
        """Get set of desired material names from config table."""
        desired = set()
        try:
            for row in range(self.config_table.rowCount()):
                material_combo = self.config_table.cellWidget(row, 0)
                if material_combo:
                    desired.add(material_combo.currentText())
        except Exception as e:
            logger.error(f"Error getting desired materials: {e}")
        return desired

    def _update_statistics(self):
        """Update session statistics."""
        try:
            # Get refined materials count
            refined_count = self.db.get_refined_materials_count()
            self.rocks_mined_label.setText(str(refined_count))

            # TODO: Calculate hourly profit and session duration
            # This requires tracking session start time and material prices
        except Exception as e:
            logger.error(f"Error updating statistics: {e}")

    # ========================================================================
    # CLOSE EVENT
    # ========================================================================
    def closeEvent(self, event):
        """Handle window close."""
        logger.info("Mining Scanner closing")
        self.stop_updates()
        self.stations_timer.stop()
        self.tts.close()
        super().closeEvent(event)


# ============================================================================
# STANDALONE EXECUTION
# ============================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    app = QApplication(sys.argv)
    app.setApplicationName("ED Mining Scanner")

    window = MiningScannerUI()
    window.show()

    sys.exit(app.exec())
