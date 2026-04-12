"""
Desktop GUI Application for AutoMeet Attender
Built with PySide6 (Qt for Python)
"""
import sys
import os
import json
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QLabel, QLineEdit, QSpinBox, QCheckBox,
    QTimeEdit, QTableWidget, QTableWidgetItem, QDialog, QFormLayout,
    QTextEdit, QSystemTrayIcon, QMenu, QMessageBox, QHeaderView,
    QFileDialog, QScrollArea, QComboBox, QSlider, QGroupBox, QFrame
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QTime
from PySide6.QtGui import QIcon, QAction
from dotenv import load_dotenv, set_key, find_dotenv
from .scheduler import MeetingScheduler
from .authentication import run_google_authentication


class MeetingWorker(QThread):
    """Worker thread for running meeting joins without blocking UI"""
    log_signal = Signal(str)
    finished_signal = Signal(bool)
    
    def __init__(self, meeting_url, meeting_name):
        super().__init__()
        self.meeting_url = meeting_url
        self.meeting_name = meeting_name
    
    def run(self):
        """Run the meeting join process"""
        try:
            from .meet_joiner import MeetJoiner
            
            load_dotenv()
            config = {
                'headless': os.getenv('HEADLESS', 'false').lower() == 'true',
                'max_retries': int(os.getenv('MAX_RETRY_ATTEMPTS', '3')),
                'retry_delay': int(os.getenv('RETRY_DELAY_SECONDS', '30')),
                'greeting_message': os.getenv('GREETING_MESSAGE', 'Hello everyone'),
                'solo_timeout_minutes': int(os.getenv('SOLO_TIMEOUT_MINUTES', '8')),
                'max_meeting_minutes': int(os.getenv('MAX_MEETING_MINUTES', '240')),
            }
            
            joiner = MeetJoiner(config)
            self.log_signal.emit('🚀 Initializing browser...')
            joiner.initialize()
            
            self.log_signal.emit(f'📞 Joining meeting: {self.meeting_name}')
            success = joiner.join_meeting(self.meeting_url, self.meeting_name)
            
            joiner.close()
            self.finished_signal.emit(success)
        
        except Exception as e:
            self.log_signal.emit(f'❌ Error: {str(e)}')
            self.finished_signal.emit(False)


class MeetingDialog(QDialog):
    """Dialog for adding/editing meetings"""
    
    def __init__(self, parent=None, meeting=None):
        super().__init__(parent)
        self.meeting = meeting
        self.init_ui()
    
    def init_ui(self):
        """Initialize the dialog UI"""
        self.setWindowTitle('Add Meeting' if not self.meeting else 'Edit Meeting')
        self.setMinimumWidth(500)
        
        layout = QFormLayout()
        
        # Meeting name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText('Daily Standup')
        layout.addRow('Meeting Name *:', self.name_input)
        
        # Meeting URL
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText('https://meet.google.com/xxx-yyyy-zzz')
        layout.addRow('Meeting URL *:', self.url_input)
        
        # Schedule time (HH:MM)
        self.schedule_input = QTimeEdit()
        self.schedule_input.setDisplayFormat('HH:mm')
        self.schedule_input.setTime(QTime(9, 0))
        layout.addRow('Schedule (HH:MM) *:', self.schedule_input)
        
        # Help text
        help_label = QLabel('Use 24-hour time, e.g., "09:00" or "18:30". Meeting runs daily at this time.')
        help_label.setStyleSheet('color: gray; font-size: 10px;')
        layout.addRow('', help_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton('Save Meeting')
        save_btn.clicked.connect(self.accept)
        save_btn.setDefault(True)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(save_btn)
        layout.addRow('', button_layout)
        
        self.setLayout(layout)
        
        # Load meeting data if editing
        if self.meeting:
            self.name_input.setText(self.meeting.get('name', ''))
            self.url_input.setText(self.meeting.get('url', ''))

            schedule_value = self.meeting.get('schedule', '')
            parsed_time = self._parse_schedule_time(schedule_value)
            if parsed_time and parsed_time.isValid():
                self.schedule_input.setTime(parsed_time)

    @staticmethod
    def _parse_schedule_time(schedule_value):
        """Parse stored schedule value into QTime."""
        if not schedule_value:
            return None

        if isinstance(schedule_value, str):
            schedule_text = schedule_value.strip()
            if ':' in schedule_text:
                time_obj = QTime.fromString(schedule_text, 'HH:mm')
                if time_obj.isValid():
                    return time_obj
            parts = schedule_text.split()
            if len(parts) >= 2:
                try:
                    minute = int(parts[0])
                    hour = int(parts[1])
                    time_obj = QTime(hour, minute)
                    if time_obj.isValid():
                        return time_obj
                except ValueError:
                    return None

        return None

    def get_meeting_data(self):
        """Get the meeting data from the form"""
        return {
            'name': self.name_input.text().strip(),
            'url': self.url_input.text().strip(),
            'schedule': self.schedule_input.time().toString('HH:mm'),
            'enabled': True  # Always enabled when created from GUI
        }
    
    def validate_meeting_data(self):
        """
        Validate the meeting data before saving
        
        Returns:
            tuple: (is_valid, error_message)
        """
        import re
        
        errors = []
        
        # Validate name
        name = self.name_input.text().strip()
        if not name:
            errors.append('• Meeting Name is required and cannot be empty')
        elif len(name) < 2:
            errors.append('• Meeting Name must be at least 2 characters long')
        
        # Validate URL
        url = self.url_input.text().strip()
        if not url:
            errors.append('• Meeting URL is required and cannot be empty')
        else:
            # Check if URL starts with correct protocol
            if not url.startswith('https://meet.google.com/'):
                errors.append('• Meeting URL must start with "https://meet.google.com/"')
            else:
                # Validate URL format
                standard_pattern = r'^https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}$'
                lookup_pattern = r'^https://meet\.google\.com/lookup/[a-zA-Z0-9_-]+$'
                
                if not (re.match(standard_pattern, url, re.IGNORECASE) or 
                        re.match(lookup_pattern, url, re.IGNORECASE)):
                    errors.append(
                        '• Invalid Google Meet URL format\n'
                        '  Expected: https://meet.google.com/xxx-xxxx-xxx\n'
                        '  (where x is a letter, format: 3-4-3)'
                    )
        
        # Validate schedule (QTimeEdit always has a valid time, so no need to check)
        
        if errors:
            return False, '\n'.join(errors)
        
        return True, ''
    
    def accept(self):
        """Override accept to validate before closing"""
        is_valid, error_message = self.validate_meeting_data()
        
        if not is_valid:
            QMessageBox.warning(
                self,
                'Validation Error',
                'Please fill all required fields correctly:\n\n' + error_message
            )
            return
        
        # If valid, proceed with normal accept
        super().accept()


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.meetings_file = Path(__file__).parent.parent / 'meetings.json'
        self.env_file = Path(__file__).parent.parent / '.env'
        self.scheduler = None
        self.meeting_worker = None
        self._auth_running = False
        
        # Initialize storage folders
        self.init_storage_folders()
        
        self.init_ui()
        self.setup_tray()
        self.load_meetings()
        self.load_settings()
        self.check_auth_status()
        
        # Start scheduler
        self.start_scheduler()
    
    def init_ui(self):
        """Initialize the main UI with sidebar navigation."""
        self.setWindowTitle('Mittora')
        self.setMinimumSize(1060, 780)
        
        self._apply_premium_theme()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        central_widget.setLayout(main_layout)
        
        # ── Left Sidebar ──
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(230)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        
        brand_frame = QFrame()
        brand_frame.setObjectName('brandFrame')
        brand_frame.setFixedHeight(80)
        brand_layout = QHBoxLayout(brand_frame)
        brand_layout.setContentsMargins(28, 0, 20, 0)
        
        brand_icon = QLabel('◆')
        brand_icon.setObjectName('brandIcon')
        brand_layout.addWidget(brand_icon)
        
        brand_label = QLabel(' Mittora')
        brand_label.setObjectName('brandLabel')
        brand_layout.addWidget(brand_label)
        brand_layout.addStretch()
        
        version = QLabel('v2.0')
        version.setObjectName('versionBadge')
        brand_layout.addWidget(version)
        sidebar_layout.addWidget(brand_frame)
        
        sep = QFrame()
        sep.setObjectName('sidebarSep')
        sep.setFixedHeight(1)
        sidebar_layout.addWidget(sep)
        sidebar_layout.addSpacing(16)
        
        nav_label = QLabel('   NAVIGATION')
        nav_label.setObjectName('navSectionLabel')
        sidebar_layout.addWidget(nav_label)
        sidebar_layout.addSpacing(8)
        
        nav_items = ['Meetings', 'Quick Join', 'History', 'Settings', 'AI Pipeline', 'Profile']
        self.nav_buttons = []
        for i, label in enumerate(nav_items):
            btn = QPushButton(f'    {label}')
            btn.setObjectName('navBtn')
            btn.setCheckable(True)
            btn.setFixedHeight(44)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=i: self._switch_page(idx))
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)
        
        sidebar_layout.addStretch()
        
        footer_frame = QFrame()
        footer_frame.setObjectName('sidebarFooter')
        footer_layout = QVBoxLayout(footer_frame)
        footer_layout.setContentsMargins(20, 12, 20, 16)
        self.scheduler_status = QLabel('● Scheduler Active')
        self.scheduler_status.setObjectName('schedulerStatus')
        footer_layout.addWidget(self.scheduler_status)
        sidebar_layout.addWidget(footer_frame)
        
        main_layout.addWidget(sidebar)
        
        # ── Content Area ──
        content_frame = QFrame()
        content_frame.setObjectName('contentFrame')
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        content_header = QFrame()
        content_header.setObjectName('contentHeader')
        content_header.setFixedHeight(80)
        ch_layout = QHBoxLayout(content_header)
        ch_layout.setContentsMargins(36, 0, 36, 0)
        
        self.page_title = QLabel('Meetings')
        self.page_title.setObjectName('pageTitle')
        ch_layout.addWidget(self.page_title)
        ch_layout.addStretch()
        
        self.meeting_count_label = QLabel('0 meetings scheduled')
        self.meeting_count_label.setObjectName('headerInfo')
        ch_layout.addWidget(self.meeting_count_label)
        content_layout.addWidget(content_header)
        
        page_container = QWidget()
        page_container.setObjectName('pageContainer')
        pc_layout = QVBoxLayout(page_container)
        pc_layout.setContentsMargins(36, 24, 36, 24)
        
        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self.create_meetings_tab())
        self.page_stack.addWidget(self.create_quick_join_tab())
        self.page_stack.addWidget(self.create_history_tab())
        self.page_stack.addWidget(self.create_settings_tab())
        self.page_stack.addWidget(self.create_ai_pipeline_tab())
        self.page_stack.addWidget(self.create_profile_tab())
        pc_layout.addWidget(self.page_stack)
        content_layout.addWidget(page_container)
        
        main_layout.addWidget(content_frame)
        
        self.nav_buttons[0].setChecked(True)
        self.page_stack.setCurrentIndex(0)
        
        self.status_label = QLabel('  Ready')
        self.statusBar().addWidget(self.status_label)
    
    def _apply_premium_theme(self):
        """Apply Mittora premium dark theme — warm amber accent."""
        self.setStyleSheet("""
            /* ══════════════════════════════════════
               MITTORA — Premium Dark Theme
               Accent: Warm Amber #e8a838
               ══════════════════════════════════════ */

            QMainWindow {
                background-color: #0c0c12;
                color: #e8e4dc;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }

            /* ── Sidebar ── */
            QFrame#sidebar {
                background-color: #101018;
                border-right: 1px solid #1e1e2a;
            }
            QFrame#brandFrame { background: transparent; }
            QLabel#brandIcon {
                font-size: 24px;
                color: #e8a838;
            }
            QLabel#brandLabel {
                font-size: 22px;
                font-weight: 700;
                color: #f0ece4;
                letter-spacing: 1px;
            }
            QLabel#versionBadge {
                font-size: 10px;
                color: #5a5668;
                padding: 3px 8px;
                background: #18182a;
                border-radius: 6px;
                border: 1px solid #2a2a3a;
            }
            QFrame#sidebarSep { background-color: #1e1e2a; }
            QLabel#navSectionLabel {
                font-size: 10px;
                font-weight: 700;
                color: #4a465a;
                letter-spacing: 2px;
                padding-left: 24px;
            }

            /* ── Nav Buttons ── */
            QPushButton#navBtn {
                background: transparent;
                color: #7a7688;
                border: none;
                border-left: 3px solid transparent;
                border-radius: 0px;
                text-align: left;
                padding-left: 24px;
                font-size: 13.5px;
                font-weight: 500;
            }
            QPushButton#navBtn:hover {
                background: #18182e;
                color: #c0bcc8;
                border-left: 3px solid #2a2a40;
            }
            QPushButton#navBtn:checked {
                background: #1a1a30;
                color: #e8a838;
                border-left: 3px solid #e8a838;
                font-weight: 600;
            }

            /* ── Sidebar Footer ── */
            QFrame#sidebarFooter { border-top: 1px solid #1e1e2a; }
            QLabel#schedulerStatus {
                font-size: 12px;
                color: #34d399;
                font-weight: 500;
            }

            /* ── Content Area ── */
            QFrame#contentFrame { background-color: #0c0c12; }
            QFrame#contentHeader {
                background-color: #0e0e16;
                border-bottom: 1px solid #1a1a26;
            }
            QLabel#pageTitle {
                font-size: 24px;
                font-weight: 700;
                color: #f0ece4;
                letter-spacing: 0.3px;
            }
            QLabel#headerInfo {
                font-size: 12px;
                color: #5a5668;
                padding: 6px 14px;
                background: #14141e;
                border-radius: 8px;
                border: 1px solid #1e1e2a;
            }
            QWidget#pageContainer { background-color: #0c0c12; }

            /* ── GroupBox ── */
            QGroupBox {
                font-size: 14px;
                font-weight: 600;
                color: #c0bcc8;
                border: 1px solid #1e1e2a;
                border-radius: 12px;
                margin-top: 18px;
                padding-top: 28px;
                background-color: #111119;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 5px 16px;
                left: 16px;
                background-color: #1a1a28;
                border-radius: 8px;
                border: 1px solid #24243a;
                color: #e8e4dc;
            }

            /* ── Inputs ── */
            QLineEdit, QSpinBox, QComboBox, QTimeEdit {
                background-color: #14141e;
                border: 1px solid #24243a;
                border-radius: 8px;
                padding: 9px 14px;
                color: #e8e4dc;
                font-size: 13px;
                selection-background-color: #e8a838;
                selection-color: #0c0c12;
                min-height: 20px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTimeEdit:focus {
                border-color: #e8a838;
                background-color: #18182a;
            }
            QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
                background-color: #0e0e16;
                color: #3a3648;
                border-color: #18182a;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #14141e;
                color: #e8e4dc;
                border: 1px solid #24243a;
                selection-background-color: #e8a838;
                selection-color: #0c0c12;
                border-radius: 8px;
                padding: 4px;
            }

            /* ── Buttons ── */
            QPushButton {
                background-color: #1a1a28;
                color: #e8e4dc;
                border: 1px solid #24243a;
                border-radius: 8px;
                padding: 9px 22px;
                font-weight: 500;
                font-size: 13px;
                min-height: 18px;
            }
            QPushButton:hover {
                background-color: #24243a;
                border-color: #e8a838;
                color: #f0ece4;
            }
            QPushButton:pressed {
                background-color: #e8a838;
                color: #0c0c12;
                border-color: #e8a838;
            }
            QPushButton#primaryBtn {
                background-color: #e8a838;
                border: none;
                color: #0c0c12;
                font-weight: 600;
            }
            QPushButton#primaryBtn:hover { background-color: #d4922a; }
            QPushButton#primaryBtn:pressed { background-color: #c07e1c; }
            QPushButton#dangerBtn {
                background-color: #dc2626;
                border: none;
                color: white;
                font-weight: 600;
            }
            QPushButton#dangerBtn:hover { background-color: #b91c1c; }
            QPushButton#successBtn {
                background-color: #059669;
                border: none;
                color: white;
                font-weight: 600;
            }
            QPushButton#successBtn:hover { background-color: #047857; }

            /* ── Checkbox ── */
            QCheckBox {
                color: #c0bcc8;
                spacing: 10px;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #2a2a3a;
                border-radius: 5px;
                background-color: #14141e;
            }
            QCheckBox::indicator:checked {
                background-color: #e8a838;
                border-color: #e8a838;
            }
            QCheckBox::indicator:hover { border-color: #e8a838; }

            /* ── Table ── */
            QTableWidget {
                background-color: #111119;
                border: 1px solid #1e1e2a;
                border-radius: 10px;
                gridline-color: #1a1a26;
                color: #e8e4dc;
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 10px 8px;
                border-bottom: 1px solid #1a1a26;
            }
            QTableWidget::item:selected {
                background-color: rgba(232, 168, 56, 0.1);
                color: #e8a838;
            }
            QHeaderView::section {
                background-color: #14141e;
                color: #5a5668;
                border: none;
                border-bottom: 2px solid #1e1e2a;
                padding: 12px 8px;
                font-weight: 700;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }

            /* ── TextEdit (Log) ── */
            QTextEdit {
                background-color: #0a0a10;
                border: 1px solid #1e1e2a;
                border-radius: 10px;
                color: #8a8698;
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 12px;
                padding: 12px;
            }

            /* ── ScrollBar ── */
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                border-radius: 3px;
                margin: 4px 0;
            }
            QScrollBar::handle:vertical {
                background: #2a2a3a;
                border-radius: 3px;
                min-height: 40px;
            }
            QScrollBar::handle:vertical:hover { background: #e8a838; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal {
                background: transparent;
                height: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal {
                background: #2a2a3a;
                border-radius: 3px;
                min-width: 40px;
            }
            QScrollBar::handle:horizontal:hover { background: #e8a838; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

            /* ── Slider ── */
            QSlider::groove:horizontal {
                background: #1a1a28;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #e8a838;
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover { background: #d4922a; }
            QSlider::sub-page:horizontal {
                background: #e8a838;
                border-radius: 3px;
            }

            /* ── StatusBar ── */
            QStatusBar {
                background-color: #0a0a10;
                color: #4a465a;
                border-top: 1px solid #1a1a26;
                font-size: 12px;
                padding: 2px 8px;
            }

            /* ── Labels ── */
            QLabel { color: #c0bcc8; }
            QLabel#sectionTitle {
                font-size: 17px;
                font-weight: 700;
                color: #f0ece4;
            }
            QLabel#sectionDesc {
                font-size: 12px;
                color: #5a5668;
            }
            QLabel#fieldHint {
                font-size: 11px;
                color: #4a465a;
                font-style: italic;
            }
            QLabel#statusActive {
                color: #34d399;
                font-weight: 600;
            }
            QLabel#statusInactive {
                color: #ef4444;
                font-weight: 600;
            }

            /* ── Misc ── */
            QFrame#separator {
                background-color: #1e1e2a;
                max-height: 1px;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
        """)
    
    def _switch_page(self, index):
        """Switch the active page in sidebar navigation."""
        titles = ['Meetings', 'Quick Join', 'History', 'Settings', 'AI Pipeline', 'Profile']
        self.page_stack.setCurrentIndex(index)
        self.page_title.setText(titles[index])
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
    
    def init_storage_folders(self):
        """Initialize storage folders for chat logs and screenshots"""
        load_dotenv(self.env_file)
        storage_path = os.getenv('STORAGE_PATH', '')
        
        if not storage_path:
            # Default to project directory
            storage_path = str(Path(__file__).parent.parent)
        
        storage_dir = Path(storage_path)
        
        try:
            storage_dir.mkdir(parents=True, exist_ok=True)
            print(f'✅ Storage base path initialized at: {storage_path}')
        except Exception as e:
            print(f'⚠️  Error initializing storage path: {str(e)}')
    
    def create_meetings_tab(self):
        """Create the meetings management tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Header with add button
        header_layout = QHBoxLayout()
        header_label = QLabel('Scheduled Meetings')
        header_label.setStyleSheet('font-size: 16px; font-weight: bold;')
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        add_btn = QPushButton('➕ Add Meeting')
        add_btn.clicked.connect(self.add_meeting)
        header_layout.addWidget(add_btn)
        layout.addLayout(header_layout)
        
        # Meetings table
        self.meetings_table = QTableWidget()
        self.meetings_table.setColumnCount(4)
        self.meetings_table.setHorizontalHeaderLabels([
            'Name', 'URL', 'Schedule', 'Actions'
        ])
        self.meetings_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.meetings_table)
        
        widget.setLayout(layout)
        return widget
    
    def create_quick_join_tab(self):
        """Create the quick join tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)
        
        # Header
        header = QLabel('Join Meeting Now')
        header.setStyleSheet('font-size: 16px; font-weight: bold;')
        layout.addWidget(header)
        
        desc = QLabel('Enter a meeting URL to join immediately')
        desc.setStyleSheet('color: gray;')
        layout.addWidget(desc)
        
        layout.addSpacing(20)
        
        # Form
        form_layout = QFormLayout()
        
        self.quick_url_input = QLineEdit()
        self.quick_url_input.setPlaceholderText('https://meet.google.com/xxx-yyyy-zzz')
        form_layout.addRow('Meeting URL *:', self.quick_url_input)
        
        self.quick_name_input = QLineEdit()
        self.quick_name_input.setPlaceholderText('Quick Meeting')
        form_layout.addRow('Meeting Name:', self.quick_name_input)
        
        layout.addLayout(form_layout)
        
        # Join button
        join_btn = QPushButton('🚀 Join Now')
        join_btn.setMinimumHeight(40)
        join_btn.clicked.connect(self.quick_join_meeting)
        layout.addWidget(join_btn)
        
        # Log output
        layout.addSpacing(20)
        log_label = QLabel('Meeting Log:')
        layout.addWidget(log_label)
        
        self.quick_join_log = QTextEdit()
        self.quick_join_log.setReadOnly(True)
        self.quick_join_log.setMaximumHeight(200)
        layout.addWidget(self.quick_join_log)
        
        layout.addStretch()
        
        widget.setLayout(layout)
        return widget
    
    def create_history_tab(self):
        """Create the Meeting History tab — browse past meeting sessions."""
        widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        widget.setLayout(main_layout)

        # Header row
        header_row = QHBoxLayout()
        header_label = QLabel('Session History')
        header_label.setObjectName('sectionTitle')
        header_row.addWidget(header_label)
        header_row.addStretch()

        refresh_btn = QPushButton('Refresh')
        refresh_btn.clicked.connect(self._refresh_history)
        header_row.addWidget(refresh_btn)

        open_folder_btn = QPushButton('Open Folder')
        open_folder_btn.clicked.connect(self._open_storage_folder)
        header_row.addWidget(open_folder_btn)

        main_layout.addLayout(header_row)

        desc = QLabel('Browse past meeting sessions — view chat messages, screenshots, and audio.')
        desc.setObjectName('sectionDesc')
        desc.setWordWrap(True)
        main_layout.addWidget(desc)

        # Sessions table
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels([
            'Meeting', 'Date', 'Chat Messages', 'Screenshots', 'Audio'
        ])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.doubleClicked.connect(self._open_session_detail)
        self.history_table.setMinimumHeight(200)
        main_layout.addWidget(self.history_table)

        # Detail panel (shown when a session is selected)
        self.history_detail = QGroupBox('Session Details')
        detail_layout = QVBoxLayout()
        detail_layout.setSpacing(10)
        detail_layout.setContentsMargins(16, 20, 16, 16)

        self.detail_info_label = QLabel('Select a session above and double-click to view details.')
        self.detail_info_label.setObjectName('sectionDesc')
        self.detail_info_label.setWordWrap(True)
        detail_layout.addWidget(self.detail_info_label)

        # Chat messages area
        self.detail_chat_label = QLabel('Chat Messages')
        self.detail_chat_label.setObjectName('sectionTitle')
        self.detail_chat_label.setVisible(False)
        detail_layout.addWidget(self.detail_chat_label)

        self.detail_chat_text = QTextEdit()
        self.detail_chat_text.setReadOnly(True)
        self.detail_chat_text.setMaximumHeight(220)
        self.detail_chat_text.setVisible(False)
        detail_layout.addWidget(self.detail_chat_text)

        # Screenshots info
        self.detail_screenshots_label = QLabel('')
        self.detail_screenshots_label.setObjectName('sectionDesc')
        self.detail_screenshots_label.setWordWrap(True)
        self.detail_screenshots_label.setVisible(False)
        detail_layout.addWidget(self.detail_screenshots_label)

        # Open session folder button
        self.detail_open_btn = QPushButton('Open Session Folder')
        self.detail_open_btn.setObjectName('primaryBtn')
        self.detail_open_btn.setMinimumHeight(38)
        self.detail_open_btn.setVisible(False)
        self.detail_open_btn.clicked.connect(self._open_selected_session_folder)
        detail_layout.addWidget(self.detail_open_btn)

        self.history_detail.setLayout(detail_layout)
        main_layout.addWidget(self.history_detail)

        # Load sessions on first render
        QTimer.singleShot(500, self._refresh_history)

        return widget

    def _refresh_history(self):
        """Scan storage directory and populate history table."""
        load_dotenv(self.env_file)
        storage_path = os.getenv('STORAGE_PATH', '')
        if not storage_path:
            storage_path = str(Path(__file__).parent.parent)

        storage_dir = Path(storage_path)
        if not storage_dir.exists():
            self.history_table.setRowCount(0)
            return

        sessions = []
        for meeting_dir in sorted(storage_dir.iterdir(), reverse=True):
            if not meeting_dir.is_dir():
                continue
            # Skip non-meeting directories
            if meeting_dir.name.startswith('.') or meeting_dir.name in (
                'auth-state', 'playwright_profile', '.venv', '__pycache__',
                'src', 'tests', '.git', '.idea', '.agent',
            ):
                continue

            # Count artifacts
            chat_count = 0
            screenshot_count = 0
            has_audio = False
            session_date = None

            for sub in meeting_dir.iterdir():
                if not sub.is_dir():
                    continue
                name_lower = sub.name.lower()
                if 'chatlog' in name_lower:
                    for f in sub.glob('*.json'):
                        try:
                            data = json.load(open(f, encoding='utf-8'))
                            if isinstance(data, list):
                                chat_count += len(data)
                            elif isinstance(data, dict) and 'messages' in data:
                                chat_count += len(data['messages'])
                        except Exception:
                            pass
                elif 'screenshot' in name_lower:
                    screenshot_count += len(list(sub.glob('*.png')))
                    screenshot_count += len(list(sub.glob('*.jpg')))
                elif 'audio' in name_lower:
                    audio_files = list(sub.glob('*.wav')) + list(sub.glob('*.mp3'))
                    has_audio = len(audio_files) > 0

            # Get modification time
            try:
                mtime = meeting_dir.stat().st_mtime
                session_date = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
            except Exception:
                session_date = '—'

            sessions.append({
                'name': meeting_dir.name.replace('_', ' '),
                'path': str(meeting_dir),
                'date': session_date,
                'chats': chat_count,
                'screenshots': screenshot_count,
                'audio': has_audio,
            })

        self.history_table.setRowCount(len(sessions))
        for row, s in enumerate(sessions):
            self.history_table.setItem(row, 0, QTableWidgetItem(s['name']))
            self.history_table.setItem(row, 1, QTableWidgetItem(s['date']))
            self.history_table.setItem(row, 2, QTableWidgetItem(str(s['chats']) if s['chats'] else '—'))
            self.history_table.setItem(row, 3, QTableWidgetItem(str(s['screenshots']) if s['screenshots'] else '—'))
            self.history_table.setItem(row, 4, QTableWidgetItem('Yes' if s['audio'] else '—'))

            # Store path in first column item
            self.history_table.item(row, 0).setData(Qt.UserRole, s['path'])

    def _open_session_detail(self, index):
        """Show detail panel for the selected session."""
        row = index.row()
        item = self.history_table.item(row, 0)
        if not item:
            return

        session_path = Path(item.data(Qt.UserRole))
        session_name = item.text()

        # Build detail info
        info_parts = [f'Session: {session_name}']

        # Load chat messages
        chat_messages = []
        for sub in session_path.iterdir():
            if sub.is_dir() and 'chatlog' in sub.name.lower():
                for f in sub.glob('*.json'):
                    try:
                        data = json.load(open(f, encoding='utf-8'))
                        if isinstance(data, list):
                            chat_messages.extend(data)
                        elif isinstance(data, dict) and 'messages' in data:
                            chat_messages.extend(data['messages'])
                    except Exception:
                        pass

        # Show chat messages
        if chat_messages:
            self.detail_chat_label.setVisible(True)
            self.detail_chat_text.setVisible(True)
            chat_text = ''
            for msg in chat_messages:
                if isinstance(msg, dict):
                    sender = msg.get('sender', msg.get('name', 'Unknown'))
                    text = msg.get('message', msg.get('text', ''))
                    ts = msg.get('timestamp', '')
                    chat_text += f'[{ts}] {sender}: {text}\n'
                elif isinstance(msg, str):
                    chat_text += msg + '\n'
            self.detail_chat_text.setPlainText(chat_text.strip() or 'No messages found.')
            info_parts.append(f'{len(chat_messages)} chat messages')
        else:
            self.detail_chat_label.setVisible(False)
            self.detail_chat_text.setVisible(False)

        # Count screenshots
        screenshot_count = 0
        screenshot_dir = None
        for sub in session_path.iterdir():
            if sub.is_dir() and 'screenshot' in sub.name.lower():
                screenshot_dir = sub
                screenshot_count = len(list(sub.glob('*.png'))) + len(list(sub.glob('*.jpg')))

        if screenshot_count > 0:
            self.detail_screenshots_label.setVisible(True)
            self.detail_screenshots_label.setText(
                f'{screenshot_count} screenshots captured  —  '
                f'Location: {screenshot_dir}'
            )
            info_parts.append(f'{screenshot_count} screenshots')
        else:
            self.detail_screenshots_label.setVisible(False)

        # Audio info
        for sub in session_path.iterdir():
            if sub.is_dir() and 'audio' in sub.name.lower():
                audio_files = list(sub.glob('*.wav')) + list(sub.glob('*.mp3'))
                if audio_files:
                    total_mb = sum(f.stat().st_size for f in audio_files) / (1024 * 1024)
                    info_parts.append(f'Audio: {len(audio_files)} file(s), {total_mb:.1f} MB')

        self.detail_info_label.setText('  |  '.join(info_parts))
        self.detail_open_btn.setVisible(True)
        self._selected_session_path = session_path

    def _open_selected_session_folder(self):
        """Open the selected session's folder in file explorer."""
        if hasattr(self, '_selected_session_path') and self._selected_session_path:
            os.startfile(str(self._selected_session_path))

    def _open_storage_folder(self):
        """Open the root storage folder in file explorer."""
        load_dotenv(self.env_file)
        storage_path = os.getenv('STORAGE_PATH', '')
        if not storage_path:
            storage_path = str(Path(__file__).parent.parent)
        if Path(storage_path).exists():
            os.startfile(storage_path)

    def create_settings_tab(self):
        """Create the settings tab with premium design."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(12, 12, 12, 24)
        
        # === Auth Section ===
        auth_group = QGroupBox('Authentication')
        auth_layout = QVBoxLayout()
        auth_layout.setSpacing(12)
        auth_layout.setContentsMargins(16, 16, 16, 16)
        
        setup_btn = QPushButton('Run Google Authentication')
        setup_btn.setObjectName('primaryBtn')
        setup_btn.setMinimumHeight(40)
        setup_btn.clicked.connect(self.run_setup)
        auth_layout.addWidget(setup_btn)
        
        auth_group.setLayout(auth_layout)
        layout.addWidget(auth_group)
        
        # === Meeting Config Section ===
        meet_group = QGroupBox('Meeting Configuration')
        meet_layout = QFormLayout()
        meet_layout.setSpacing(12)
        meet_layout.setContentsMargins(16, 16, 16, 16)
        meet_layout.setLabelAlignment(Qt.AlignRight)
        
        self.headless_checkbox = QCheckBox('Run browser in headless mode (hidden)')
        meet_layout.addRow('', self.headless_checkbox)
        
        self.solo_timeout_input = QSpinBox()
        self.solo_timeout_input.setRange(1, 60)
        self.solo_timeout_input.setValue(8)
        self.solo_timeout_input.setSuffix(' min')
        self.solo_timeout_input.setToolTip('If AutoMeet is alone for this long, it will leave.')
        meet_layout.addRow('Solo Timeout:', self.solo_timeout_input)

        self.max_meeting_minutes_input = QSpinBox()
        self.max_meeting_minutes_input.setRange(5, 480)
        self.max_meeting_minutes_input.setValue(240)
        self.max_meeting_minutes_input.setSuffix(' min')
        self.max_meeting_minutes_input.setToolTip('Safety cap to avoid infinite meetings.')
        meet_layout.addRow('Max Duration:', self.max_meeting_minutes_input)
        
        self.max_retries_input = QSpinBox()
        self.max_retries_input.setRange(1, 10)
        self.max_retries_input.setValue(3)
        meet_layout.addRow('Max Retries:', self.max_retries_input)
        
        self.retry_delay_input = QSpinBox()
        self.retry_delay_input.setRange(5, 120)
        self.retry_delay_input.setValue(30)
        self.retry_delay_input.setSuffix(' sec')
        meet_layout.addRow('Retry Delay:', self.retry_delay_input)
        
        self.greeting_input = QLineEdit()
        self.greeting_input.setPlaceholderText('Hello everyone')
        meet_layout.addRow('Greeting:', self.greeting_input)
        
        self.screenshot_threshold_input = QSpinBox()
        self.screenshot_threshold_input.setRange(1, 20)
        self.screenshot_threshold_input.setValue(5)
        self.screenshot_threshold_input.setToolTip('Lower = more screenshots, Higher = fewer')
        meet_layout.addRow('Screenshot Sensitivity:', self.screenshot_threshold_input)
        
        hint = QLabel('Hash threshold (1-20). Lower values capture more screen changes.')
        hint.setObjectName('fieldHint')
        meet_layout.addRow('', hint)
        
        meet_group.setLayout(meet_layout)
        layout.addWidget(meet_group)
        
        # === Storage Section ===
        storage_group = QGroupBox('Storage Location')
        storage_layout = QVBoxLayout()
        storage_layout.setSpacing(10)
        storage_layout.setContentsMargins(16, 16, 16, 16)
        
        desc = QLabel('Where to save chat logs, screenshots and audio recordings')
        desc.setObjectName('sectionDesc')
        storage_layout.addWidget(desc)
        
        path_row = QHBoxLayout()
        self.storage_path_input = QLineEdit()
        self.storage_path_input.setPlaceholderText('Select folder...')
        self.storage_path_input.setReadOnly(True)
        path_row.addWidget(self.storage_path_input)
        
        browse_btn = QPushButton('Browse')
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self.browse_storage_folder)
        path_row.addWidget(browse_btn)
        
        storage_layout.addLayout(path_row)
        storage_group.setLayout(storage_layout)
        layout.addWidget(storage_group)
        
        # === Save Button ===
        save_btn = QPushButton('💾  Save All Settings')
        save_btn.setObjectName('successBtn')
        save_btn.setMinimumHeight(44)
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)
        
        layout.addStretch()
        
        widget.setLayout(layout)
        scroll.setWidget(widget)
        return scroll
    
    def create_ai_pipeline_tab(self):
        """Create the AI Pipeline configuration tab — profile & credentials."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(12, 12, 12, 24)
        
        # === Master Toggle ===
        toggle_group = QGroupBox('Pipeline Status')
        toggle_layout = QHBoxLayout()
        toggle_layout.setContentsMargins(16, 16, 16, 16)
        
        self.ai_enabled_checkbox = QCheckBox('Enable AI Pipeline')
        self.ai_enabled_checkbox.setToolTip('Master switch — when off, Mittora works normally without AI features.')
        toggle_layout.addWidget(self.ai_enabled_checkbox)
        
        toggle_layout.addStretch()
        
        self.ai_status_label = QLabel('● Inactive')
        self.ai_status_label.setObjectName('statusInactive')
        toggle_layout.addWidget(self.ai_status_label)
        
        self.ai_enabled_checkbox.toggled.connect(self._on_ai_toggle)
        
        toggle_group.setLayout(toggle_layout)
        layout.addWidget(toggle_group)
        
        # === Profile Section ===
        profile_group = QGroupBox('Your Profile')
        profile_layout = QFormLayout()
        profile_layout.setSpacing(12)
        profile_layout.setContentsMargins(16, 16, 16, 16)
        profile_layout.setLabelAlignment(Qt.AlignRight)
        
        self.ai_display_name = QLineEdit()
        self.ai_display_name.setPlaceholderText('e.g. Shivank')
        self.ai_display_name.setToolTip('The name others use to address you in meetings. Trigger detection uses this.')
        profile_layout.addRow('Display Name:', self.ai_display_name)
        
        name_hint = QLabel('This is the name the AI listens for in the meeting transcript.')
        name_hint.setObjectName('fieldHint')
        profile_layout.addRow('', name_hint)
        
        profile_group.setLayout(profile_layout)
        layout.addWidget(profile_group)
        
        # === API Credentials ===
        cred_group = QGroupBox('API Credentials')
        cred_layout = QVBoxLayout()
        cred_layout.setSpacing(12)
        cred_layout.setContentsMargins(16, 16, 16, 16)
        
        key_row = QHBoxLayout()
        key_label = QLabel('Groq API Key:')
        key_label.setFixedWidth(110)
        key_row.addWidget(key_label)
        
        self.ai_api_key = QLineEdit()
        self.ai_api_key.setPlaceholderText('gsk_...')
        self.ai_api_key.setEchoMode(QLineEdit.Password)
        self.ai_api_key.setToolTip('Your Groq API key from console.groq.com')
        key_row.addWidget(self.ai_api_key)
        
        self.toggle_key_btn = QPushButton('👁')
        self.toggle_key_btn.setFixedWidth(40)
        self.toggle_key_btn.setToolTip('Show/Hide API key')
        self.toggle_key_btn.clicked.connect(self._toggle_api_key_visibility)
        key_row.addWidget(self.toggle_key_btn)
        
        cred_layout.addLayout(key_row)
        
        key_hint = QLabel('Get your free key at console.groq.com → API Keys')
        key_hint.setObjectName('fieldHint')
        cred_layout.addWidget(key_hint)
        
        cred_group.setLayout(cred_layout)
        layout.addWidget(cred_group)
        
        # === Model Configuration ===
        model_group = QGroupBox('Model Configuration')
        model_layout = QFormLayout()
        model_layout.setSpacing(12)
        model_layout.setContentsMargins(16, 16, 16, 16)
        model_layout.setLabelAlignment(Qt.AlignRight)
        
        trigger_models = [
            'llama-3.1-8b-instant',
            'llama-3.3-70b-versatile',
            'qwen/qwen3-32b',
        ]
        self.ai_trigger_model = QComboBox()
        self.ai_trigger_model.addItems(trigger_models)
        self.ai_trigger_model.setToolTip('Fast model for yes/no trigger detection. 8B is fastest.')
        model_layout.addRow('Trigger Model:', self.ai_trigger_model)
        
        reply_models = [
            'qwen/qwen3-32b',
            'llama-3.3-70b-versatile',
            'openai/gpt-oss-120b',
            'llama-3.1-8b-instant',
        ]
        self.ai_reply_model = QComboBox()
        self.ai_reply_model.addItems(reply_models)
        self.ai_reply_model.setToolTip('Model for generating chat replies. Larger = better quality.')
        model_layout.addRow('Reply Model:', self.ai_reply_model)
        
        qa_models = [
            'openai/gpt-oss-120b',
            'qwen/qwen3-32b',
            'llama-3.3-70b-versatile',
        ]
        self.ai_qa_model = QComboBox()
        self.ai_qa_model.addItems(qa_models)
        self.ai_qa_model.setToolTip('Heavy model for detailed Q&A (future use).')
        model_layout.addRow('QA Model:', self.ai_qa_model)
        
        model_hint = QLabel('All models run via Groq API. Smaller models = lower latency.')
        model_hint.setObjectName('fieldHint')
        model_layout.addRow('', model_hint)
        
        model_group.setLayout(model_layout)
        layout.addWidget(model_group)
        
        # === Pipeline Behavior ===
        behavior_group = QGroupBox('Pipeline Behavior')
        behavior_layout = QFormLayout()
        behavior_layout.setSpacing(14)
        behavior_layout.setContentsMargins(16, 16, 16, 16)
        behavior_layout.setLabelAlignment(Qt.AlignRight)
        
        # Chunk duration slider
        chunk_row = QHBoxLayout()
        self.ai_chunk_slider = QSlider(Qt.Horizontal)
        self.ai_chunk_slider.setRange(10, 30)
        self.ai_chunk_slider.setValue(20)
        self.ai_chunk_slider.setTickInterval(5)
        self.ai_chunk_slider.setTickPosition(QSlider.TicksBelow)
        chunk_row.addWidget(self.ai_chunk_slider)
        self.ai_chunk_label = QLabel('20s')
        self.ai_chunk_label.setFixedWidth(36)
        chunk_row.addWidget(self.ai_chunk_label)
        self.ai_chunk_slider.valueChanged.connect(lambda v: self.ai_chunk_label.setText(f'{v}s'))
        behavior_layout.addRow('Chunk Duration:', chunk_row)
        
        chunk_hint = QLabel('Audio chunk size sent to STT. Lower = faster response, may reduce quality.')
        chunk_hint.setObjectName('fieldHint')
        behavior_layout.addRow('', chunk_hint)
        
        # Overlap slider
        overlap_row = QHBoxLayout()
        self.ai_overlap_slider = QSlider(Qt.Horizontal)
        self.ai_overlap_slider.setRange(0, 10)
        self.ai_overlap_slider.setValue(5)
        self.ai_overlap_slider.setTickInterval(1)
        self.ai_overlap_slider.setTickPosition(QSlider.TicksBelow)
        overlap_row.addWidget(self.ai_overlap_slider)
        self.ai_overlap_label = QLabel('5s')
        self.ai_overlap_label.setFixedWidth(36)
        overlap_row.addWidget(self.ai_overlap_label)
        self.ai_overlap_slider.valueChanged.connect(lambda v: self.ai_overlap_label.setText(f'{v}s'))
        behavior_layout.addRow('Chunk Overlap:', overlap_row)
        
        # Cooldown slider
        cooldown_row = QHBoxLayout()
        self.ai_cooldown_slider = QSlider(Qt.Horizontal)
        self.ai_cooldown_slider.setRange(10, 180)
        self.ai_cooldown_slider.setValue(60)
        self.ai_cooldown_slider.setTickInterval(10)
        self.ai_cooldown_slider.setTickPosition(QSlider.TicksBelow)
        cooldown_row.addWidget(self.ai_cooldown_slider)
        self.ai_cooldown_label = QLabel('60s')
        self.ai_cooldown_label.setFixedWidth(36)
        cooldown_row.addWidget(self.ai_cooldown_label)
        self.ai_cooldown_slider.valueChanged.connect(lambda v: self.ai_cooldown_label.setText(f'{v}s'))
        behavior_layout.addRow('Reply Cooldown:', cooldown_row)
        
        cooldown_hint = QLabel('Minimum seconds between auto-replies to avoid spamming.')
        cooldown_hint.setObjectName('fieldHint')
        behavior_layout.addRow('', cooldown_hint)
        
        behavior_group.setLayout(behavior_layout)
        layout.addWidget(behavior_group)
        
        # === Save Button ===
        save_btn = QPushButton('💾  Save AI Pipeline Settings')
        save_btn.setObjectName('successBtn')
        save_btn.setMinimumHeight(44)
        save_btn.clicked.connect(self.save_ai_pipeline_settings)
        layout.addWidget(save_btn)
        
        layout.addStretch()
        
        widget.setLayout(layout)
        scroll.setWidget(widget)
        return scroll

    def create_profile_tab(self):
        """Create the Profile tab — personalizes the AI bot's behaviour."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(12, 12, 12, 24)

        # === Header ===
        header = QLabel('Your Profile')
        header.setObjectName('sectionTitle')
        layout.addWidget(header)

        desc = QLabel('This information personalizes the AI bot so it answers with your identity and expertise.')
        desc.setObjectName('sectionDesc')
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # === Identity Section ===
        identity_group = QGroupBox('Identity')
        identity_layout = QFormLayout()
        identity_layout.setSpacing(12)
        identity_layout.setContentsMargins(16, 16, 16, 16)
        identity_layout.setLabelAlignment(Qt.AlignRight)

        self.profile_display_name = QLineEdit()
        self.profile_display_name.setPlaceholderText('e.g. Shivank')
        self.profile_display_name.setToolTip('The name others call you in meetings.')
        identity_layout.addRow('Display Name:', self.profile_display_name)

        self.profile_role = QLineEdit()
        self.profile_role.setPlaceholderText('e.g. BCA Student, Sem 6')
        self.profile_role.setToolTip('Your role or designation — helps the bot introduce itself accurately.')
        identity_layout.addRow('Role / Designation:', self.profile_role)

        self.profile_aliases = QLineEdit()
        self.profile_aliases.setPlaceholderText('e.g. Sivank, Siwank, Shiwank')
        self.profile_aliases.setToolTip('Comma-separated alternate spellings of your name (for Whisper STT fuzzy matching).')
        identity_layout.addRow('Name Aliases:', self.profile_aliases)

        alias_hint = QLabel('Whisper often misspells names. Add common misspellings here.')
        alias_hint.setObjectName('fieldHint')
        identity_layout.addRow('', alias_hint)

        identity_group.setLayout(identity_layout)
        layout.addWidget(identity_group)

        # === Meeting Context Section ===
        context_group = QGroupBox('Meeting Context')
        context_layout = QFormLayout()
        context_layout.setSpacing(12)
        context_layout.setContentsMargins(16, 16, 16, 16)
        context_layout.setLabelAlignment(Qt.AlignRight)

        # Meeting Purpose dropdown + Other freetext
        purpose_row = QHBoxLayout()
        self.profile_purpose_combo = QComboBox()
        self.profile_purpose_combo.addItems([
            'Online Class',
            'Team Standup',
            'Interview',
            'Presentation',
            'Group Discussion',
            'Other',
        ])
        self.profile_purpose_combo.setToolTip('What kind of meeting is this? Adjusts the bot\'s tone.')
        self.profile_purpose_combo.currentTextChanged.connect(self._on_purpose_changed)
        purpose_row.addWidget(self.profile_purpose_combo)

        self.profile_purpose_other = QLineEdit()
        self.profile_purpose_other.setPlaceholderText('Describe your meeting type...')
        self.profile_purpose_other.setVisible(False)
        purpose_row.addWidget(self.profile_purpose_other)

        context_layout.addRow('Meeting Purpose:', purpose_row)

        self.profile_subject = QLineEdit()
        self.profile_subject.setPlaceholderText('e.g. Computer Science, Mathematics')
        self.profile_subject.setToolTip('Subjects the bot should prioritize when answering questions.')
        context_layout.addRow('Subject / Domain:', self.profile_subject)

        subject_hint = QLabel('Comma-separated subjects. The AI will prioritize answers in these domains.')
        subject_hint.setObjectName('fieldHint')
        context_layout.addRow('', subject_hint)

        context_group.setLayout(context_layout)
        layout.addWidget(context_group)

        # === Response Style Section ===
        style_group = QGroupBox('Response Style')
        style_layout = QVBoxLayout()
        style_layout.setSpacing(10)
        style_layout.setContentsMargins(16, 16, 16, 16)

        style_desc = QLabel('How should the AI responses sound?')
        style_desc.setObjectName('sectionDesc')
        style_layout.addWidget(style_desc)

        self.profile_style_combo = QComboBox()
        self.profile_style_combo.addItems(['Casual', 'Formal', 'Concise'])
        self.profile_style_combo.setToolTip(
            'Casual = friendly and natural, '
            'Formal = professional tone, '
            'Concise = shortest possible answers'
        )
        style_layout.addWidget(self.profile_style_combo)

        style_group.setLayout(style_layout)
        layout.addWidget(style_group)

        # === Save Button ===
        save_btn = QPushButton('💾  Save Profile')
        save_btn.setObjectName('successBtn')
        save_btn.setMinimumHeight(44)
        save_btn.clicked.connect(self.save_profile)
        layout.addWidget(save_btn)

        layout.addStretch()

        widget.setLayout(layout)
        scroll.setWidget(widget)
        return scroll

    def _on_purpose_changed(self, text):
        """Show/hide the free-text field when 'Other' is selected."""
        self.profile_purpose_other.setVisible(text == 'Other')
    
    def _on_ai_toggle(self, checked):
        """Update status label when AI pipeline is toggled."""
        if checked:
            self.ai_status_label.setText('● Active')
            self.ai_status_label.setObjectName('statusActive')
        else:
            self.ai_status_label.setText('● Inactive')
            self.ai_status_label.setObjectName('statusInactive')
        # Force style refresh
        self.ai_status_label.setStyleSheet(self.ai_status_label.styleSheet())
        self._apply_premium_theme()
    
    def _toggle_api_key_visibility(self):
        """Toggle API key show/hide."""
        if self.ai_api_key.echoMode() == QLineEdit.Password:
            self.ai_api_key.setEchoMode(QLineEdit.Normal)
            self.toggle_key_btn.setText('🔒')
        else:
            self.ai_api_key.setEchoMode(QLineEdit.Password)
            self.toggle_key_btn.setText('👁')
    
    def setup_tray(self):
        """Setup system tray icon"""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip('Mittora')
        
        # Create tray menu
        tray_menu = QMenu()
        
        show_action = QAction('Show App', self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        quick_join_action = QAction('Quick Join', self)
        quick_join_action.triggered.connect(lambda: (self.show(), self._switch_page(1)))
        tray_menu.addAction(quick_join_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction('Quit', self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
    
    def tray_icon_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.Trigger:
            self.show()
    
    def closeEvent(self, event):
        """Handle window close event"""
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            'Mittora',
            'Application minimized to tray',
            QSystemTrayIcon.Information,
            2000
        )
    
    def quit_application(self):
        """Quit the application"""
        if self.scheduler:
            self.scheduler.stop()
        QApplication.quit()
    
    def load_meetings(self):
        """Load meetings from JSON file"""
        try:
            if self.meetings_file.exists():
                with open(self.meetings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    meetings = data.get('meetings', [])
                    self.display_meetings(meetings)
                    self.meeting_count_label.setText(f'{len(meetings)} meetings scheduled')
        except Exception as e:
            QMessageBox.warning(self, 'Error', f'Failed to load meetings: {str(e)}')
    
    def display_meetings(self, meetings):
        """Display meetings in the table"""
        self.meetings_table.setRowCount(len(meetings))
        
        for i, meeting in enumerate(meetings):
            self.meetings_table.setItem(i, 0, QTableWidgetItem(meeting.get('name', '')))
            self.meetings_table.setItem(i, 1, QTableWidgetItem(meeting.get('url', '')))
            self.meetings_table.setItem(i, 2, QTableWidgetItem(meeting.get('schedule', '')))
            
            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(0, 0, 0, 0)
            
            edit_btn = QPushButton('Edit')
            edit_btn.clicked.connect(lambda checked, idx=i: self.edit_meeting(idx))
            actions_layout.addWidget(edit_btn)
            
            delete_btn = QPushButton('Delete')
            delete_btn.clicked.connect(lambda checked, idx=i: self.delete_meeting(idx))
            actions_layout.addWidget(delete_btn)
            
            actions_widget.setLayout(actions_layout)
            self.meetings_table.setCellWidget(i, 3, actions_widget)
    
    def save_meetings(self, meetings):
        """Save meetings to JSON file"""
        try:
            data = {'meetings': meetings}
            with open(self.meetings_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            self.load_meetings()
            self.restart_scheduler()
            return True
        except Exception as e:
            QMessageBox.warning(self, 'Error', f'Failed to save meetings: {str(e)}')
            return False
    
    def add_meeting(self):
        """Add a new meeting"""
        dialog = MeetingDialog(self)
        if dialog.exec():
            meeting_data = dialog.get_meeting_data()
            
            # Load current meetings
            meetings = []
            if self.meetings_file.exists():
                with open(self.meetings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    meetings = data.get('meetings', [])
            
            meetings.append(meeting_data)
            self.save_meetings(meetings)
            QMessageBox.information(self, 'Success', 'Meeting added successfully!')
    
    def edit_meeting(self, index):
        """Edit an existing meeting"""
        # Load current meetings
        with open(self.meetings_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            meetings = data.get('meetings', [])
        
        if index < len(meetings):
            dialog = MeetingDialog(self, meetings[index])
            if dialog.exec():
                meetings[index] = dialog.get_meeting_data()
                self.save_meetings(meetings)
                QMessageBox.information(self, 'Success', 'Meeting updated successfully!')
    
    def delete_meeting(self, index):
        """Delete a meeting"""
        reply = QMessageBox.question(
            self, 'Confirm Delete',
            'Are you sure you want to delete this meeting?',
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            with open(self.meetings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                meetings = data.get('meetings', [])
            
            if index < len(meetings):
                meetings.pop(index)
                self.save_meetings(meetings)
                QMessageBox.information(self, 'Success', 'Meeting deleted successfully!')
    
    def quick_join_meeting(self):
        """Quick join a meeting"""
        import re
        
        url = self.quick_url_input.text().strip()
        if not url:
            QMessageBox.warning(
                self, 
                'Validation Error', 
                'Please fill all required fields:\n\n• Meeting URL is required and cannot be empty'
            )
            return
        
        # Validate URL format
        if not url.startswith('https://meet.google.com/'):
            QMessageBox.warning(
                self,
                'Validation Error',
                'Invalid Meeting URL:\n\n• URL must start with "https://meet.google.com/"'
            )
            return
        
        # Validate URL format
        standard_pattern = r'^https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}$'
        lookup_pattern = r'^https://meet\.google\.com/lookup/[a-zA-Z0-9_-]+$'
        
        if not (re.match(standard_pattern, url, re.IGNORECASE) or 
                re.match(lookup_pattern, url, re.IGNORECASE)):
            QMessageBox.warning(
                self,
                'Validation Error',
                'Invalid Google Meet URL format:\n\n'
                '• Expected format: https://meet.google.com/xxx-xxxx-xxx\n'
                '  (where x is a letter, format: 3-4-3)\n\n'
                'Example: https://meet.google.com/abc-defg-hij'
            )
            return
        
        name = self.quick_name_input.text().strip() or 'Quick Meeting'

        self.quick_join_log.clear()
        self.quick_join_log.append('🚀 Starting quick join...\n')

        # Run in worker thread
        self.meeting_worker = MeetingWorker(url, name)
        self.meeting_worker.log_signal.connect(self.append_log)
        self.meeting_worker.finished_signal.connect(self.meeting_finished)
        self.meeting_worker.start()
    
    def append_log(self, message):
        """Append message to log"""
        self.quick_join_log.append(message)
    
    def meeting_finished(self, success):
        """Handle meeting finished"""
        if success:
            self.quick_join_log.append('\n✅ Meeting completed successfully!')
        else:
            self.quick_join_log.append('\n❌ Meeting failed')
    
    def load_settings(self):
        """Load settings from .env file"""
        load_dotenv(self.env_file)
        
        # Meeting settings
        self.headless_checkbox.setChecked(os.getenv('HEADLESS', 'false').lower() == 'true')
        self.solo_timeout_input.setValue(int(os.getenv('SOLO_TIMEOUT_MINUTES', '8')))
        self.max_meeting_minutes_input.setValue(int(os.getenv('MAX_MEETING_MINUTES', '240')))
        self.max_retries_input.setValue(int(os.getenv('MAX_RETRY_ATTEMPTS', '3')))
        self.retry_delay_input.setValue(int(os.getenv('RETRY_DELAY_SECONDS', '30')))
        self.greeting_input.setText(os.getenv('GREETING_MESSAGE', 'Hello everyone'))
        self.screenshot_threshold_input.setValue(int(os.getenv('SCREENSHOT_HASH_THRESHOLD', '5')))
        
        # Storage path
        storage_path = os.getenv('STORAGE_PATH', '')
        if not storage_path:
            storage_path = str(Path(__file__).parent.parent)
        self.storage_path_input.setText(storage_path)
        
        # AI Pipeline settings
        self.ai_enabled_checkbox.setChecked(os.getenv('AI_PIPELINE_ENABLED', 'true').lower() == 'true')
        self.ai_display_name.setText(os.getenv('USER_DISPLAY_NAME', ''))
        self.ai_api_key.setText(os.getenv('GROQ_API_KEY', ''))
        
        # Models — set combo box to matching value or keep default
        trigger_model = os.getenv('LLM_TRIGGER_MODEL', 'llama-3.1-8b-instant')
        idx = self.ai_trigger_model.findText(trigger_model)
        if idx >= 0:
            self.ai_trigger_model.setCurrentIndex(idx)
        
        reply_model = os.getenv('LLM_REPLY_MODEL', 'qwen/qwen3-32b')
        idx = self.ai_reply_model.findText(reply_model)
        if idx >= 0:
            self.ai_reply_model.setCurrentIndex(idx)
        
        qa_model = os.getenv('LLM_QA_MODEL', 'openai/gpt-oss-120b')
        idx = self.ai_qa_model.findText(qa_model)
        if idx >= 0:
            self.ai_qa_model.setCurrentIndex(idx)
        
        # Sliders
        self.ai_chunk_slider.setValue(int(os.getenv('CHUNK_DURATION', '20')))
        self.ai_overlap_slider.setValue(int(os.getenv('CHUNK_OVERLAP', '5')))
        self.ai_cooldown_slider.setValue(int(os.getenv('REPLY_COOLDOWN', '60')))

        # Profile tab
        self._load_profile()
    
    def save_settings(self):
        """Save meeting settings to .env file"""
        try:
            if not self.env_file.exists():
                self.env_file.touch()
            
            env_path = str(self.env_file)
            set_key(env_path, 'HEADLESS', 'true' if self.headless_checkbox.isChecked() else 'false')
            set_key(env_path, 'SOLO_TIMEOUT_MINUTES', str(self.solo_timeout_input.value()))
            set_key(env_path, 'MAX_MEETING_MINUTES', str(self.max_meeting_minutes_input.value()))
            set_key(env_path, 'MAX_RETRY_ATTEMPTS', str(self.max_retries_input.value()))
            set_key(env_path, 'RETRY_DELAY_SECONDS', str(self.retry_delay_input.value()))
            set_key(env_path, 'GREETING_MESSAGE', self.greeting_input.text())
            set_key(env_path, 'SCREENSHOT_HASH_THRESHOLD', str(self.screenshot_threshold_input.value()))
            set_key(env_path, 'STORAGE_PATH', self.storage_path_input.text())
            
            self.init_storage_folders()
            
            QMessageBox.information(self, 'Settings Saved', 'Meeting settings saved successfully!')
            self.restart_scheduler()
        except Exception as e:
            QMessageBox.warning(self, 'Error', f'Failed to save settings: {str(e)}')
    
    def save_ai_pipeline_settings(self):
        """Save AI Pipeline settings to .env file."""
        try:
            if not self.env_file.exists():
                self.env_file.touch()
            
            env_path = str(self.env_file)
            
            set_key(env_path, 'AI_PIPELINE_ENABLED', 'true' if self.ai_enabled_checkbox.isChecked() else 'false')
            set_key(env_path, 'USER_DISPLAY_NAME', self.ai_display_name.text().strip())
            
            # Only save API key if it's not empty
            api_key = self.ai_api_key.text().strip()
            if api_key:
                set_key(env_path, 'GROQ_API_KEY', api_key)
            
            set_key(env_path, 'LLM_TRIGGER_MODEL', self.ai_trigger_model.currentText())
            set_key(env_path, 'LLM_REPLY_MODEL', self.ai_reply_model.currentText())
            set_key(env_path, 'LLM_QA_MODEL', self.ai_qa_model.currentText())
            set_key(env_path, 'CHUNK_DURATION', str(self.ai_chunk_slider.value()))
            set_key(env_path, 'CHUNK_OVERLAP', str(self.ai_overlap_slider.value()))
            set_key(env_path, 'REPLY_COOLDOWN', str(self.ai_cooldown_slider.value()))
            
            QMessageBox.information(self, 'Settings Saved', 'AI Pipeline settings saved successfully!')
        except Exception as e:
            QMessageBox.warning(self, 'Error', f'Failed to save AI settings: {str(e)}')

    def _load_profile(self):
        """Load profile fields from .env into the Profile tab."""
        self.profile_display_name.setText(os.getenv('USER_DISPLAY_NAME', ''))
        self.profile_role.setText(os.getenv('USER_ROLE', ''))
        self.profile_aliases.setText(os.getenv('USER_NAME_ALIASES', ''))
        self.profile_subject.setText(os.getenv('USER_SUBJECT_DOMAIN', ''))

        # Response style
        style = os.getenv('USER_RESPONSE_STYLE', 'Casual')
        idx = self.profile_style_combo.findText(style)
        if idx >= 0:
            self.profile_style_combo.setCurrentIndex(idx)

        # Meeting purpose
        purpose = os.getenv('USER_MEETING_PURPOSE', 'Online Class')
        idx = self.profile_purpose_combo.findText(purpose)
        if idx >= 0:
            self.profile_purpose_combo.setCurrentIndex(idx)
        else:
            # Custom value — select "Other" and fill the free-text field
            other_idx = self.profile_purpose_combo.findText('Other')
            if other_idx >= 0:
                self.profile_purpose_combo.setCurrentIndex(other_idx)
            self.profile_purpose_other.setText(purpose)
            self.profile_purpose_other.setVisible(True)

    def save_profile(self):
        """Save profile fields to .env file."""
        try:
            if not self.env_file.exists():
                self.env_file.touch()

            env_path = str(self.env_file)
            display_name = self.profile_display_name.text().strip()

            set_key(env_path, 'USER_DISPLAY_NAME', display_name)
            set_key(env_path, 'USER_ROLE', self.profile_role.text().strip())
            set_key(env_path, 'USER_NAME_ALIASES', self.profile_aliases.text().strip())
            set_key(env_path, 'USER_SUBJECT_DOMAIN', self.profile_subject.text().strip())
            set_key(env_path, 'USER_RESPONSE_STYLE', self.profile_style_combo.currentText())

            # Meeting purpose — use free-text if "Other" is selected
            purpose = self.profile_purpose_combo.currentText()
            if purpose == 'Other':
                custom = self.profile_purpose_other.text().strip()
                purpose = custom if custom else 'Other'
            set_key(env_path, 'USER_MEETING_PURPOSE', purpose)

            # Sync display name to AI Pipeline tab
            self.ai_display_name.setText(display_name)

            QMessageBox.information(self, 'Profile Saved', 'Your profile has been saved! It will be used when the next meeting starts.')
        except Exception as e:
            QMessageBox.warning(self, 'Error', f'Failed to save profile: {str(e)}')
    
    def check_auth_status(self):
        """Check authentication status"""
        auth_file = Path(__file__).parent.parent / 'auth-state' / 'google-auth.json'
        profile_dir = Path(__file__).parent.parent / 'playwright_profile'
        cookies_file = profile_dir / 'Default' / 'Cookies'
        
        # Check if both auth file and browser profile with cookies exist
        if auth_file.exists() and cookies_file.exists():
            print('✅ Authentication status: Authenticated')
        else:
            print('❌ Authentication status: Not authenticated')
            
        # Print debug info
        print(f'Auth check: auth_file={auth_file.exists()}, cookies={cookies_file.exists()}')
    
    def run_setup(self):
        """Run the authentication setup"""
        # Check if authentication is already running
        if hasattr(self, '_auth_running') and self._auth_running:
            QMessageBox.warning(
                self, 'Authentication In Progress',
                'Authentication is already in progress. Please wait for it to complete.'
            )
            return
        
        reply = QMessageBox.question(
            self, 'Run Setup',
            'This will open a browser for Google authentication. Continue?',
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self._auth_running = True
            # Show progress message
            QMessageBox.information(
                self, 'Starting Authentication',
                'Browser will open shortly for Google login.\n\n'
                'Please complete the login process in the browser.\n'
                'The browser will close automatically when done.'
            )
            
            # Run authentication in a separate thread to avoid blocking UI
            auth_thread = threading.Thread(target=self._run_authentication_thread)
            auth_thread.daemon = True
            auth_thread.start()
    
    def _run_authentication_thread(self):
        """Run authentication in a separate thread"""
        try:
            def progress_callback(msg):
                """Print progress to console"""
                print(msg)
            
            success, message = run_google_authentication(progress_callback=progress_callback)
            
            # Update UI on main thread using QTimer
            QTimer.singleShot(0, lambda: self._handle_auth_result(success, message))
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Authentication exception: {error_details}")
            QTimer.singleShot(0, lambda: self._handle_auth_result(False, f"Authentication error: {str(e)}"))
        finally:
            self._auth_running = False
    
    def _handle_auth_result(self, success, message):
        """Handle authentication result on main thread"""
        self._auth_running = False
        
        if success:
            QMessageBox.information(
                self, 'Authentication Complete',
                'Google authentication completed successfully!\n\nYou can now schedule and join meetings.'
            )
            self.check_auth_status()
        else:
            # Check if it's a browser installation issue
            if 'playwright browsers' in message.lower() or 'executable doesn\'t exist' in message.lower():
                QMessageBox.critical(
                    self, 'Playwright Browsers Not Installed',
                    f'{message}\n\n'
                    'SOLUTION:\n'
                    '1. Open Command Prompt or PowerShell\n'
                    '2. Run: playwright install chromium\n'
                    '3. Then try authentication again\n\n'
                    'Or run the install_browsers.bat script in the app folder.'
                )
            else:
                QMessageBox.warning(
                    self, 'Authentication Failed',
                    f'Authentication failed:\n\n{message}\n\nPlease try again.'
                )
    
    def start_scheduler(self):
        """Start the meeting scheduler"""
        try:
            self.scheduler = MeetingScheduler(self.meetings_file)
            if self.scheduler.load_config():
                self.scheduler.schedule_all_meetings()
                self.scheduler.start()
                self.status_label.setText('🎯 Scheduler running')
        except Exception as e:
            self.status_label.setText(f'❌ Scheduler error: {str(e)}')
    
    def browse_storage_folder(self):
        """Open folder browser to select storage location"""
        current_path = self.storage_path_input.text()
        if not current_path:
            current_path = str(Path(__file__).parent.parent)
        
        folder = QFileDialog.getExistingDirectory(
            self,
            'Select Storage Folder',
            current_path,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if folder:
            self.storage_path_input.setText(folder)
            QMessageBox.information(
                self,
                'Folder Selected',
                f'Storage folder set to:\n{folder}\n\nClick "Save Settings" to apply changes.'
            )
    
    def restart_scheduler(self):
        """Restart the scheduler with new configuration"""
        if self.scheduler:
            self.scheduler.stop()
        self.start_scheduler()


def run_gui():
    """Run the GUI application"""
    app = QApplication(sys.argv)
    app.setApplicationName('Mittora')
    app.setQuitOnLastWindowClosed(False)  # Keep running in tray
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    run_gui()
