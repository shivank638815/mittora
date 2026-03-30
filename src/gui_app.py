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
    QFileDialog
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
        self.setMinimumSize(900, 700)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Header
        header = QLabel('🤖 AutoMeet Attender')
        header.setStyleSheet('font-size: 24px; font-weight: bold; padding: 20px;')
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)
        
        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_meetings_tab(), '📅 Meetings')
        self.tabs.addTab(self.create_quick_join_tab(), '🚀 Quick Join')
        self.tabs.addTab(self.create_settings_tab(), '⚙️ Settings')
        main_layout.addWidget(self.tabs)
        
        # Status bar
        self.status_label = QLabel('Ready')
        self.statusBar().addWidget(self.status_label)
        
        self.meeting_count_label = QLabel('0 meetings scheduled')
        self.statusBar().addPermanentWidget(self.meeting_count_label)
    
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
        """Create the settings tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)
        
        # Authentication section
        auth_group = QLabel('Authentication')
        auth_group.setStyleSheet('font-size: 14px; font-weight: bold;')
        layout.addWidget(auth_group)
        
        setup_btn = QPushButton('🔐 Run Setup / Re-authenticate')
        setup_btn.clicked.connect(self.run_setup)
        layout.addWidget(setup_btn)
        
        layout.addSpacing(20)
        
        # Configuration section
        config_group = QLabel('Meeting Configuration')
        config_group.setStyleSheet('font-size: 14px; font-weight: bold;')
        layout.addWidget(config_group)
        
        form_layout = QFormLayout()
        
        self.headless_checkbox = QCheckBox('Run browser in headless mode (hidden)')
        form_layout.addRow('', self.headless_checkbox)
        
        self.solo_timeout_input = QSpinBox()
        self.solo_timeout_input.setRange(1, 60)
        self.solo_timeout_input.setValue(8)
        self.solo_timeout_input.setSuffix(' minutes')
        self.solo_timeout_input.setToolTip('If AutoMeet is alone in the meeting for this many minutes, it will leave.')
        form_layout.addRow('Solo Timeout:', self.solo_timeout_input)

        self.max_meeting_minutes_input = QSpinBox()
        self.max_meeting_minutes_input.setRange(5, 480)
        self.max_meeting_minutes_input.setValue(240)
        self.max_meeting_minutes_input.setSuffix(' minutes')
        self.max_meeting_minutes_input.setToolTip('Safety cap to avoid staying in meetings indefinitely.')
        form_layout.addRow('Max Meeting Length:', self.max_meeting_minutes_input)
        
        self.max_retries_input = QSpinBox()
        self.max_retries_input.setRange(1, 10)
        self.max_retries_input.setValue(3)
        form_layout.addRow('Max Retry Attempts:', self.max_retries_input)
        
        self.retry_delay_input = QSpinBox()
        self.retry_delay_input.setRange(5, 120)
        self.retry_delay_input.setValue(30)
        self.retry_delay_input.setSuffix(' seconds')
        form_layout.addRow('Retry Delay:', self.retry_delay_input)
        
        self.greeting_input = QLineEdit()
        self.greeting_input.setPlaceholderText('Hello everyone')
        form_layout.addRow('Greeting Message:', self.greeting_input)
        
        self.screenshot_threshold_input = QSpinBox()
        self.screenshot_threshold_input.setRange(1, 20)
        self.screenshot_threshold_input.setValue(5)
        self.screenshot_threshold_input.setToolTip('Lower = more sensitive (more screenshots), Higher = less sensitive (fewer screenshots)')
        form_layout.addRow('Screenshot Sensitivity:', self.screenshot_threshold_input)
        
        sensitivity_help = QLabel('Perceptual hash threshold (1-20). Lower values capture more changes.')
        sensitivity_help.setStyleSheet('color: gray; font-size: 10px;')
        form_layout.addRow('', sensitivity_help)
        
        layout.addLayout(form_layout)
        
        layout.addSpacing(20)
        
        # Storage location section
        storage_group = QLabel('Storage Location')
        storage_group.setStyleSheet('font-size: 14px; font-weight: bold;')
        layout.addWidget(storage_group)
        
        storage_desc = QLabel('Choose where to save chat logs and screenshots')
        storage_desc.setStyleSheet('color: gray; font-size: 10px;')
        layout.addWidget(storage_desc)
        
        storage_layout = QHBoxLayout()
        self.storage_path_input = QLineEdit()
        self.storage_path_input.setPlaceholderText('Select folder for logs and screenshots')
        self.storage_path_input.setReadOnly(True)
        storage_layout.addWidget(self.storage_path_input)
        
        browse_btn = QPushButton('📁 Browse')
        browse_btn.clicked.connect(self.browse_storage_folder)
        storage_layout.addWidget(browse_btn)
        
        layout.addLayout(storage_layout)
        
        storage_info = QLabel('Folders "All_Chatlogs" and "Screenshots" will be created automatically')
        storage_info.setStyleSheet('color: gray; font-size: 10px; font-style: italic;')
        layout.addWidget(storage_info)
        
        layout.addSpacing(10)
        
        save_settings_btn = QPushButton('💾 Save Settings')
        save_settings_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_settings_btn)
        
        layout.addStretch()
        
        widget.setLayout(layout)
        return widget
    
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
        
        self.headless_checkbox.setChecked(os.getenv('HEADLESS', 'false').lower() == 'true')
        self.solo_timeout_input.setValue(int(os.getenv('SOLO_TIMEOUT_MINUTES', '8')))
        self.max_meeting_minutes_input.setValue(int(os.getenv('MAX_MEETING_MINUTES', '240')))
        self.max_retries_input.setValue(int(os.getenv('MAX_RETRY_ATTEMPTS', '3')))
        self.retry_delay_input.setValue(int(os.getenv('RETRY_DELAY_SECONDS', '30')))
        self.greeting_input.setText(os.getenv('GREETING_MESSAGE', 'Hello everyone'))
        self.screenshot_threshold_input.setValue(int(os.getenv('SCREENSHOT_HASH_THRESHOLD', '5')))
        
        # Load storage path
        storage_path = os.getenv('STORAGE_PATH', '')
        if not storage_path:
            storage_path = str(Path(__file__).parent.parent)
        self.storage_path_input.setText(storage_path)
    
    def save_settings(self):
        """Save settings to .env file"""
        try:
            # Create .env if it doesn't exist
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
            
            # Reinitialize storage folders with new path
            self.init_storage_folders()
            
            QMessageBox.information(self, 'Success', 'Settings saved successfully!')
            self.restart_scheduler()
        except Exception as e:
            QMessageBox.warning(self, 'Error', f'Failed to save settings: {str(e)}')
    
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
