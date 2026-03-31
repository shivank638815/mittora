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
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QLabel, QLineEdit, QSpinBox, QCheckBox,
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
        """Initialize the main UI"""
        self.setWindowTitle('AutoMeet Attender')
        self.setMinimumSize(960, 740)
        
        # Apply premium theme
        self._apply_premium_theme()
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        central_widget.setLayout(main_layout)
        
        # Header bar
        header_bar = QFrame()
        header_bar.setObjectName('headerBar')
        header_bar.setFixedHeight(72)
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(28, 0, 28, 0)
        
        header = QLabel('AutoMeet Attender')
        header.setObjectName('appTitle')
        header_layout.addWidget(header)
        
        header_layout.addStretch()
        
        version_label = QLabel('v2.0')
        version_label.setObjectName('versionLabel')
        header_layout.addWidget(version_label)
        
        main_layout.addWidget(header_bar)
        
        # Content area
        content_widget = QWidget()
        content_widget.setObjectName('contentArea')
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(16, 16, 16, 16)
        
        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setObjectName('mainTabs')
        self.tabs.addTab(self.create_meetings_tab(), '📅  Meetings')
        self.tabs.addTab(self.create_quick_join_tab(), '🚀  Quick Join')
        self.tabs.addTab(self.create_settings_tab(), '⚙️  Settings')
        self.tabs.addTab(self.create_ai_pipeline_tab(), '🧠  AI Pipeline')
        content_layout.addWidget(self.tabs)
        
        main_layout.addWidget(content_widget)
        
        # Status bar
        self.status_label = QLabel('  Ready')
        self.statusBar().addWidget(self.status_label)
        
        self.meeting_count_label = QLabel('0 meetings scheduled  ')
        self.statusBar().addPermanentWidget(self.meeting_count_label)
    
    def _apply_premium_theme(self):
        """Apply a polished dark theme with modern design tokens."""
        self.setStyleSheet("""
            /* === Base === */
            QMainWindow {
                background-color: #0f1117;
                color: #e1e4eb;
                font-family: 'Segoe UI', 'Inter', sans-serif;
                font-size: 13px;
            }
            
            /* === Header Bar === */
            QFrame#headerBar {
                background-color: #161822;
                border-bottom: 1px solid #252836;
            }
            QLabel#appTitle {
                font-size: 20px;
                font-weight: 700;
                color: #f0f2f7;
                letter-spacing: 0.5px;
            }
            QLabel#versionLabel {
                font-size: 11px;
                color: #565b6e;
                padding: 4px 10px;
                background: #1c1f2e;
                border-radius: 8px;
            }
            
            /* === Content === */
            QWidget#contentArea {
                background-color: #0f1117;
            }
            
            /* === Tabs === */
            QTabWidget::pane {
                border: 1px solid #252836;
                border-radius: 10px;
                background-color: #161822;
                padding: 8px;
            }
            QTabBar::tab {
                background: transparent;
                color: #7a7f94;
                padding: 10px 22px;
                margin-right: 4px;
                border-radius: 8px 8px 0px 0px;
                font-weight: 500;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background: #161822;
                color: #f0f2f7;
                border-bottom: 2px solid #3b82f6;
            }
            QTabBar::tab:hover:!selected {
                background: #1c1f2e;
                color: #c0c4d4;
            }
            
            /* === GroupBox === */
            QGroupBox {
                font-size: 14px;
                font-weight: 600;
                color: #c0c4d4;
                border: 1px solid #252836;
                border-radius: 10px;
                margin-top: 18px;
                padding-top: 24px;
                background-color: #1c1f2e;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 4px 14px;
                left: 16px;
                background-color: #252836;
                border-radius: 6px;
                color: #e1e4eb;
            }
            
            /* === Inputs === */
            QLineEdit, QSpinBox, QComboBox, QTimeEdit {
                background-color: #1c1f2e;
                border: 1px solid #303448;
                border-radius: 8px;
                padding: 8px 14px;
                color: #e1e4eb;
                font-size: 13px;
                selection-background-color: #3b82f6;
                min-height: 20px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTimeEdit:focus {
                border-color: #3b82f6;
                background-color: #21243a;
            }
            QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
                background-color: #13151d;
                color: #4a4e5e;
                border-color: #1e2130;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 10px;
            }
            QComboBox QAbstractItemView {
                background-color: #1c1f2e;
                color: #e1e4eb;
                border: 1px solid #303448;
                selection-background-color: #3b82f6;
                border-radius: 6px;
                padding: 4px;
            }
            
            /* === Buttons === */
            QPushButton {
                background-color: #252836;
                color: #e1e4eb;
                border: 1px solid #303448;
                border-radius: 8px;
                padding: 9px 20px;
                font-weight: 500;
                font-size: 13px;
                min-height: 18px;
            }
            QPushButton:hover {
                background-color: #303448;
                border-color: #3b82f6;
            }
            QPushButton:pressed {
                background-color: #3b82f6;
                color: white;
            }
            QPushButton#primaryBtn {
                background-color: #3b82f6;
                border: none;
                color: white;
                font-weight: 600;
            }
            QPushButton#primaryBtn:hover {
                background-color: #2563eb;
            }
            QPushButton#primaryBtn:pressed {
                background-color: #1d4ed8;
            }
            QPushButton#dangerBtn {
                background-color: #dc2626;
                border: none;
                color: white;
                font-weight: 600;
            }
            QPushButton#dangerBtn:hover {
                background-color: #b91c1c;
            }
            QPushButton#successBtn {
                background-color: #16a34a;
                border: none;
                color: white;
                font-weight: 600;
            }
            QPushButton#successBtn:hover {
                background-color: #15803d;
            }
            
            /* === Checkbox === */
            QCheckBox {
                color: #c0c4d4;
                spacing: 8px;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #303448;
                border-radius: 4px;
                background-color: #1c1f2e;
            }
            QCheckBox::indicator:checked {
                background-color: #3b82f6;
                border-color: #3b82f6;
            }
            
            /* === Table === */
            QTableWidget {
                background-color: #161822;
                border: 1px solid #252836;
                border-radius: 8px;
                gridline-color: #252836;
                color: #e1e4eb;
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QTableWidget::item:selected {
                background-color: #252e4a;
                color: #f0f2f7;
            }
            QHeaderView::section {
                background-color: #1c1f2e;
                color: #7a7f94;
                border: none;
                border-bottom: 1px solid #252836;
                padding: 10px 8px;
                font-weight: 600;
                font-size: 12px;
                text-transform: uppercase;
            }
            
            /* === TextEdit (Log) === */
            QTextEdit {
                background-color: #0f1117;
                border: 1px solid #252836;
                border-radius: 8px;
                color: #a0a7b8;
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 12px;
                padding: 8px;
            }
            
            /* === ScrollBar === */
            QScrollBar:vertical {
                background: #0f1117;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #303448;
                border-radius: 4px;
                min-height: 32px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3b82f6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            
            /* === Slider === */
            QSlider::groove:horizontal {
                background: #252836;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #3b82f6;
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #2563eb;
            }
            QSlider::sub-page:horizontal {
                background: #3b82f6;
                border-radius: 3px;
            }
            
            /* === StatusBar === */
            QStatusBar {
                background-color: #161822;
                color: #565b6e;
                border-top: 1px solid #252836;
                font-size: 12px;
            }
            
            /* === Labels === */
            QLabel {
                color: #c0c4d4;
            }
            QLabel#sectionTitle {
                font-size: 15px;
                font-weight: 600;
                color: #e1e4eb;
            }
            QLabel#sectionDesc {
                font-size: 12px;
                color: #565b6e;
            }
            QLabel#fieldHint {
                font-size: 11px;
                color: #4a5068;
                font-style: italic;
            }
            QLabel#statusActive {
                color: #22c55e;
                font-weight: 600;
            }
            QLabel#statusInactive {
                color: #ef4444;
                font-weight: 600;
            }
            
            /* === Frame Separator === */
            QFrame#separator {
                background-color: #252836;
                max-height: 1px;
            }
        """)
    
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
        auth_group = QGroupBox('🔐  Authentication')
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
        meet_group = QGroupBox('📋  Meeting Configuration')
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
        storage_group = QGroupBox('📁  Storage Location')
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
        toggle_group = QGroupBox('⚡  Pipeline Status')
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
        profile_group = QGroupBox('👤  Your Profile')
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
        cred_group = QGroupBox('🔑  API Credentials')
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
        model_group = QGroupBox('🤖  Model Configuration')
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
        behavior_group = QGroupBox('🎛️  Pipeline Behavior')
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
        self.tray_icon.setToolTip('AutoMeet Attender')
        
        # Create tray menu
        tray_menu = QMenu()
        
        show_action = QAction('Show App', self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        quick_join_action = QAction('Quick Join', self)
        quick_join_action.triggered.connect(lambda: (self.show(), self.tabs.setCurrentIndex(1)))
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
            'AutoMeet Attender',
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
    app.setApplicationName('AutoMeet Attender')
    app.setQuitOnLastWindowClosed(False)  # Keep running in tray
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    run_gui()
