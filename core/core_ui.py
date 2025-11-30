"""
UI Manager - Centralized UI styling and Qt imports
All Qt imports in one place for easy maintenance and consistency
"""

from typing import List, Optional, Tuple
import logging

# ============================================================================
# CENTRALIZED QT IMPORTS - Import from here in all UI files!
# ============================================================================

# Core Qt Widgets
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QRadioButton, QSlider, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QTabWidget, QGroupBox, QFrame, QSplitter,
    QMenuBar, QMenu, QToolBar, QStatusBar,
    QFileDialog, QMessageBox, QInputDialog, QColorDialog,
    QScrollArea, QDockWidget, QMdiArea, QMdiSubWindow
)

# Qt Core
from PySide6.QtCore import (
    Qt, QTimer, QThread, Signal, Slot,
    QUrl, QSettings, QSize, QPoint, QRect,
    QDateTime, QDate, QTime
)

# Qt GUI
from PySide6.QtGui import (
    QColor, QFont, QPalette, QBrush, QPen,
    QIcon, QPixmap, QImage, QPainter,
    QDesktopServices, QKeySequence, QAction
)

# Import database manager for config loading
from database_manager import load_config

# Setup logger
logger = logging.getLogger(__name__)

# ============================================================================
# ED THEME COLORS
# ============================================================================

ED_ORANGE = "#FF7700"
ED_DARK = "#0D0D0D"
ED_GRAY = "#2A2A2A"
ED_LIGHT_GRAY = "#3D3D3D"
ED_SUCCESS = "#00FF00"  # Fixed: was _colors.get(...)
ED_ERROR = "#FF0000"     # Fixed: was _colors.get(...)
ED_WARNING = "#FFAA00"   # Fixed: was _colors.get(...)

# ============================================================================
# STYLESHEET GENERATORS
# ============================================================================

def get_base_stylesheet() -> str:
    """Get base application stylesheet with ED theme."""
    return f"""
        QMainWindow {{
            background-color: {ED_DARK};
            color: white;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 10pt;
        }}
        
        QWidget {{
            background-color: {ED_DARK};
            color: white;
        }}
        
        QLabel {{
            color: white;
            padding: 2px;
        }}
        
        QPushButton {{
            background-color: {ED_GRAY};
            color: white;
            border: 1px solid {ED_ORANGE};
            border-radius: 3px;
            padding: 5px 15px;
            font-weight: bold;
        }}
        
        QPushButton:hover {{
            background-color: {ED_ORANGE};
            border-color: white;
        }}
        
        QPushButton:pressed {{
            background-color: #CC5500;
        }}
        
        QPushButton:disabled {{
            background-color: #2A2A2A;
            border-color: #555555;
            color: #666666;
        }}
        
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {{
            background-color: {ED_GRAY};
            color: white;
            border: 1px solid {ED_ORANGE};
            border-radius: 3px;
            padding: 3px;
            selection-background-color: {ED_ORANGE};
        }}
        
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
            border-color: white;
            border-width: 2px;
        }}
        
        QComboBox::drop-down {{
            border: none;
            background: {ED_ORANGE};
        }}
        
        QComboBox::down-arrow {{
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid white;
            margin-right: 5px;
        }}
        
        QTabWidget::pane {{
            border: 1px solid {ED_ORANGE};
            background-color: {ED_DARK};
        }}
        
        QTabBar::tab {{
            background-color: {ED_GRAY};
            color: white;
            border: 1px solid {ED_ORANGE};
            border-bottom: none;
            padding: 8px 20px;
            margin-right: 2px;
        }}
        
        QTabBar::tab:selected {{
            background-color: {ED_ORANGE};
            font-weight: bold;
        }}
        
        QTabBar::tab:hover {{
            background-color: #CC5500;
        }}
        
        QProgressBar {{
            border: 1px solid {ED_ORANGE};
            border-radius: 3px;
            text-align: center;
            background-color: {ED_GRAY};
            color: white;
            font-weight: bold;
        }}
        
        QProgressBar::chunk {{
            background-color: {ED_ORANGE};
        }}
        
        QGroupBox {{
            border: 1px solid {ED_ORANGE};
            border-radius: 5px;
            margin-top: 1ex;
            font-weight: bold;
            color: {ED_ORANGE};
        }}
        
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            color: {ED_ORANGE};
        }}
        
        QCheckBox {{
            color: white;
            spacing: 5px;
        }}
        
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {ED_ORANGE};
            border-radius: 3px;
            background-color: {ED_GRAY};
        }}
        
        QCheckBox::indicator:checked {{
            background-color: {ED_ORANGE};
            image: none;
        }}
        
        QCheckBox::indicator:hover {{
            border-color: white;
        }}
        
        QScrollBar:vertical {{
            border: none;
            background-color: {ED_DARK};
            width: 12px;
            margin: 0;
        }}
        
        QScrollBar::handle:vertical {{
            background-color: {ED_ORANGE};
            min-height: 20px;
            border-radius: 6px;
        }}
        
        QScrollBar::handle:vertical:hover {{
            background-color: white;
        }}
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        
        QScrollBar:horizontal {{
            border: none;
            background-color: {ED_DARK};
            height: 12px;
            margin: 0;
        }}
        
        QScrollBar::handle:horizontal {{
            background-color: {ED_ORANGE};
            min-width: 20px;
            border-radius: 6px;
        }}
        
        QScrollBar::handle:horizontal:hover {{
            background-color: white;
        }}
        
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        
        QMenuBar {{
            background-color: {ED_DARK};
            color: white;
            border-bottom: 1px solid {ED_ORANGE};
        }}
        
        QMenuBar::item {{
            background-color: transparent;
            padding: 4px 10px;
        }}
        
        QMenuBar::item:selected {{
            background-color: {ED_ORANGE};
        }}
        
        QMenu {{
            background-color: {ED_GRAY};
            color: white;
            border: 1px solid {ED_ORANGE};
        }}
        
        QMenu::item:selected {{
            background-color: {ED_ORANGE};
        }}
    """


def get_table_stylesheet() -> str:
    """Get stylesheet specifically for QTableWidget."""
    return f"""
        QTableWidget {{
            background-color: {ED_DARK};
            color: white;
            gridline-color: {ED_GRAY};
            border: 1px solid {ED_ORANGE};
            selection-background-color: {ED_ORANGE};
            selection-color: white;
        }}
        
        QTableWidget::item {{
            padding: 5px;
        }}
        
        QTableWidget::item:alternate {{
            background-color: #1A1A1A;
        }}
        
        QHeaderView::section {{
            background-color: {ED_ORANGE};
            color: white;
            padding: 5px;
            border: 1px solid {ED_DARK};
            font-weight: bold;
        }}
        
        QHeaderView::section:hover {{
            background-color: white;
            color: {ED_DARK};
        }}
    """


# ============================================================================
# WIDGET FACTORY FUNCTIONS
# ============================================================================

def create_ed_table(column_count: int, headers: List[str], parent=None) -> QTableWidget:
    """
    Create a styled QTableWidget with ED theme.
    
    Args:
        column_count: Number of columns
        headers: List of header labels
        parent: Parent widget
    
    Returns:
        Configured QTableWidget
    """
    table = QTableWidget(parent)
    table.setColumnCount(column_count)
    table.setHorizontalHeaderLabels(headers)
    
    # Styling
    table.setStyleSheet(get_table_stylesheet())
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    
    # Header stretch
    header = table.horizontalHeader()
    for i in range(column_count):
        if i == column_count - 1:
            header.setStretchLastSection(True)
        else:
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
    
    return table


def create_ed_button(text: str, icon: str = "", parent=None) -> QPushButton:
    """Create a styled QPushButton with ED theme."""
    btn_text = f"{icon} {text}" if icon else text
    btn = QPushButton(btn_text, parent)
    # Stylesheet is applied via base theme
    return btn


def create_ed_progress_bar(min_val: int = 0, max_val: int = 100,
                           parent=None) -> QProgressBar:
    """Create a styled QProgressBar with ED theme."""
    bar = QProgressBar(parent)
    bar.setMinimum(min_val)
    bar.setMaximum(max_val)
    bar.setTextVisible(True)
    # Stylesheet is applied via base theme
    return bar


def create_ed_label(text: str, font_size: int = 10, bold: bool = False,
                    color: Optional[str] = None, parent=None) -> QLabel:
    """Create a styled QLabel with ED theme."""
    label = QLabel(text, parent)
    font = QFont("Segoe UI", font_size)
    if bold:
        font.setBold(True)
    label.setFont(font)
    if color:
        label.setStyleSheet(f"color: {color};")
    return label


# ============================================================================
# BASE WINDOW CLASS
# ============================================================================

class EDBaseWindow(QMainWindow):
    """
    Base window class for all ED Mining Suite windows.
    
    Provides:
    - Automatic ED theme application
    - Config-driven settings
    - Common update timer
    - Logging
    """
    
    def __init__(self, app_name: str = "ED App",
                 window_size: Optional[Tuple[int, int]] = None,
                 update_interval_ms: Optional[int] = None):
        """
        Initialize base ED window.
        
        Args:
            app_name: Window title suffix
            window_size: (width, height) or None for config default
            update_interval_ms: Update timer interval or None for config default
        """
        super().__init__()
        
        self.app_name = app_name
        self.config = load_config()
        
        # Setup window
        self.setWindowTitle(f"ED Mining Suite - {app_name}")
        
        # Size
        if window_size:
            width, height = window_size
        else:
            ui_settings = self.config.get("ui_settings", {})
            width = ui_settings.get("window_width", 1200)
            height = ui_settings.get("window_height", 800)
        
        self.resize(width, height)
        
        # Apply ED theme
        self.setStyleSheet(get_base_stylesheet())
        
        # Setup update timer (subclasses override _update_data)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_data)
        
        if update_interval_ms is None:
            update_interval_ms = self.config.get("ui_settings", {}).get("update_interval_ms", 1000)
        
        self.update_interval_ms = update_interval_ms
        logger.info(f"{app_name} window initialized")
    
    def _update_data(self):
        """
        Override this method in subclasses to update UI from database.
        Called by update_timer on interval.
        """
        pass
    
    def start_updates(self):
        """Start the update timer."""
        if not self.update_timer.isActive():
            self.update_timer.start(self.update_interval_ms)
            logger.debug(f"{self.app_name}: Update timer started ({self.update_interval_ms}ms)")
    
    def stop_updates(self):
        """Stop the update timer."""
        if self.update_timer.isActive():
            self.update_timer.stop()
            logger.debug(f"{self.app_name}: Update timer stopped")
    
    def get_color(self, color_name: str, default: str = "#FFFFFF") -> str:
        """Get color from config by name."""
        return self.config.get("colors", {}).get(color_name, default)
    
    def get_setting(self, section: str, key: str, default: any = None) -> any:
        """Get setting from config."""
        return self.config.get(section, {}).get(key, default)
    
    def closeEvent(self, event):
        """Handle window close - stop timers."""
        self.stop_updates()
        logger.info(f"{self.app_name} window closed")
        super().closeEvent(event)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def format_credits(credits: int) -> str:
    """Format credits with thousand separators."""
    return f"{credits:,} Cr"


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format percentage value."""
    return f"{value:.{decimals}f}%"


def get_progress_bar_color(percentage: float,
                           warn_threshold: float = 75.0,
                           critical_threshold: float = 90.0) -> str:
    """
    Get color for progress bar based on percentage.
    
    Args:
        percentage: Current percentage (0-100)
        warn_threshold: Warning color threshold
        critical_threshold: Critical/error color threshold
    
    Returns:
        Color hex string
    """
    if percentage >= critical_threshold:
        return ED_ERROR
    elif percentage >= warn_threshold:
        return ED_WARNING
    else:
        return ED_SUCCESS


def set_table_row_color(table: QTableWidget, row: int, color: str):
    """Set background color for entire table row."""
    for col in range(table.columnCount()):
        item = table.item(row, col)
        if item:
            item.setBackground(QColor(color))


def set_table_cell_color(table: QTableWidget, row: int, col: int,
                         fg_color: Optional[str] = None,
                         bg_color: Optional[str] = None):
    """Set foreground and/or background color for table cell."""
    item = table.item(row, col)
    if item:
        if fg_color:
            item.setForeground(QColor(fg_color))
        if bg_color:
            item.setBackground(QColor(bg_color))
