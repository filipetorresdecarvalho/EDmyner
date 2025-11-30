#!/usr/bin/env python3
"""
ED Window Manager - Centralized launcher with MDI interface.
"""

import sys
import os
import shutil
import time
import subprocess
import traceback
from pathlib import Path

from core.core_ui import QApplication, QMainWindow, QMessageBox, QMdiArea, Qt

from core.core_database import (
    DATA_DIR, DB_PATH, CONFIG_PATH, init_db, load_config, get_db
)

from windows.win_mining import MiningScannerUI
from windows.win_chat import ChatMonitor


class DataSetup:
    @staticmethod
    def init():
        DATA_DIR.mkdir(exist_ok=True)
        root_config = Path("ed_mining_config.json")
        if root_config.exists() and not CONFIG_PATH.exists():
            shutil.move(root_config, CONFIG_PATH)


class Checker:
    def __init__(self):
        self.python_ok = False
        self.deps_ok = False
        self.files_ok = False

    def check_python(self) -> bool:
        print("\n1. Python Version:")
        version = sys.version_info
        print(f"   Python {version.major}.{version.minor}.{version.micro}")
        if version.major >= 3 and version.minor >= 8:
            print("   ✓ Version OK")
            self.python_ok = True
            return True
        else:
            print("   ✗ Requires Python 3.8+")
            return False

    def check_deps(self) -> bool:
        print("\n2. Dependencies:")
        required = ["PySide6", "pyttsx3"]
        missing = []
        for dep in required:
            try:
                __import__(dep)
                print(f"   ✓ {dep}")
            except ImportError:
                print(f"   ✗ {dep} - Missing")
                missing.append(dep)
        
        if missing:
            print(f"\n   Install with: pip install {' '.join(missing)}")
            self.deps_ok = False
            return False
        else:
            self.deps_ok = True
            return True

    def check_db_files(self) -> bool:
        print("\n3. Files:")
        db_status = "✓ exists" if DB_PATH.exists() else "⚠ will be created"
        print(f"   DB: {db_status} ({DB_PATH})")
        
        cfg_status = "✓ exists" if CONFIG_PATH.exists() else "⚠ will be created"
        print(f"   Config: {cfg_status} ({CONFIG_PATH})")
        
        files = {
            "ed_mining_scanner.py": "Mining Scanner",
            "ed_chat_monitor.py": "Chat Monitor",
            "ed_log_reader.py": "Log Reader",
            "tts_handler.py": "TTS Handler",
            "database_manager.py": "Database Manager",
            "ui_manager.py": "UI Manager"
        }
        
        for filename, desc in files.items():
            if os.path.exists(filename):
                print(f"   ✓ {desc}: {filename}")
            else:
                print(f"   ✗ {desc}: {filename} - MISSING")
                self.files_ok = False
                return False
        
        self.files_ok = True
        return True

    def validate(self) -> bool:
        print("\n" + "="*50)
        print("ED Mining Suite - System Check")
        print("="*50)
        
        self.check_python()
        self.check_deps()
        self.check_db_files()
        
        print("\n" + "="*50)
        if self.python_ok and self.deps_ok and self.files_ok:
            print("✓ All checks passed - Ready to launch")
            print("="*50 + "\n")
            return True
        else:
            print("✗ Some checks failed - Please fix issues above")
            print("="*50 + "\n")
            return False


class LogLauncher:
    def __init__(self):
        self.process = None
        self.script_path = "ed_log_reader.py"

    def is_running(self) -> bool:
        try:
            db = get_db()
            status = db.get_service_status()
            return bool(status.get('is_running', 0))
        except Exception as e:
            print(f"Error checking log reader status: {e}")
            return False

    def start(self, log_path: str = None) -> bool:
        if self.is_running():
            print("Log reader already running")
            return True
        
        try:
            cmd = [sys.executable, self.script_path]
            if log_path:
                cmd.append(log_path)
            
            if os.name == 'nt':
                self.process = subprocess.Popen(
                    cmd,
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
                )
            else:
                self.process = subprocess.Popen(cmd, start_new_session=True)
            
            time.sleep(1)
            print(f"✓ Log reader started (PID: {self.process.pid})")
            return True
        except Exception as e:
            print(f"✗ Failed to start log reader: {e}")
            return False

    def ensure_started(self):
        if not self.is_running():
            default_path = os.path.join(
                os.path.expanduser("~"),
                "Saved Games",
                "Frontier Developments",
                "Elite Dangerous"
            )
            self.start(default_path)


class WindowManager(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Initialize
        DataSetup.init()
        init_db()
        
        # Setup window
        self.setWindowTitle("ED Mining Suite - Manager")
        self.setMinimumSize(800, 600)
        
        # Apply theme
        config = load_config()
        colors = config.get("colors", {})
        ed_orange = colors.get("ed_orange", "#FF7700")
        ed_dark = colors.get("ed_dark", "#0D0D0D")
        
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {ed_dark};
                color: white;
            }}
            QMenuBar {{
                background-color: {ed_dark};
                color: white;
                border-bottom: 1px solid {ed_orange};
            }}
            QMenuBar::item:selected {{
                background-color: {ed_orange};
            }}
            QMenu {{
                background-color: {ed_dark};
                color: white;
                border: 1px solid {ed_orange};
            }}
            QMenu::item:selected {{
                background-color: {ed_orange};
            }}
            QMdiArea {{
                background-color: {ed_dark};
            }}
        """)
        
        # Window references
        self.scanner_win = None
        self.chat_win = None
        
        # ✅ MDI AREA - Sub-windows stay inside this!
        self.mdi = QMdiArea()
        self.setCentralWidget(self.mdi)
        
        # Log reader
        self.log_launcher = LogLauncher()
        
        # Create menu
        self._create_menu()
        
        # Start log reader
        self.log_launcher.ensure_started()
        
        # Show maximized
        self.showMaximized()
        
        # Status bar
        self.statusBar().showMessage("✓ Log Reader Running | Use Window menu to open tools")
        
        print("\n✓ ED Mining Suite Manager running")
        print("  Press Ctrl+1 for Scanner, Ctrl+2 for Chat\n")

    def _create_menu(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        quit_action = file_menu.addAction("&Quit")
        quit_action.triggered.connect(self.close)
        
        # Window menu
        window_menu = menubar.addMenu("&Window")
        
        scanner_action = window_menu.addAction("&Scanner")
        scanner_action.triggered.connect(self.toggle_scanner)
        scanner_action.setShortcut("Ctrl+1")
        
        chat_action = window_menu.addAction("&Chat")
        chat_action.triggered.connect(self.toggle_chat)
        chat_action.setShortcut("Ctrl+2")
        
        window_menu.addSeparator()
        
        tile_action = window_menu.addAction("&Tile Windows")
        tile_action.triggered.connect(self._tile_windows)
        
        cascade_action = window_menu.addAction("&Cascade Windows")
        cascade_action.triggered.connect(self._cascade_windows)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = help_menu.addAction("&About")
        about_action.triggered.connect(self._show_about)

    def toggle_scanner(self):
        if self.scanner_win:
            self.scanner_win.close()
            self.scanner_win = None
            print("Scanner closed")
        else:
            try:
                scanner = MiningScannerUI()
                
                # ✅ ADD TO MDI AREA
                self.scanner_win = self.mdi.addSubWindow(scanner)
                self.scanner_win.setWindowTitle("📡 Mining Scanner")
                self.scanner_win.resize(1000, 700)
                self.scanner_win.show()
                
                print("Scanner opened")
            except Exception as e:
                QMessageBox.critical(
                    self, "Error",
                    f"Failed to open scanner:\n{e}\n\n{traceback.format_exc()}"
                )

    def toggle_chat(self):
        if self.chat_win:
            self.chat_win.close()
            self.chat_win = None
            print("Chat closed")
        else:
            try:
                chat = ChatMonitor()
                
                # ✅ ADD TO MDI AREA
                self.chat_win = self.mdi.addSubWindow(chat)
                self.chat_win.setWindowTitle("💬 Chat Monitor")
                self.chat_win.resize(600, 500)
                self.chat_win.show()
                
                print("Chat opened")
            except Exception as e:
                QMessageBox.critical(
                    self, "Error",
                    f"Failed to open chat:\n{e}\n\n{traceback.format_exc()}"
                )

    def _tile_windows(self):
        self.mdi.tileSubWindows()
        print("Windows tiled")

    def _cascade_windows(self):
        self.mdi.cascadeSubWindows()
        print("Windows cascaded")

    def _show_about(self):
        QMessageBox.about(
            self,
            "About ED Mining Suite",
            "ED Mining Suite v2.0\n\n"
            "Centralized toolset for Elite Dangerous mining operations\n\n"
            "Features:\n"
            "- Mining Scanner (Ctrl+1)\n"
            "- Chat Monitor (Ctrl+2)\n"
            "- Background log reader service"
        )

    def closeEvent(self, event):
        print("\nShutting down ED Mining Suite...")
        
        if self.scanner_win:
            self.scanner_win.close()
        
        if self.chat_win:
            self.chat_win.close()
        
        print("✓ Shutdown complete\n")
        event.accept()


def main():
    # Run diagnostics
    checker = Checker()
    if not checker.validate():
        print("\nPress Enter to exit...")
        input()
        sys.exit(1)
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("ED Mining Suite")
    app.setOrganizationName("ED Tools")
    
    # Create and show main window
    manager = WindowManager()
    
    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
