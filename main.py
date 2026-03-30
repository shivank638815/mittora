
"""
AutoMeet Attender - Main CLI Entry Point
Automated Google Meet attendance system with scheduling
"""
import sys
import os
import argparse
import signal
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.scheduler import MeetingScheduler
from src.meet_joiner import MeetJoiner


def print_banner():
    """Print application banner"""
    print("""
===========================================================
                                                           
           AutoMeet Attender v1.0                     
           Automated Google Meet Attendance System         
                                                           
===========================================================
""")


def join_now(meeting_url, meeting_name, duration):
    """
    Join a meeting immediately
    
    Args:
        meeting_url (str): Google Meet URL
        meeting_name (str): Name of the meeting
        duration (int): Duration to stay in minutes
    """
    print('\n🚀 Quick Join Mode\n')
    
    load_dotenv()
    
    config = {
        'headless': os.getenv('HEADLESS', 'false').lower() == 'true',
        'max_retries': int(os.getenv('MAX_RETRY_ATTEMPTS', '3')),
        'retry_delay': int(os.getenv('RETRY_DELAY_SECONDS', '30')),
        'greeting_message': os.getenv('GREETING_MESSAGE', 'Hello everyone'),
        'solo_timeout_minutes': int(os.getenv('SOLO_TIMEOUT_MINUTES', '8')),
        'max_meeting_minutes': int(os.getenv('MAX_MEETING_MINUTES', '240')),
        'audio_prefer_loopback': os.getenv('AUDIO_PREFER_LOOPBACK', 'true').lower() == 'true',
        'audio_device': os.getenv('AUDIO_DEVICE') or None,
        'audio_loopback_device_name': os.getenv('AUDIO_LOOPBACK_DEVICE_NAME') or None,
        'audio_sample_rate': int(os.getenv('AUDIO_SAMPLE_RATE', '16000')),
    }
    
    joiner = MeetJoiner(config)
    
    try:
        joiner.initialize()
        joiner.join_meeting(meeting_url, meeting_name)
    except Exception as error:
        print(f'❌ Error: {str(error)}')
    finally:
        joiner.close()


def run_scheduler():
    """Run the meeting scheduler"""
    meetings_config = Path(__file__).parent / 'meetings.json'
    
    scheduler = MeetingScheduler(meetings_config)
    
    if not scheduler.load_config():
        print('\n❌ Failed to load meetings configuration')
        print('📝 Please check your meetings.json file\n')
        sys.exit(1)
    
    scheduler.schedule_all_meetings()
    scheduler.start()
    
    print('🎯 AutoMeet Attender is now running...')
    print('💡 Press Ctrl+C to stop\n')
    print('📖 Usage:')
    print('   - Scheduled mode: python main.py (current mode)')
    print('   - Join now: python main.py join <meeting-url> [meeting-name] [duration]\n')
    print('   - GUI mode: python main.py gui\n')
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print('\n\n👋 Shutting down AutoMeet Attender...')
        scheduler.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Keep the process running
    try:
        while True:
            signal.pause()
    except AttributeError:
        # signal.pause() not available on Windows
        import time
        while True:
            time.sleep(1)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='AutoMeet Attender - Automated Google Meet Attendance System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                    # Run scheduler mode
  python main.py gui                                # Launch GUI application
  python main.py join <url>                         # Quick join a meeting
  python main.py join <url> "Team Meeting" 45       # Join with custom name and duration
        """
    )
    
    parser.add_argument(
        'mode',
        nargs='?',
        default='schedule',
        choices=['schedule', 'join', 'gui'],
        help='Operation mode: schedule (default), join, or gui'
    )
    
    parser.add_argument(
        'meeting_url',
        nargs='?',
        help='Meeting URL (required for join mode)'
    )
    
    parser.add_argument(
        'meeting_name',
        nargs='?',
        default='Quick Meeting',
        help='Meeting name (optional, for join mode)'
    )
    
    parser.add_argument(
        'duration',
        nargs='?',
        type=int,
        default=60,
        help='Duration in minutes (optional, for join mode)'
    )
    
    args = parser.parse_args()
    
    print_banner()
    
    # Handle different modes
    if args.mode == 'gui':
        # Launch GUI
        from src.gui_app import run_gui
        run_gui()
    
    elif args.mode == 'join':
        # Quick join mode
        if not args.meeting_url:
            print('❌ Error: Meeting URL is required for join mode')
            print('Usage: python main.py join <meeting-url> [meeting-name] [duration]')
            sys.exit(1)
        
        join_now(args.meeting_url, args.meeting_name, args.duration)
    
    else:
        # Scheduler mode (default)
        run_scheduler()


if __name__ == '__main__':
    main()
