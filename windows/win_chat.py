#!/usr/bin/env python3
"""
ED Chat Monitor - Refactored with centralized managers.
Inherits from EDBaseWindow, uses database_manager for all DB operations.

Features:
- Real-time chat message display from journal
- Icon-coded message types (Security, Pirates, System, Squadron, Friends)
- Per-message TTS toggle
- Visual separators between message type changes
- Auto-scroll to newest messages
"""

import sys
import logging
from typing import List, Dict, Any

from core.core_ui import QApplication, QMainWindow, QMessageBox, QMdiArea, Qt

from core.core_database import get_db
from utilities.util_tts import TTSHandler


logger = logging.getLogger(__name__)

# ============================================================================
# CHAT TYPE CONFIGURATION - Icons and colors for different message types
# ============================================================================
CHAT_TYPES = {
    "sec": {
        "icon": "🛡️",
        "color": "#00BFFF",  # Light blue for security forces
        "label": "Security"
    },
    "pirate": {
        "icon": "🏴\u200d☠️",
        "color": "#FF4500",  # Orange-red for pirates
        "label": "Pirate"
    },
    "system": {
        "icon": "⚙️",
        "color": "#FFFF00",  # Yellow for system messages
        "label": "System"
    },
    "sq": {
        "icon": "🛩️",
        "color": "#9370DB",  # Purple for squadron
        "label": "Squadron"
    },
    "friends": {
        "icon": "👥",
        "color": "#32CD32",  # Green for friends
        "label": "Friends"
    },
    "other": {
        "icon": "👤",
        "color": "#A9A9A9",  # Gray for other/generic
        "label": "Other"
    }
}


# ============================================================================
# CHAT MONITOR WINDOW
# ============================================================================
class ChatMonitor(EDBaseWindow):
    """
    Chat monitor window - displays chat messages from journal with icons.
    Inherits from EDBaseWindow for automatic theming and timer management.
    """

    def __init__(self):
        # Get config for update interval
        config = load_config()
        chat_settings = config.get("chat_settings", {})
        poll_interval = chat_settings.get("poll_interval_ms", 2000)

        # Initialize base window
        super().__init__(
            app_name="Chat Monitor",
            window_size=(500, 700),
            update_interval_ms=poll_interval
        )

        # Database and TTS
        self.db = get_db()
        self.tts = TTSHandler()

        # Track last seen timestamp
        self.last_timestamp = "1970-01-01T00:00:00Z"

        # Track last message type for separator insertion
        self.last_message_type = None

        # Create UI
        self._create_ui()

        # Optional: Clear chat on startup
        if chat_settings.get("auto_clear_on_start", True):
            self._clear_chat()

        # Start update timer
        self.start_updates()

        logger.info("Chat Monitor initialized")

    def _create_ui(self):
        """Create the chat monitor UI."""
        # Central widget and layout
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Title
        title = QLabel("💬 Elite Dangerous Chat Monitor")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet(f"color: {ED_ORANGE}; padding: 5px;")
        layout.addWidget(title)

        # Chat table with 4 columns
        self.chat_table = create_ed_table(
            column_count=4,
            headers=["Channel - Sender", "Message", "TTS", ""],
            parent=self
        )

        # Set column widths
        self.chat_table.setColumnWidth(0, 200)  # Channel - Sender
        self.chat_table.setColumnWidth(2, 50)   # TTS checkbox
        self.chat_table.setColumnWidth(3, 30)   # Spacer

        # Column 1 (Message) stretches
        self.chat_table.horizontalHeader().setStretchLastSection(False)
        #self.chat_table.horizontalHeader().setSectionResizeMode(1, self.chat_table.horizontalHeader().Stretch)

        # Then in your code:
        self.chat_table.horizontalHeader().setSectionResizeMode(1, 
            QHeaderView.ResizeMode.Stretch)


        layout.addWidget(self.chat_table)

        # Bottom button bar
        button_layout = QHBoxLayout()

        clear_btn = QPushButton("🗑️ Clear Chat")
        clear_btn.clicked.connect(self._clear_chat)
        button_layout.addWidget(clear_btn)

        button_layout.addStretch()

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #00FF00;")
        button_layout.addWidget(self.status_label)

        layout.addLayout(button_layout)

        self.setCentralWidget(central)

    @Slot()
    def _update_data(self):
        """
        Update chat messages from database (called by timer).
        Overrides EDBaseWindow._update_data().
        """
        try:
            # Get new messages since last timestamp
            messages = self.db.get_new_chat_messages(self.last_timestamp)

            if not messages:
                return

            # Process messages (newest at bottom)
            for msg in messages:
                self._add_message_to_table(msg)
                self.last_timestamp = msg["journal_timestamp"]

            # Auto-scroll to bottom
            self.chat_table.scrollToBottom()

            # Update status
            total_rows = self.chat_table.rowCount()
            self.status_label.setText(f"{len(messages)} new | {total_rows} total")

        except Exception as e:
            logger.error(f"Error updating chat: {e}")
            self.status_label.setText(f"Error: {e}")
            self.status_label.setStyleSheet("color: #FF0000;")

    def _add_message_to_table(self, msg: Dict[str, Any]):
        """Add a single message to the table with formatting."""
        subtype = msg.get("subtype", "other")
        chat_type = CHAT_TYPES.get(subtype, CHAT_TYPES["other"])

        # Insert spacer row if message type changed
        if self.last_message_type and self.last_message_type != subtype:
            self._insert_spacer_row()

        self.last_message_type = subtype

        # Insert new row at bottom
        row = self.chat_table.rowCount()
        self.chat_table.insertRow(row)

        # Column 0: Icon + Channel - Sender
        icon = chat_type["icon"]
        channel = msg.get("channel", "unknown").upper()
        sender = msg.get("from_localised", "Unknown")

        from PySide6.QtWidgets import QTableWidgetItem

        col0_item = QTableWidgetItem(f"{icon} {channel} - {sender}")
        col0_item.setForeground(QColor(chat_type["color"]))
        col0_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.chat_table.setItem(row, 0, col0_item)

        # Column 1: Message text
        message_text = msg.get("message_localised", "")
        col1_item = QTableWidgetItem(message_text)
        col1_item.setForeground(QColor("white"))
        self.chat_table.setItem(row, 1, col1_item)

        # Column 2: TTS checkbox (centered widget)
        tts_checkbox = QCheckBox()
        tts_checkbox.setChecked(True)
        tts_checkbox.toggled.connect(
            lambda checked, m=message_text: self._on_tts_toggled(m, checked)
        )

        # Center the checkbox in cell
        tts_widget = QWidget()
        tts_layout = QHBoxLayout(tts_widget)
        tts_layout.addWidget(tts_checkbox)
        tts_layout.setAlignment(Qt.AlignCenter)
        tts_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_table.setCellWidget(row, 2, tts_widget)

        # Column 3: Empty spacer
        col3_item = QTableWidgetItem("")
        self.chat_table.setItem(row, 3, col3_item)

    def _insert_spacer_row(self):
        """Insert a visual spacer row between different message types."""
        row = self.chat_table.rowCount()
        self.chat_table.insertRow(row)

        from PySide6.QtWidgets import QTableWidgetItem

        # Create merged spacer cell
        spacer_item = QTableWidgetItem("")
        spacer_item.setBackground(QColor(ED_GRAY))
        self.chat_table.setItem(row, 0, spacer_item)

        # Merge all columns for spacer
        self.chat_table.setSpan(row, 0, 1, 4)

        # Set row height smaller
        self.chat_table.setRowHeight(row, 5)

    def _on_tts_toggled(self, message: str, checked: bool):
        """Handle TTS checkbox toggle."""
        if checked:
            self.tts.speak(message)
            logger.debug(f"TTS: {message[:50]}...")

    @Slot()
    def _clear_chat(self):
        """Clear all chat messages from database and table."""
        try:
            self.db.clear_chat_messages()
            self.chat_table.setRowCount(0)
            self.last_timestamp = "1970-01-01T00:00:00Z"
            self.last_message_type = None
            self.status_label.setText("Chat cleared")
            logger.info("Chat cleared")
        except Exception as e:
            logger.error(f"Error clearing chat: {e}")
            self.status_label.setText(f"Clear failed: {e}")
            self.status_label.setStyleSheet("color: #FF0000;")

    def closeEvent(self, event):
        """Handle window close - cleanup resources."""
        logger.info("Chat Monitor closing")
        self.stop_updates()
        self.tts.close()
        super().closeEvent(event)


# ============================================================================
# STANDALONE EXECUTION
# ============================================================================
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    app = QApplication(sys.argv)
    app.setApplicationName("ED Chat Monitor")

    window = ChatMonitor()
    window.show()

    sys.exit(app.exec())
