# 🤖 AutoMeet Attender

Automated Google Meet attendance system with scheduling - Python Desktop Application

## Features

- ✅ **Automated Meeting Joining**: Automatically join Google Meet meetings at scheduled times
- 📅 **Cron-based Scheduling**: Flexible scheduling using cron expressions
- 🖥️ **Desktop GUI**: Beautiful PySide6-based desktop application with system tray support
- 🚀 **Quick Join**: Instantly join meetings without scheduling
- 💬 **Auto Greeting**: Automatically send greeting messages in chat
- 🎤 **Media Control**: Automatically mute microphone and turn off camera
- 🔄 **Retry Logic**: Configurable retry attempts with delays
- 🔐 **Persistent Authentication**: One-time Google authentication setup
- 📊 **Meeting Management**: Add, edit, and delete scheduled meetings through GUI
- ⚙️ **Configurable Settings**: Customize behavior through settings panel
- 📸 **Intelligent Screenshots**: Perceptual hashing captures only unique screens (95%+ storage savings)
- 📁 **Custom Storage**: Choose folder location for chat logs and screenshots
- 📝 **Detailed Logging**: JSON logs with complete meeting timeline and events

## Requirements

- Python 3.8 or higher
- Windows/Linux/macOS
- Google Account
- Internet connection

## Installation

### 1. Clone or Download

```bash
cd d:\Mini_Projectt
```

### 2. Create Virtual Environment

```bash
python -m venv venv
```

### 3. Activate Virtual Environment

**Windows:**
```bash
venv\Scripts\activate
```

**Linux/macOS:**
```bash
source venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Install Playwright Browsers

```bash
playwright install chromium
```

### 6. Setup Environment

Copy `.env.example` to `.env`:

```bash
copy .env.example .env
```

Edit `.env` file to configure settings (optional).

## Setup Authentication

Before using the application, you need to authenticate with Google:

```bash
python setup.py
```

**Important Steps:**
1. A browser window will open
2. **Manually login** to your Google account
3. Complete any 2FA verification
4. Wait for redirect to Google Account page
5. Browser will close automatically
6. Authentication state is saved for future use

## Usage

### GUI Mode (Recommended)

Launch the desktop application:

```bash
python main.py gui
```

**GUI Features:**
- **Meetings Tab**: Manage scheduled meetings (add, edit, delete)
- **Quick Join Tab**: Join meetings instantly
- **Settings Tab**: Configure application behavior and re-authenticate
- **System Tray**: Minimize to tray, quick access menu

### CLI Mode

#### Run Scheduler (Automated Mode)

```bash
python main.py
```

This will:
- Load meetings from `meetings.json`
- Schedule all enabled meetings
- Run continuously in the background
- Press `Ctrl+C` to stop

#### Quick Join (Immediate)

```bash
python main.py join <meeting-url> [meeting-name] [duration]
```

**Examples:**

```bash
# Join with defaults
python main.py join https://meet.google.com/abc-defg-hij

# Join with custom name and duration
python main.py join https://meet.google.com/abc-defg-hij "Team Meeting" 45
```

## Configuration

### meetings.json

Configure scheduled meetings:

```json
{
  "meetings": [
    {
      "name": "Daily Standup",
      "url": "https://meet.google.com/xxx-yyyy-zzz",
      "schedule": "0 9 * * 1-5",
      "enabled": true,
      "duration": 30
    }
  ]
}
```

**Fields:**
- `name`: Meeting name (for logging)
- `url`: Google Meet URL
- `schedule`: Cron expression (see below)
- `enabled`: Enable/disable meeting
- `duration`: Minutes to stay in meeting

### Cron Schedule Examples

```
0 9 * * 1-5      # Weekdays at 9:00 AM
30 14 * * *      # Every day at 2:30 PM
0 10 * * 1       # Every Monday at 10:00 AM
0 15 * * 3,5     # Wednesday and Friday at 3:00 PM
*/30 * * * *     # Every 30 minutes
```

Use [crontab.guru](https://crontab.guru) for help with cron expressions.

### .env Configuration

```env
# Browser Configuration
HEADLESS=false                    # Run browser hidden (true/false)

# Meeting Configuration
STAY_DURATION_MINUTES=60          # Default meeting duration
MAX_RETRY_ATTEMPTS=3              # Retry attempts if join fails
RETRY_DELAY_SECONDS=30            # Delay between retries

# Chat Configuration
GREETING_MESSAGE=Hello everyone   # Auto-send message in chat
```

## Project Structure

```
d:\Mini_Projectt\
├── main.py                 # CLI entry point
├── setup.py                # Authentication setup script
├── requirements.txt        # Python dependencies
├── meetings.json           # Meeting schedules
├── .env                    # Configuration (create from .env.example)
├── .env.example            # Example configuration
├── README.md               # This file
├── auth-state/             # Authentication storage (auto-created)
│   └── google-auth.json
└── src/
    ├── __init__.py
    ├── meet_joiner.py      # Playwright automation
    ├── scheduler.py        # APScheduler integration
    └── gui_app.py          # PySide6 desktop GUI
```

## Troubleshooting

### Authentication Issues

If you get "Authentication state not found":

```bash
python setup.py
```

Complete the manual login process.

### Browser Not Opening

Make sure Playwright browsers are installed:

```bash
playwright install chromium
```

### Meeting Join Fails

1. Check your internet connection
2. Verify the meeting URL is correct
3. Ensure you're authenticated (run `python setup.py`)
4. Check if meeting requires host approval
5. Review logs for specific errors

### GUI Won't Start

Ensure PySide6 is installed:

```bash
pip install PySide6
```

### Scheduler Not Running

1. Verify `meetings.json` exists and is valid JSON
2. Check cron expressions are valid
3. Ensure at least one meeting is enabled
4. Check `.env` file exists

## Features in Detail

### Automatic Media Control

- Camera is automatically turned off before joining
- Microphone is automatically muted
- Verified after joining to ensure privacy

### Retry Logic

- Configurable retry attempts (default: 3)
- Delay between retries (default: 30 seconds)
- Detailed logging of each attempt

### Chat Greeting

- Automatically opens chat panel
- Sends configured greeting message
- Handles various Google Meet UI variations

### System Tray Integration

- Minimize to system tray
- Quick access menu
- Show/hide window
- Quick join shortcut

### Meeting Duration

- Stays in meeting for configured duration
- Periodic checks to ensure still connected
- Graceful exit after duration

## Command Reference

```bash
# Setup authentication
python setup.py

# Launch GUI
python main.py gui

# Run scheduler
python main.py

# Quick join
python main.py join <url> [name] [duration]

# Help
python main.py --help
```

## Security Notes

- Authentication tokens are stored locally in `auth-state/google-auth.json`
- Never share this file or commit it to version control
- Re-run `python setup.py` if authentication expires
- The `.gitignore` file excludes sensitive files by default

## Tips

1. **Test First**: Use quick join mode to test before scheduling
2. **Headless Mode**: Enable for production use (no browser window)
3. **Cron Testing**: Use [crontab.guru](https://crontab.guru) to validate schedules
4. **Backup Config**: Keep a backup of `meetings.json` and `.env`
5. **System Tray**: GUI runs in background when minimized

## Known Limitations

- Google Meet UI changes may require selector updates
- Host approval required for some meetings
- Network issues may cause join failures
- Windows: `signal.pause()` not available (uses polling instead)

## License

MIT License - Feel free to use and modify

## Support

For issues or questions:
1. Check troubleshooting section
2. Review logs for error messages
3. Verify configuration files
4. Test with quick join mode first

---

**Made with ❤️ using Python, Playwright, APScheduler, and PySide6**
