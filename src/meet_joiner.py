"""
MeetJoiner - Handles Google Meet automation using Playwright
"""
import os
import sys
import time
import json
import io
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import imagehash
from PIL import Image
from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright

from .stereo_mix_recorder import StereoMixRecorder
from .lockfile_cleanup import cleanup_with_retry

import logging
ai_logger = logging.getLogger('mittora.ai_pipeline')


def get_base_path():
    """
    Get the base path for the application.
    Works in both development mode and when compiled as EXE.
    
    Returns:
        Path: Base directory path
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled EXE - use executable's directory
        return Path(sys.executable).parent
    else:
        # Running as script - use script's parent directory
        return Path(__file__).parent.parent



class MeetJoiner:
    """Automates joining and managing Google Meet sessions"""
    
    def __init__(self, config=None):
        """
        Initialize MeetJoiner with configuration
        
        Args:
            config (dict): Configuration dictionary with keys:
                - headless (bool): Run browser in headless mode
                - solo_timeout_minutes (int): Minutes to wait when alone
                - max_meeting_minutes (int): Maximum time to stay in meeting
                - max_retries (int): Maximum retry attempts
                - retry_delay (int): Seconds between retries
                - greeting_message (str): Message to send in chat
        """
        self.config = config or {}
        self.headless = self.config.get('headless', False)
        self.solo_timeout_minutes = self.config.get('solo_timeout_minutes', 8)
        self.max_meeting_minutes = self.config.get('max_meeting_minutes', 240)
        self.max_retries = self.config.get('max_retries', 3)
        self.retry_delay = self.config.get('retry_delay', 30)
        self.greeting_message = self.config.get('greeting_message', 'Hello everyone')
        self.capture_screenshots = self.config.get('capture_screenshots', True)

        self.meeting_start_time = None
        self.last_meeting_duration_seconds = 0
        
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        
        # Auth file path (works in both dev and EXE mode)
        self.auth_file = get_base_path() / 'auth-state' / 'google-auth.json'
        
        # Storage paths
        self._init_storage_paths()
        
        # Chat log for current meeting
        self.chat_log = []
        
        # Track seen chat messages to avoid duplicates
        self.seen_messages = set()
        self.saved_chat_entries = set()
        
        # Chat monitoring with MutationObserver
        self.chat_observer_active = False
        self.chat_monitoring_enabled = True  # Can be disabled via config
        
        # Screenshot capture settings - OPTIMIZED with fast polling
        self.last_screenshot_hash = None
        self.last_screenshot_bytes = None  # Keep last screenshot for comparison
        load_dotenv()
        self.screenshot_hash_threshold = int(os.getenv('SCREENSHOT_HASH_THRESHOLD', '3')) # Lower threshold
        self.screenshot_interval = float(os.getenv('SCREENSHOT_INTERVAL_SECONDS', '1.5'))  # Fast 1.5-second checks
        self.screenshot_pixel_threshold = float(os.getenv('SCREENSHOT_PIXEL_THRESHOLD', '1.0'))  # 1.0% pixel difference

        # Stereo Mix audio recorder (folder assigned when meeting starts)
        self.audio_recorder = None
        self._audio_recording_started = False

        # AI Pipeline controller (initialized when meeting starts)
        self._ai_pipeline = None

        # Active meeting metadata
        self.current_meeting_name = None
        self.current_meeting_id = None
        self.chat_messages_path = None

    
    def initialize(self):
        """Initialize browser and context with saved authentication"""
        if not self.auth_file.exists():
            raise FileNotFoundError(
                'Authentication state not found. Please run: python setup.py'
            )
        
        print('🚀 Initializing browser...')
        
        # Clean up any stale lockfiles before launching browser
        user_data_dir = get_base_path() / 'playwright_profile'
        print('🧹 Checking for stale browser lockfiles...')
        
        try:
            cleanup_success = cleanup_with_retry(user_data_dir, max_retries=2, retry_delay=1.0)
            if not cleanup_success:
                print('⚠️  Lockfile cleanup failed - browser may not launch properly')
                print('💡 You may need to manually close any running Chrome instances')
        except Exception as e:
            print(f'⚠️  Error during lockfile cleanup: {str(e)}')
        
        # Initialize Playwright
        self.playwright = sync_playwright().start()
        
        # Find browser (Chrome or Chromium)
        import os
        user_home = Path.home()
        
        # Try Chrome first (most users have it)
        chrome_paths = [
            Path(os.environ.get('PROGRAMFILES', 'C:\\Program Files')) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
            Path(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)')) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
            Path(os.environ.get('LOCALAPPDATA', '')) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
        ]
        
        browser_exe = None
        browser_name = None
        
        # Check for Chrome
        for chrome_path in chrome_paths:
            if chrome_path.exists():
                browser_exe = chrome_path
                browser_name = "Chrome"
                print(f'✅ Found Chrome at: {browser_exe}')
                break
        
        # If Chrome not found, try Chromium
        if not browser_exe:
            system_chromium_path = user_home / 'AppData' / 'Local' / 'ms-playwright'
            if system_chromium_path.exists():
                for chromium_dir in system_chromium_path.glob('chromium-*'):
                    potential_exe = chromium_dir / 'chrome-win' / 'chrome.exe'
                    if potential_exe.exists():
                        browser_exe = potential_exe
                        browser_name = "Chromium"
                        print(f'✅ Found Chromium at: {browser_exe}')
                        break
        
        # If neither found, raise error
        if not browser_exe:
            raise FileNotFoundError(
                'No browser found!\n\n'
                'Please install one of:\n'
                '1. Google Chrome (recommended) - https://www.google.com/chrome/\n'
                '2. Playwright Chromium - Run: playwright install chromium'
            )
        
        # Launch browser with retry logic
        max_launch_retries = 3
        launch_retry_delay = 2
        
        for attempt in range(1, max_launch_retries + 1):
            try:
                print(f'🌐 Launching browser (attempt {attempt}/{max_launch_retries})...')
                
                self.context = self.playwright.chromium.launch_persistent_context(
                    str(user_data_dir),
                    headless=False,
                    executable_path=str(browser_exe),  # Use found browser (Chrome or Chromium)
                    args=[
                        '--start-maximized',
                        '--disable-blink-features=AutomationControlled',
                        '--use-fake-ui-for-media-stream',
                    ],
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    no_viewport=True,  # Allow browser to use native window size
                    timeout=30000,  # 30 second timeout for launch
                )
                
                # Get the page object from persistent context
                if len(self.context.pages) > 0:
                    self.page = self.context.pages[0]
                else:
                    self.page = self.context.new_page()
                
                # Note: browser object not available with persistent context
                self.browser = None
                
                print('✅ Browser initialized with persistent profile and native viewport')
                return  # Success - exit retry loop
                
            except Exception as e:
                print(f'❌ Browser launch attempt {attempt} failed: {str(e)}')
                
                # Clean up on failure
                try:
                    if self.context:
                        self.context.close()
                    if self.playwright:
                        self.playwright.stop()
                except:
                    pass
                
                self.context = None
                self.page = None
                self.playwright = None
                
                if attempt < max_launch_retries:
                    print(f'⏳ Retrying in {launch_retry_delay} seconds...')
                    time.sleep(launch_retry_delay)
                    
                    # Try cleanup again before retry
                    print('🧹 Re-attempting lockfile cleanup...')
                    try:
                        cleanup_with_retry(user_data_dir, max_retries=1, retry_delay=0.5)
                    except:
                        pass
                else:
                    raise Exception(f'Failed to launch browser after {max_launch_retries} attempts: {str(e)}')
    
    def _init_storage_paths(self):
        """Initialize storage paths for logs and screenshots"""
        load_dotenv()
        storage_path = os.getenv('STORAGE_PATH', '')
        
        if not storage_path:
            storage_path = str(get_base_path())
        
        self.storage_dir = Path(storage_path)
        
        # Current meeting folder (will be set when joining)
        self.current_meeting_folder = None
        self.chatlogs_dir = None
        self.screenshots_dir = None
    
    def join_meeting(self, meeting_url, meeting_name='Meeting'):
        """
        Join a Google Meet meeting
        
        Args:
            meeting_url (str): Google Meet URL
            meeting_name (str): Name of the meeting for logging
            
        Returns:
            bool: True if successfully joined and stayed, False otherwise
        """
        # Sanitize URL before attempting to join
        meeting_url = self._sanitize_meeting_url(meeting_url)
        
        attempt = 0
        
        while attempt < self.max_retries:
            try:
                attempt += 1
                print(f'\n📞 Attempt {attempt}/{self.max_retries}: Joining "{meeting_name}"')
                print(f'🔗 URL: {meeting_url}')
                
                self.page.goto(meeting_url, wait_until='domcontentloaded', timeout=60000)
                self.page.wait_for_timeout(3000)
                
                # Turn off camera and microphone before joining
                self._disable_media_devices()
                
                # Try to join the meeting
                joined = self._click_join_button()
                
                if joined:
                    print(f'✅ Successfully joined "{meeting_name}"')
                    
                    # Create dedicated folder for this meeting
                    self._create_meeting_folder(meeting_name)
                    self.current_meeting_name = meeting_name
                    
                    # Initialize chat log and screenshot tracking for this meeting
                    self.chat_log = []
                    self.seen_messages = set()
                    self.saved_chat_entries = set()
                    self.last_screenshot_hash = None
                    self._log_event('Meeting joined', meeting_name)
                    
                    # CREATE CHATLOG FILES IMMEDIATELY (don't wait for meeting to end)
                    self._initialize_chatlog_files(meeting_name)
                    
                    # Wait for meeting to fully load
                    self.page.wait_for_timeout(5000)
                    
                    # Optimize page display and prevent visual glitches
                    self._optimize_display()
                    
                    # Verify and ensure media devices are off
                    self._verify_media_devices_off()
                    
                    # Send greeting message
                    self._send_chat_message(self.greeting_message)

                    # Start audio recording
                    self._start_audio_recording(meeting_name)

                    # Initialize AI pipeline (hooks into audio stream)
                    self._initialize_ai_pipeline()

                    self.meeting_start_time = time.time()
                    self.last_meeting_duration_seconds = 0

                    print('⏱️  Monitoring meeting (dynamic departure mode)')
                    
                    # Stay in the meeting with participant-based monitoring and solo timeout tracking
                    duration_seconds = self._stay_in_meeting_with_monitoring()
                    self.last_meeting_duration_seconds = duration_seconds
                    self._log_event('Meeting duration', f'{duration_seconds/60:.2f} minutes recorded')
                    
                    print(f'👋 Leaving "{meeting_name}"')
                    self._log_event('Meeting ended', meeting_name)

                    # Save chat log (already saved in real-time)
                    self._save_chat_messages_immediate()

                    # Stop AI pipeline before stopping audio
                    self._shutdown_ai_pipeline()

                    # Generate meeting summary (JSON + PDF)
                    self._generate_meeting_summary(meeting_name)

                    # Stop audio recording
                    self._stop_audio_recording()

                    return True
                else:
                    raise Exception('Failed to click join button')
            
            except Exception as error:
                print(f'❌ Attempt {attempt} failed: {str(error)}')
                self._stop_audio_recording()  # Stop recording on error
                
                if attempt < self.max_retries:
                    print(f'⏳ Retrying in {self.retry_delay} seconds...')
                    time.sleep(self.retry_delay)
                else:
                    print(f'❌ Failed to join "{meeting_name}" after {self.max_retries} attempts')
                    return False
        
        return False
    
    def _optimize_display(self):
        """Optimize display to prevent visual glitches and ensure proper fullscreen"""
        # Disabled to prevent layout issues (cutting off bottom bar)
        pass
        # try:
        #     script = """
        #     () => {
        #         // Remove any scrollbars or margin issues
        #         document.body.style.overflow = 'hidden';
        #         document.body.style.margin = '0';
        #         document.body.style.padding = '0';
        #         document.documentElement.style.overflow = 'hidden';
        #         document.documentElement.style.margin = '0';
        #         document.documentElement.style.padding = '0';
        #         
        #         // Ensure viewport takes full screen
        #         const viewport = document.querySelector('meta[name="viewport"]');
        #         if (viewport) {
        #             viewport.setAttribute('content', 'width=device-width, initial-scale=1, maximum-scale=1');
        #         }
        #         
        #         // Hide any UI elements that might not fit properly
        #         const menus = document.querySelectorAll('[role="menu"], [role="dialog"]');
        #         menus.forEach(el => {
        #             if (el.offsetHeight > window.innerHeight * 0.9) {
        #                 el.style.maxHeight = (window.innerHeight - 50) + 'px';
        #                 el.style.overflowY = 'auto';
        #             }
        #         });
        #         
        #         return true;
        #     }
        #     """
        #     self.page.evaluate(script)
        #     print('✅ Display optimized for fullscreen')
        # except Exception as e:
        #     print(f'⚠️  Could not optimize display: {str(e)}')
    
    def _disable_media_devices(self):
        """Disable camera and microphone before joining"""
        print('🎤 Configuring media devices (mic/camera off)...')
        
        try:
            # Wait for media controls to load
            self.page.wait_for_timeout(2000)
            
            # Try multiple selectors for camera button (looking for enabled state)
            camera_selectors = [
                'div[data-is-muted="false"][aria-label*="camera" i]',
                'div[data-is-muted="false"][aria-label*="video" i]',
                'button[aria-label*="Turn off camera" i]',
                'button[aria-label*="camera" i]:not([aria-label*="Turn on"])',
                'div[role="button"][aria-label*="camera" i][data-is-muted="false"]',
            ]
            
            camera_off = False
            for selector in camera_selectors:
                try:
                    camera_button = self.page.query_selector(selector)
                    if camera_button:
                        camera_button.click()
                        print('📷 Camera turned off')
                        camera_off = True
                        self.page.wait_for_timeout(500)
                        break
                except:
                    continue
            
            if not camera_off:
                print('📷 Camera already off or not found')
            
            self._log_event('Media devices configured', 'Camera and microphone turned off')
            
            # Try multiple selectors for microphone button (looking for enabled state)
            mic_selectors = [
                'div[data-is-muted="false"][aria-label*="microphone" i]',
                'div[data-is-muted="false"][aria-label*="mic" i]',
                'button[aria-label*="Turn off microphone" i]',
                'button[aria-label*="microphone" i]:not([aria-label*="Turn on"])',
                'div[role="button"][aria-label*="microphone" i][data-is-muted="false"]',
            ]
            
            mic_off = False
            for selector in mic_selectors:
                try:
                    mic_button = self.page.query_selector(selector)
                    if mic_button:
                        mic_button.click()
                        print('🎤 Microphone muted')
                        mic_off = True
                        self.page.wait_for_timeout(500)
                        break
                except:
                    continue
            
            if not mic_off:
                print('🎤 Microphone already muted or not found')
        
        except Exception as error:
            print('⚠️  Could not configure media devices (they may already be off)')
    
    def _verify_media_devices_off(self):
        """Verify media devices are off after joining"""
        print('🔍 Verifying media devices are off...')
        
        try:
            # Check if camera is on and turn it off
            camera_on_selectors = [
                'button[aria-label*="Turn off camera" i]',
                'div[role="button"][aria-label*="camera" i][data-is-muted="false"]',
            ]
            
            for selector in camera_on_selectors:
                camera_button = self.page.query_selector(selector)
                if camera_button:
                    camera_button.click()
                    print('📷 Camera was on - turned off')
                    self.page.wait_for_timeout(500)
                    break
            
            # Check if microphone is on and turn it off
            mic_on_selectors = [
                'button[aria-label*="Turn off microphone" i]',
                'div[role="button"][aria-label*="microphone" i][data-is-muted="false"]',
            ]
            
            for selector in mic_on_selectors:
                mic_button = self.page.query_selector(selector)
                if mic_button:
                    mic_button.click()
                    print('🎤 Microphone was on - muted')
                    self.page.wait_for_timeout(500)
                    break
            
            print('✅ Media devices verified as off')
            self._log_event('Media verification', 'All media devices confirmed off')
        
        except Exception as error:
            print(f'⚠️  Could not verify media devices: {str(error)}')
    
    def _send_chat_message(self, message):
        """Send a message in the meeting chat"""
        print(f'💬 Sending chat message: "{message}"')
        
        try:
            self.page.wait_for_timeout(1000)
            
            # Broader chat input selectors (Google Meet 2025+)
            chat_input_selectors = [
                'textarea[aria-label*="Send a message" i]',
                'textarea[aria-label*="message" i]',
                'textarea[placeholder*="Send a message" i]',
                'textarea[placeholder*="message" i]',
                'div[contenteditable="true"][aria-label*="Send a message" i]',
                'div[contenteditable="true"][aria-label*="message" i]',
                'div[contenteditable="plaintext-only"][aria-label*="message" i]',
                'input[aria-label*="Send a message" i]',
                'input[aria-label*="message" i]',
                'input[placeholder*="Send a message" i]',
                'input[placeholder*="message" i]',
            ]
            
            # Step 1: Check if chat input is already visible (panel already open)
            chat_input = None
            for selector in chat_input_selectors:
                try:
                    el = self.page.query_selector(selector)
                    if el and el.is_visible():
                        chat_input = el
                        print('💬 Chat panel already open — input found')
                        break
                except:
                    continue
            
            # Step 2: If not found, toggle the chat panel open
            if not chat_input:
                chat_button_selectors = [
                    'button[aria-label*="Chat with everyone" i]',
                    'button[aria-label*="Chat" i]:not([aria-label*="caption"])',
                    'button[jsname][aria-label*="Chat" i]',
                    'div[role="button"][aria-label*="Chat" i]',
                    'button[data-tooltip*="Chat" i]',
                ]
                
                for selector in chat_button_selectors:
                    try:
                        chat_button = self.page.query_selector(selector)
                        if chat_button:
                            chat_button.click()
                            print('💬 Chat panel opened')
                            self.page.wait_for_timeout(1500)
                            break
                    except:
                        continue
                
                # Try finding input again after opening panel
                for selector in chat_input_selectors:
                    try:
                        el = self.page.query_selector(selector)
                        if el and el.is_visible():
                            chat_input = el
                            break
                    except:
                        continue
            
            # Step 3: Type and send
            if chat_input:
                chat_input.click()
                self.page.wait_for_timeout(300)
                
                # Clear any existing text
                chat_input.fill('') if hasattr(chat_input, 'fill') else None
                self.page.wait_for_timeout(200)
                
                chat_input.type(message, delay=50)
                print('✍️  Message typed')
                self.page.wait_for_timeout(500)
                
                # Press Enter to send
                self.page.keyboard.press('Enter')
                print('✅ Message sent successfully!')
                self._log_event('Chat message sent', message)
                self.page.wait_for_timeout(500)
                
                # Do NOT close chat panel — leave it open for monitoring
            else:
                print('⚠️  Could not find chat input field')
                # Take screenshot for debugging
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                screenshot_path = self.screenshots_dir / f'chat-debug_{timestamp}.png'
                self.page.screenshot(path=str(screenshot_path))
                print(f'📸 Debug screenshot saved to: {screenshot_path}')
                self._log_event('Screenshot', f'Debug screenshot: {screenshot_path.name}')
        
        except Exception as error:
            print(f'❌ Error sending chat message: {str(error)}')
            self._log_event('Error', f'Chat message error: {str(error)}')
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                screenshot_path = self.screenshots_dir / f'chat-error_{timestamp}.png'
                self.page.screenshot(path=str(screenshot_path))
                print(f'📸 Error screenshot saved to: {screenshot_path}')
                self._log_event('Screenshot', f'Error screenshot: {screenshot_path.name}')
            except:
                pass

    def _close_chat_panel(self):
        """Attempt to close/hide the chat panel to restore full-screen layout."""
        try:
            close_selectors = [
                'button[aria-label*="Close chat" i]',
                'button[aria-label*="Hide chat" i]',
                'button[aria-label*="Close" i][data-mdc-dialog-action]',
                'button[aria-pressed="true"][aria-label*="Chat" i]',
                'button[aria-pressed="true"][aria-label*="Open chat" i]',
            ]

            for selector in close_selectors:
                btn = self.page.query_selector(selector)
                if btn:
                    btn.click()
                    self.page.wait_for_timeout(500)
                    print('💬 Chat panel closed')
                    self._log_event('Chat panel closed', selector)
                    return

            self.page.keyboard.press('Escape')
            self.page.wait_for_timeout(200)
        except Exception as error:
            print(f'⚠️  Unable to close chat panel: {str(error)}')
    
    def _click_join_button(self):
        """Click the join button to enter the meeting"""
        print('🔘 Looking for join button...')
        
        # Wait a bit for the page to fully load
        self.page.wait_for_timeout(2000)
        
        # Multiple selectors for the join button (Google Meet changes these frequently)
        join_selectors = [
            'button:has-text("Ask to join")',
            'button:has-text("Join now")',
            'button[aria-label*="Ask to join" i]',
            'button[aria-label*="Join now" i]',
            'span:has-text("Ask to join")',
            'span:has-text("Join now")',
            'div[role="button"]:has-text("Ask to join")',
            'div[role="button"]:has-text("Join now")',
        ]
        
        for selector in join_selectors:
            try:
                button = self.page.query_selector(selector)
                if button:
                    button.click()
                    print('✅ Join button clicked')
                    self.page.wait_for_timeout(3000)
                    return True
            except:
                continue
        
        # If no button found, take a screenshot for debugging
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = self.screenshots_dir / f'join-debug_{timestamp}.png'
        self.page.screenshot(path=str(screenshot_path))
        print(f'📸 Screenshot saved to: {screenshot_path}')
        self._log_event('Screenshot', f'Join debug screenshot: {screenshot_path.name}')
        
        return False
    
    def _sanitize_meeting_url(self, url):
        """
        Sanitize and validate meeting URL, extracting the meeting code and reconstructing a clean URL
        
        Args:
            url (str): Raw meeting URL (may be malformed)
            
        Returns:
            str: Clean, valid meeting URL
        """
        import re
        
        # Remove whitespace
        url = url.strip()
        
        # Pattern for Google Meet code: xxx-xxxx-xxx (3-4-3 letters/numbers with dashes)
        # More permissive pattern to catch various formats
        code_pattern = r'([a-z]{3}-[a-z]{4}-[a-z]{3})'
        
        # Try to find the meeting code
        match = re.search(code_pattern, url, re.IGNORECASE)
        
        if match:
            code = match.group(1).lower()
            clean_url = f'https://meet.google.com/{code}'
            
            if clean_url != url:
                print(f'🔧 URL sanitized: {code}')
            
            return clean_url
        
        # If no code found, check if it's already a valid URL
        if url.startswith('https://meet.google.com/') and len(url) > 30:
            return url
        
        # If URL doesn't have protocol, add it
        if url.startswith('meet.google.com/'):
            return 'https://' + url
        
        # Last resort: return as-is and let Google Meet handle the error
        print(f'⚠️  Could not sanitize URL, using as-is: {url}')
        return url
    
    def _stay_in_meeting_with_monitoring(self):
        """Stay in the meeting with dynamic participant and activity monitoring."""
        max_duration_seconds = self.max_meeting_minutes * 60
        solo_timeout_seconds = self.solo_timeout_minutes * 60
        check_interval = 30  # seconds between participant checks
        last_screenshot_time = time.time()
        last_check_time = time.time()
        last_chat_poll_time = time.time()  # Track last chat poll
        start_time = time.time()
        solo_start = None

        # Setup simple chat monitoring (just open panel, no complex observer)
        if self.chat_monitoring_enabled:
            self._setup_chat_monitoring()

        if self.capture_screenshots:
            print(f'📸 Screenshot monitoring: OPTIMIZED (every {self.screenshot_interval}s with smart comparison)')
        else:
            print('🖥️  Screenshot monitoring disabled by configuration')

        while True:
            current_time = time.time()
            elapsed_seconds = current_time - start_time
            remaining_minutes = max(int((max_duration_seconds - elapsed_seconds) / 60), 0)
            
            if elapsed_seconds >= max_duration_seconds:
                print('⏳ Max meeting duration reached. Leaving meeting.')
                self._log_event('Leave condition', 'Max meeting duration reached')
                break

            # Check if still in meeting (every 30 seconds)
            if self.page.is_closed():
                print('❌ Browser closed by user or crashed. Exiting.')
                self._log_event('Leave condition', 'Browser closed')
                break

            if current_time - last_check_time >= check_interval:
                last_check_time = current_time
                print(f'⏰ Elapsed: {int(elapsed_seconds // 60)} min | Remaining cap: {remaining_minutes} min')
                
                try:
                    url = self.page.url
                    if 'meet.google.com' not in url:
                        print('⚠️  No longer in meeting (URL changed)')
                        self._log_event('Leave condition', 'URL changed / meeting ended')
                        break
                except Exception:
                    print('⚠️  Lost connection to meeting')
                    self._log_event('Leave condition', 'Lost connection to meeting')
                    break

                participant_count = self._get_participant_count()
                if participant_count is not None:
                    print(f'👥 Participants detected: {participant_count}')
                    if participant_count > 1:
                        solo_start = None
                    else:
                        if solo_start is None:
                            solo_start = time.time()
                            print('⏳ Alone in meeting. Starting solo timer...')
                            self._log_event('Solo timer start', 'Single participant detected')
                        elif time.time() - solo_start >= solo_timeout_seconds:
                            print('⏲️  Solo timeout reached. Leaving meeting.')
                            self._log_event('Leave condition', 'Solo timeout reached')
                            break
                else:
                    print('⚠️  Unable to detect participant count this cycle')

            # OPTIMIZED Screenshot capture - fast polling (every 2-3 seconds)
            if self.capture_screenshots and current_time - last_screenshot_time >= self.screenshot_interval:
                last_screenshot_time = current_time
                try:
                    self._capture_screenshot_optimized()
                except Exception as e:
                    print(f'⚠️  Screenshot error: {str(e)}')

            # NEW: Simple polling for chat messages (every 5 seconds)
            if self.chat_monitoring_enabled and current_time - last_chat_poll_time >= 5:
                last_chat_poll_time = current_time
                try:
                    self._poll_chat_messages()
                except Exception as e:
                    print(f'⚠️  Chat polling error: {str(e)}')

            # AI Pipeline: send any queued replies (runs on Playwright thread)
            if self._ai_pipeline and self._ai_pipeline.is_running:
                try:
                    pending_reply = self._ai_pipeline.get_pending_reply()
                    if pending_reply:
                        print(f'🤖 AI Pipeline reply → sending to chat: {pending_reply}')
                        self._send_chat_message(pending_reply)
                except Exception as e:
                    print(f'⚠️  AI reply send error: {str(e)}')

            time.sleep(1)  # Check every 1 second for better responsiveness

        return time.time() - start_time
    
    def _save_auth_state(self):
        """Save current authentication state to keep login persistent"""
        try:
            if self.context:
                self.context.storage_state(path=str(self.auth_file))
                print(f'💾 Authentication state saved: {self.auth_file}')
        except Exception as e:
            print(f'⚠️  Could not save auth state: {str(e)}')
    
    def close(self):
        """Close browser and cleanup resources"""
        try:
            # Save authentication state before closing (only if context still alive)
            if self.context and not getattr(self.context, '_closed', False):
                self._save_auth_state()

            # Close persistent context (browser not available with persistent context)
            if self.context:
                print('🔒 Closing browser context...')
                self.context.close()
                
                # Wait for browser to fully close
                time.sleep(1)
                print('✅ Browser context closed')

            if self.playwright:
                self.playwright.stop()
                print('✅ Playwright stopped')
            
            # Clean up any remaining lockfiles
            print('🧹 Cleaning up browser lockfiles...')
            user_data_dir = get_base_path() / 'playwright_profile'
            try:
                cleanup_with_retry(user_data_dir, max_retries=1, retry_delay=0.5)
            except Exception as e:
                print(f'⚠️  Lockfile cleanup warning: {str(e)}')
                
        except Exception as error:
            print(f'⚠️  Error closing browser: {str(error)}')
        finally:
            self._stop_audio_recording()  # Ensure audio recording is stopped
            
            # Reset state
            self.context = None
            self.page = None
            self.playwright = None



    
    def _create_meeting_folder(self, meeting_name):
        """Create a dedicated folder for this meeting's files"""
        import re
        safe_name = meeting_name.strip()
        # Remove all Windows-invalid path chars: \ / : * ? " < > |
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', safe_name)
        # Remove protocol prefix if URL was passed as name
        safe_name = re.sub(r'^https?__', '', safe_name)
        # Collapse multiple underscores
        safe_name = re.sub(r'_+', '_', safe_name).strip('_')
        safe_name = '_'.join(part for part in safe_name.split() if part) or 'Meeting'
        meeting_root = self.storage_dir / safe_name
        meeting_root.mkdir(parents=True, exist_ok=True)

        base_names = ['Screenshot', 'Chatlog', 'Audio']
        max_existing_index = 0

        for child in meeting_root.iterdir():
            if not child.is_dir():
                continue
            for base in base_names:
                if child.name == base:
                    max_existing_index = max(max_existing_index, 1)
                elif child.name.startswith(base):
                    suffix = child.name[len(base):]
                    if suffix.isdigit():
                        max_existing_index = max(max_existing_index, int(suffix))

        next_index = 1 if max_existing_index == 0 else max_existing_index + 1

        def create_subfolder(base_name: str) -> Path:
            suffix = '' if next_index == 1 else str(next_index)
            folder = meeting_root / f'{base_name}{suffix}'
            folder.mkdir(parents=True, exist_ok=True)
            return folder

        self.current_meeting_folder = meeting_root
        self.screenshots_dir = create_subfolder('Screenshot')
        self.chatlogs_dir = create_subfolder('Chatlog')
        self.audio_dir = create_subfolder('Audio')  # Empty folder for future audio implementation

        # Initialize stereo mix recorder with Audio folder (MP3 conversion enabled)
        self.audio_recorder = StereoMixRecorder(self.audio_dir, convert_to_mp3=True)

        print(f'📁 Meeting folder prepared: {meeting_root}')
        print(
            f'📂 Session directories → Screenshot: {self.screenshots_dir.name}, '
            f'Chatlog: {self.chatlogs_dir.name}, Audio: {self.audio_dir.name}'
        )



    def _start_audio_recording(self, meeting_name):
        """Start audio recording using Stereo Mix"""
        if not self.audio_recorder:
            print("⚠️  Audio recorder not initialized")
            return
            
        try:
            recording_path = self.audio_recorder.start(meeting_name)
            if recording_path:
                self._audio_recording_started = True
                print(f'🎙️  Audio recording started: {recording_path}')
            else:
                print("⚠️  Failed to start audio recording")
        except Exception as error:
            print(f'⚠️  Unable to start audio recording: {str(error)}')

    def _stop_audio_recording(self):
        """Stop audio recording if it is running"""
        if not self._audio_recording_started or not self.audio_recorder:
            return
            
        try:
            recording_path = self.audio_recorder.stop()
            if recording_path:
                print(f'💾 Audio recording saved: {recording_path}')
            self._audio_recording_started = False
        except Exception as error:
            print(f'⚠️  Unable to stop audio recording: {str(error)}')
            self._audio_recording_started = False

    def _initialize_ai_pipeline(self):
        """Initialize the AI pipeline and hook it into the audio stream."""
        load_dotenv()
        
        # Check if AI pipeline is enabled
        if os.getenv('AI_PIPELINE_ENABLED', 'true').lower() != 'true':
            print('🧠 AI Pipeline is DISABLED via config')
            return
        
        # Check for API key
        if not os.getenv('GROQ_API_KEY'):
            print('⚠️  GROQ_API_KEY not set — AI Pipeline disabled')
            return
        
        try:
            from .ai_pipeline.groq_client import GroqClient
            from .ai_pipeline.stt_engine import STTEngine
            from .ai_pipeline.transcript_manager import TranscriptManager
            from .ai_pipeline.llm_router import LLMRouter
            from .ai_pipeline.trigger_detector import TriggerDetector
            from .ai_pipeline.reply_engine import ReplyEngine
            from .ai_pipeline.pipeline_controller import PipelineController
            
            # Configure logging for AI pipeline
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
                datefmt='%H:%M:%S',
            )
            
            # Read config
            user_name = os.getenv('USER_DISPLAY_NAME', 'User')
            chunk_duration = float(os.getenv('CHUNK_DURATION', '20'))
            chunk_overlap = float(os.getenv('CHUNK_OVERLAP', '5'))
            reply_cooldown = float(os.getenv('REPLY_COOLDOWN', '60'))
            sample_rate = self.audio_recorder.sample_rate if self.audio_recorder else 44100
            channels = self.audio_recorder.channels if self.audio_recorder else 2
            
            # Build pipeline components
            groq_client = GroqClient()
            
            stt_engine = STTEngine(
                groq_client=groq_client,
                chunk_duration=chunk_duration,
                chunk_overlap=chunk_overlap,
                sample_rate=sample_rate,
                channels=channels,
            )
            
            transcript_manager = TranscriptManager(
                meeting_id=self.current_meeting_id or 'unknown',
                save_dir=self.chatlogs_dir,
            )
            
            llm_router = LLMRouter(groq_client=groq_client)
            
            trigger_detector = TriggerDetector(
                llm_router=llm_router,
                transcript_manager=transcript_manager,
                user_name=user_name,
            )
            
            reply_engine = ReplyEngine(
                llm_router=llm_router,
                user_name=user_name,
                user_role=os.getenv('USER_ROLE', ''),
                meeting_purpose=os.getenv('USER_MEETING_PURPOSE', ''),
                subject_domain=os.getenv('USER_SUBJECT_DOMAIN', ''),
                response_style=os.getenv('USER_RESPONSE_STYLE', 'Casual'),
            )
            
            pipeline = PipelineController(
                groq_client=groq_client,
                stt_engine=stt_engine,
                transcript_manager=transcript_manager,
                trigger_detector=trigger_detector,
                reply_engine=reply_engine,
                chat_sender=self._send_chat_message,
                reply_cooldown=reply_cooldown,
            )
            
            # Hook into audio stream
            if self.audio_recorder:
                self.audio_recorder.register_chunk_listener(pipeline.on_audio_chunk)
                print('🔗 AI Pipeline hooked into audio stream')
            
            # Start the pipeline
            pipeline.start()
            self._ai_pipeline = pipeline
            
            print(f'🧠 AI Pipeline ACTIVE — monitoring for "{user_name}"')
            print(f'   Chunk: {chunk_duration}s | Cooldown: {reply_cooldown}s')
            
        except Exception as error:
            print(f'⚠️  Failed to initialize AI Pipeline: {str(error)}')
            import traceback
            traceback.print_exc()
            self._ai_pipeline = None

    def _shutdown_ai_pipeline(self):
        """Gracefully shut down the AI pipeline."""
        if self._ai_pipeline:
            try:
                self._ai_pipeline.stop()
                print('🧠 AI Pipeline stopped')
            except Exception as error:
                print(f'⚠️  Error stopping AI Pipeline: {str(error)}')
            finally:
                self._ai_pipeline = None

    def _generate_meeting_summary(self, meeting_name):
        """Generate meeting summary (JSON + PDF) from transcript after meeting ends."""
        if not self.chatlogs_dir:
            print('⚠️  No chatlog directory — skipping summary generation')
            return

        transcript_path = self.chatlogs_dir / 'ai_transcript.json'
        if not transcript_path.exists():
            print('⚠️  No transcript file found — skipping summary generation')
            return

        try:
            from .ai_pipeline.summary_engine import SummaryEngine
            from .ai_pipeline.groq_client import GroqClient
            from .ai_pipeline.llm_router import LLMRouter

            print('📝 Generating meeting summary...')

            # Load transcript text
            transcript_text = SummaryEngine.load_transcript_from_file(transcript_path)
            if not transcript_text:
                print('⚠️  Transcript too short for summary generation')
                return

            # Build summary engine
            groq_client = GroqClient()
            llm_router = LLMRouter(groq_client=groq_client)
            engine = SummaryEngine(llm_router=llm_router)

            # Generate summary
            summary = engine.generate(transcript_text, meeting_name=meeting_name)
            if not summary:
                print('⚠️  Summary generation failed')
                return

            # Save JSON
            json_path = engine.save_summary(summary, self.chatlogs_dir)
            if json_path:
                print(f'📋 Summary saved: {json_path.name}')

            # Export PDF
            pdf_path = engine.export_pdf(summary, self.chatlogs_dir)
            if pdf_path:
                print(f'📄 Summary PDF exported: {pdf_path.name}')

        except ImportError as e:
            print(f'⚠️  Summary dependencies not available: {e}')
        except Exception as error:
            print(f'⚠️  Summary generation error: {str(error)}')
            import traceback
            traceback.print_exc()

    
    def _log_event(self, event_type, details):
        """Log an event to the chat log"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = {
            'timestamp': timestamp,
            'event': event_type,
            'details': details
        }
        self.chat_log.append(log_entry)
    

    
    def _calculate_image_hash(self, image_bytes):
        """Calculate perceptual hash of an image"""
        try:
            image = Image.open(io.BytesIO(image_bytes))
            # Use average hash for perceptual comparison
            return imagehash.average_hash(image)
        except Exception as e:
            print(f'⚠️  Error calculating image hash: {str(e)}')
            return None
    
    def _calculate_pixel_difference(self, img1_bytes, img2_bytes):
        """Calculate pixel-level difference between two images (returns percentage 0-100)"""
        try:
            import numpy as np
            
            # Open both images
            img1 = Image.open(io.BytesIO(img1_bytes)).convert('RGB')
            img2 = Image.open(io.BytesIO(img2_bytes)).convert('RGB')
            
            # Resize to same size if needed (use smaller size for efficiency)
            if img1.size != img2.size:
                # Resize to smaller dimensions for faster comparison
                target_size = (min(img1.width, img2.width), min(img1.height, img2.height))
                img1 = img1.resize(target_size)
                img2 = img2.resize(target_size)
            
            # Convert to numpy arrays
            arr1 = np.array(img1, dtype=np.float32)
            arr2 = np.array(img2, dtype=np.float32)
            
            # Calculate mean absolute difference
            diff = np.abs(arr1 - arr2)
            mean_diff = np.mean(diff)
            
            # Convert to percentage (0-255 scale to 0-100%)
            percentage = (mean_diff / 255.0) * 100.0
            
            return percentage
            
        except Exception as e:
            print(f'⚠️  Error calculating pixel difference: {str(e)}')
            # Return high value to force saving on error
            return 100.0
    
    def _capture_screenshot_optimized(self):
        """OPTIMIZED screenshot capture with fast 2-3s polling and smart comparison"""
        try:
            # Validate screenshot directory exists
            if not self.screenshots_dir:
                return
            
            if not self.screenshots_dir.exists():
                self.screenshots_dir.mkdir(parents=True, exist_ok=True)
            
            # Check if browser is already closed
            if self.page.is_closed():
                return
            
            # Take screenshot in memory
            screenshot_bytes = self.page.screenshot()
            
            # Calculate perceptual hash (fast preliminary check)
            current_hash = self._calculate_image_hash(screenshot_bytes)
            
            if current_hash is None:
                return
            
            # Determine if we should save this screenshot
            should_save = False
            save_reason = ""
            
            if self.last_screenshot_hash is None:
                # First screenshot - always save
                should_save = True
                save_reason = "first"
            else:
                # Quick hash comparison
                hash_diff = current_hash - self.last_screenshot_hash
                
                if hash_diff > self.screenshot_hash_threshold:
                    # Hash differs - now do detailed pixel comparison
                    pixel_diff = self._calculate_pixel_difference(self.last_screenshot_bytes, screenshot_bytes)
                    
                    if pixel_diff >= self.screenshot_pixel_threshold:
                        should_save = True
                        save_reason = f"changed (hash:{hash_diff}, pixels:{pixel_diff:.1f}%)"
                    else:
                        # Hash differs but pixels are similar (minor UI changes)
                        save_reason = f"minor change (hash:{hash_diff}, pixels:{pixel_diff:.1f}%)"
            
            if should_save:
                # Save the screenshot
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                screenshot_path = self.screenshots_dir / f'meeting_{timestamp}.png'
                
                with open(screenshot_path, 'wb') as f:
                    f.write(screenshot_bytes)
                
                print(f'📸 Screenshot saved: {screenshot_path.name} ({save_reason})')
                self._log_event('Screenshot', f'{screenshot_path.name} - {save_reason}')
                
                # Update tracking
                self.last_screenshot_hash = current_hash
                self.last_screenshot_bytes = screenshot_bytes
            else:
                # Not different enough - skip
                if save_reason:
                    print(f'⏭️  Screen unchanged or {save_reason} - skipped')
                
        except Exception as e:
            error_msg = str(e)
            if "Target page, context or browser has been closed" in error_msg:
                print('⚠️  Browser closed during screenshot capture')
                return
            print(f'⚠️  Screenshot error: {error_msg}')



    def _get_participant_count(self):
        """Attempt to read the current participant count from the meeting UI."""
        try:
            script = r"""
            () => {
                const selectors = [
                    'button[aria-label*="people" i]',
                    'button[aria-label*="participants" i]',
                    'button[aria-label*="show everyone" i]',
                    '[aria-label*="people" i][role="button"]'
                ];

                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const label = (el.getAttribute('aria-label') || el.textContent || '').trim();
                        const match = label.match(/\d+/);
                        if (match) {
                            return parseInt(match[0], 10);
                        }
                    }
                }

                const badge = document.querySelector('[aria-label*="People" i] span');
                if (badge && badge.textContent) {
                    const match = badge.textContent.match(/\d+/);
                    if (match) {
                        return parseInt(match[0], 10);
                    }
                }

                const participantNodes = document.querySelectorAll('[data-participant-id], [data-fps-request-id]');
                if (participantNodes && participantNodes.length) {
                    return participantNodes.length;
                }
                return null;
            }
            """

            count = self.page.evaluate(script)
            if count is not None:
                return int(count)
        except Exception as error:
            print(f'⚠️  Unable to detect participant count: {str(error)}')
            self._log_event('Participant detection error', str(error))
        return None
    
    def _open_chat_panel_persistent(self):
        """Open chat panel once and keep it open for the duration of the meeting"""
        try:
            print('💬 Opening chat panel for message monitoring...')
            
            # Check if chat is already open
            close_button_selectors = [
                'button[aria-label*="Close chat" i]',
                'button[aria-label*="Hide chat" i]',
            ]
            
            for selector in close_button_selectors:
                if self.page.query_selector(selector):
                    print('💬 Chat panel already open')
                    return True
            
            # Try to open chat panel
            chat_button_selectors = [
                'button[aria-label*="Chat" i]:not([aria-label*="caption"])',
                'button[jsname][aria-label*="Chat" i]',
                'div[role="button"][aria-label*="Chat" i]',
                'button[data-tooltip*="Chat" i]',
                '[aria-label*="Chat with everyone" i]',
            ]
            
            for selector in chat_button_selectors:
                try:
                    chat_button = self.page.query_selector(selector)
                    if chat_button:
                        chat_button.click()
                        self.page.wait_for_timeout(1000)  # Wait for chat to open
                        print('✅ Chat panel opened successfully')
                        
                        # Hide the panel visually to remove the white strip
                        self._hide_chat_panel_visuals()
                        
                        return True
                except Exception as e:
                    continue
            
            print('⚠️  Could not find chat button')
            return False
            
        except Exception as e:
            print(f'⚠️  Error opening chat panel: {str(e)}')
            return False
    
    def _hide_chat_panel_visuals(self):
        """NUCLEAR OPTION: Use display:none to completely hide the panel"""
        try:
            script = """
            () => {
                console.log('🔨 Starting nuclear panel hiding...');
                
                const hidePanel = () => {
                    // Find the panel by looking for the close button
                    const closeButton = document.querySelector('button[aria-label*="Close"], button[aria-label*="Hide"]');
                    
                    if (closeButton) {
                        console.log('✓ Close button found');
                        
                        // Find the side panel container
                        let panel = closeButton.closest('div[role="complementary"]');
                        
                        // Fallback: try other selectors
                        if (!panel) {
                            const selectors = ['.bsU9b', '.R5ccN', '[data-panel-id]'];
                            for (const sel of selectors) {
                                panel = document.querySelector(sel);
                                if (panel) break;
                            }
                        }
                        
                        if (panel) {
                            // NUCLEAR: Just hide it completely
                            panel.style.display = 'none';
                            console.log('💥 Panel hidden with display:none');
                            return true;
                        } else {
                            console.log('✗ Could not find panel container');
                        }
                    } else {
                        console.log('✗ Close button not found - panel might not be open');
                    }
                    
                    return false;
                };
                
                // Try immediately
                const success = hidePanel();
                
                // Keep trying every 100ms for 5 seconds
                let attempts = 0;
                const maxAttempts = 50;
                const interval = setInterval(() => {
                    attempts++;
                    if (hidePanel() || attempts >= maxAttempts) {
                        clearInterval(interval);
                        console.log(`Hiding attempts: ${attempts}`);
                    }
                }, 100);
                
                return success;
            }
            """
            result = self.page.evaluate(script)
            if result:
                print('👻 ✅ Panel hidden successfully (display:none)')
            else:
                print('👻 ⚠️  Panel hiding queued (will retry)')
        except Exception as e:
            print(f'❌ Could not hide chat panel: {e}')
    
    
    def _setup_chat_monitoring(self):
        """Setup simple chat monitoring - just open the panel and keep it ready"""
        try:
            print('💬 Setting up simple chat monitoring...')
            
            # Open chat panel once
            chat_opened = self._open_chat_panel_once()
            
            if not chat_opened:
                print('⚠️  Could not open chat - will retry during monitoring')
                return False
            
            # Wait for chat to load
            self.page.wait_for_timeout(2000)
            
            # Hide chat panel visually to avoid white strip
            self._hide_chat_panel_visual()
            
            print('✅ Simple chat monitoring ready (polling-based)')
            return True
            
        except Exception as e:
            print(f'⚠️  Error setting up chat monitoring: {str(e)}')
            return False
    
    def _open_chat_panel_once(self):
        """Open chat panel once and keep it open"""
        try:
            # Check if already open
            if self.page.query_selector('button[aria-label*="Close chat" i], button[aria-label*="Hide chat" i]'):
                print('💬 Chat panel already open')
                return True
            
            # Try multiple selectors to open chat
            chat_selectors = [
                'button[aria-label*="Chat with everyone" i]',
                'button[aria-label*="Open chat" i]',
                'button[aria-label*="Chat" i]:not([aria-label*="caption" i])',
                'div[role="button"][aria-label*="Chat" i]',
                '[data-tooltip*="Chat" i]',
            ]
            
            for selector in chat_selectors:
                try:
                    btn = self.page.query_selector(selector)
                    if btn:
                        btn.click()
                        self.page.wait_for_timeout(1000)
                        print(f'💬 Chat panel opened with: {selector}')
                        return True
                except:
                    continue
            
            print('⚠️  Could not find chat button')
            return False
            
        except Exception as e:
            print(f'⚠️  Error opening chat panel: {str(e)}')
            return False

    def _initialize_chatlog_files(self, meeting_name):
        """Initialize chat messages JSON file with specific format"""
        try:
            if not self.chatlogs_dir:
                print('⚠️  Cannot initialize chatlog files - no chatlogs directory')
                return
            
            print(f'🔧 Initializing chat messages file in: {self.chatlogs_dir}')
            
            # Ensure directory exists
            self.chatlogs_dir.mkdir(parents=True, exist_ok=True)
            
            chat_messages_path = self.chatlogs_dir / 'chat_messages.json'
            
            # Generate short meeting ID (random 4 chars)
            import random
            import string
            short_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            meeting_id = f"meet-{short_id}"
            
            # Current time for start with specific format: Time - 14:55 , Date - 23 -11-2025
            now = datetime.now()
            
            # Initial structure
            initial_data = {
                "meeting_id": meeting_id,
                "date": now.strftime('%d-%m-%Y'),
                "chat_log": []
            }
            
            with open(chat_messages_path, 'w', encoding='utf-8') as f:
                json.dump(initial_data, f, indent=2, ensure_ascii=False)
            
            self.chat_messages_path = chat_messages_path
            self.current_meeting_id = meeting_id
            self.saved_chat_entries = set()
            print(f'✅ Created: {chat_messages_path}')
            print(f'✅ Chat messages file initialized with ID: {meeting_id}')
            
        except Exception as e:
            import traceback
            print(f'❌ Error initializing chat messages file: {str(e)}')
            print(f'❌ Traceback: {traceback.format_exc()}')

    def _poll_chat_messages(self):
        """Aggressive polling: Extract ALL text from chat panel and parse it"""
        try:
            if self.page.is_closed():
                return

            # Extract full text from the side panel
            script = """
            () => {
                // Try to find the side panel
                const panel = document.querySelector('div[role="complementary"]') || 
                              document.querySelector('div[data-panel-id]') ||
                              document.querySelector('.bsU9b'); // Common class for side panel
                              
                if (panel) {
                    return panel.innerText || panel.textContent;
                }
                
                // Fallback: Look for any container with "In-call messages" or similar header
                const headers = document.querySelectorAll('h2, h3, div[role="heading"]');
                for (const h of headers) {
                    if ((h.innerText || '').toLowerCase().includes('messages')) {
                        // Return the parent container's text
                        return h.closest('div').parentElement.innerText;
                    }
                }
                
                return "";
            }
            """
            
            full_panel_text = self.page.evaluate(script)
            
            if full_panel_text and len(full_panel_text) > 10:
                self._parse_full_chat_text(full_panel_text)
                    
        except Exception as e:
            error_msg = str(e)
            if "Target page, context or browser has been closed" in error_msg:
                print('⚠️  Browser closed during chat polling')
                return
            print(f'⚠️  Polling extraction error: {error_msg}')

    def _is_valid_sender_name(self, name):
        """Check if a string looks like a valid sender name"""
        # 1. Length check (names are usually short)
        if len(name) > 30 or len(name) < 2:
            return False
            
        # 2. Punctuation check (names don't usually have sentence punctuation)
        # Allow parentheses for "(Company)" but not sentence punctuation
        if any(char in name for char in ['?', '!', ',']):
            return False
        
        # Check for period not at end (e.g., "Dr. Smith" is ok, but "Hello. How" is not)
        if '.' in name and not name.endswith('.'):
            # Allow initials like "J. Smith"
            parts = name.split('.')
            if len(parts) > 2 or (len(parts) == 2 and len(parts[0]) > 2):
                return False
            
        # 3. Word count check (most names are 1-4 words)
        words = name.split()
        if len(words) > 4:
            return False
        
        if len(words) == 0:
            return False
            
        # 4. Common sentence starters check
        sentence_starters = {
            'can', 'what', 'where', 'how', 'why', 'are', 'is', 'do', 'did', 'could', 'would', 'should',
            'hello', 'hi', 'hey', 'good', 'thanks', 'thank', 'yes', 'no', 'ok', 'okay', 'because', 'beacause'
        }
        if words[0].lower() in sentence_starters:
            return False
            
        # 5. Common message patterns that are definitely not names
        message_patterns = {
            'i am', 'i think', 'i have', 'i want', 'i need', 'i will', 'i can', 'i was',
            'you are', 'you have', 'you will', 'you can', 'you should', 'you were',
            'we are', 'we have', 'we will', 'we can', 'we should', 'we were',
            'they are', 'they have', 'they will', 'they can', 'they should', 'they were',
            'this is', 'that is', 'there is', 'here is', 'it is', 'it was',
            'toggle is', 'goat is', 'my name is', 'because it', 'beacause it'
        }
        
        name_lower = name.lower()
        for pattern in message_patterns:
            if name_lower.startswith(pattern):
                return False
        
        # 6. Check if it looks like a continuation of a sentence (lowercase start after first word)
        if len(words) > 1:
            # If multiple words and most are lowercase common words, likely a message
            common_words = {'is', 'are', 'was', 'were', 'the', 'a', 'an', 'it', 'to', 'for', 'of', 'in', 'on', 'at'}
            lowercase_common = sum(1 for w in words[1:] if w.lower() in common_words)
            if lowercase_common >= len(words) - 1:
                return False
            
        return True
    def _parse_full_chat_text(self, text):
        """Parse the full text dump from the chat panel"""
        try:
            import re
            
            # Split into lines
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            print(f'🔍 Parsing {len(lines)} lines from panel')
            
            # UI noise to filter out
            ui_noise = {
                'keep', 'pin message', 'send', 'send message', 'send a message',
                'in-call messages', 'messages can only be seen by people in the call',
                'and are deleted when the call ends', 'close', 'let participants send messages',
                'chat', 'continuous chat is off', 'continuous chat is on'
            }
            
            # Regex for time (e.g., 11:57 AM or 3:00 PM or 10:37)
            time_pattern = re.compile(r'^\d{1,2}:\d{2}(\s*[AP]M)?$', re.IGNORECASE)
            combined_name_time_pattern = re.compile(
                r'^(?P<name>.+?)\s+(?P<time>\d{1,2}:\d{2}(?:\s*[AP]M)?)$',
                re.IGNORECASE,
            )
            
            current_sender = None
            current_time = None
            last_message = None  # Track last message to prevent it becoming a sender
            i = 0
            
            while i < len(lines):
                line = lines[i]
                
                # Check if name and timestamp appear on the same line (new Meet layout)
                combined_match = combined_name_time_pattern.match(line)
                if combined_match:
                    potential_name = combined_match.group('name').strip()
                    timestamp = combined_match.group('time').strip()

                    # KEY FIX: Validate it's not UI noise AND not the previous message AND passes validation
                    if (potential_name.lower() not in ui_noise and 
                        potential_name != last_message and
                        self._is_valid_sender_name(potential_name)):
                        
                        current_sender = potential_name
                        current_time = timestamp
                        print(f'🔍 Sender detected (inline): "{current_sender}" at {current_time}')
                        i += 1
                        continue

                    # If it isn't a valid sender, treat the name part as a message
                    if current_sender and potential_name.lower() not in ui_noise:
                        self._process_parsed_message(current_sender, potential_name, current_time or '')
                        last_message = potential_name
                    i += 1
                    continue

                # Check if next line is a timestamp
                if i + 1 < len(lines) and time_pattern.match(lines[i + 1]):
                    potential_name = line
                    timestamp = lines[i + 1]
                    
                    # Validate it's not UI noise
                    if potential_name.lower() in ui_noise:
                        i += 2
                        continue
                    
                    # KEY FIX: Validate it looks like a name AND is not the last message
                    # Check all three conditions: validation, not last message, not UI noise
                    if (not self._is_valid_sender_name(potential_name) or 
                        potential_name == last_message):
                        
                        # It's NOT a valid name, so it must be a message.
                        if current_sender:
                            self._process_parsed_message(current_sender, potential_name, current_time or '')
                            last_message = potential_name
                            print(f'💬 Message (rejected as sender): "{potential_name}"')
                        
                        # Move past both lines
                        i += 2
                        continue

                    # Valid sender found - all checks passed
                    current_sender = potential_name
                    current_time = timestamp
                    print(f'🔍 Sender detected (multi-line): "{current_sender}" at {current_time}')
                    
                    # Skip name and timestamp
                    i += 2
                    continue
                
                # Standalone timestamp (skip)
                if time_pattern.match(line):
                    i += 1
                    continue
                
                # UI noise (skip)
                if line.lower() in ui_noise:
                    i += 1
                    continue
                
                # Any other line with a current sender = message
                if current_sender and len(line) > 0 and line.lower() not in ui_noise:
                    self._process_parsed_message(current_sender, line, current_time or '')
                    last_message = line
                
                i += 1
                
        except Exception as e:
            print(f'⚠️  Text parsing error: {str(e)}')
    def _process_parsed_message(self, sender, message, time_str):
        """Process and save a parsed message"""
        # Filter noise
        if not message or not sender:
            return
        
        # Filter out UI noise senders and messages
        noise_words = {
            'chat', 'messages', 'in-call messages',
            'keep', 'pin message', 'send', 'send message', 'send a message',
            'okay', 'pin', 'message'
        }
        
        if sender.lower() in noise_words or message.lower() in noise_words:
            return
        
        # Filter very short messages (likely noise)
        if len(message) < 2:
            return
            
        # Deduplication
        dedup_key = f"{sender}|{message}"
        if dedup_key in self.seen_messages:
            return
            
        self.seen_messages.add(dedup_key)
        
        # Add to log
        chat_entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event': 'Chat Message',
            'sender': sender,
            'message': message,
            'time': time_str
        }
        
        self.chat_log.append(chat_entry)
        print(f'💬 NEW: {sender}: {message}')
        
        # Save to file
        self._save_chat_messages_immediate()

    def _hide_chat_panel_visual(self):
        """Hide chat panel visually while keeping it open in DOM"""
        try:
            script = """
            () => {
                const closeBtn = document.querySelector('button[aria-label*="Close" i], button[aria-label*="Hide" i]');
                if (closeBtn) {
                    let panel = closeBtn.closest('[role="complementary"]');
                    if (!panel) {
                        panel = closeBtn.closest('div[class*="panel"], div[class*="sidebar"]');
                    }
                    if (panel) {
                        panel.style.display = 'none';
                        console.log('Chat panel hidden visually');
                        return true;
                    }
                }
                return false;
            }
            """
            self.page.evaluate(script)
        except Exception as e:
            print(f'⚠️  Could not hide chat panel: {str(e)}')

    def _parse_and_save_message(self, raw_text):
        """Parse raw message text and save with deduplication (Python-side processing)"""
        try:
            import re
            
            # Clean up text
            text = raw_text.strip()
            
            # Remove common noise
            noise_patterns = [
                r'keep\s*Pin\s*message',
                r'Pin\s*message',
                r'Message from',
            ]
            for pattern in noise_patterns:
                text = re.sub(pattern, '', text, flags=re.IGNORECASE)
            text = text.strip()
            
            if not text or len(text) < 2:
                return
            
            # Split into lines
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            if len(lines) < 2:
                return
            
            # Parse sender and message
            # Format is typically: "Sender Name\n12:34 PM\nMessage content"
            # or: "Sender Name\nMessage content"
            sender = None
            message_lines = []
            time_str = None
            
            # Regex to identify timestamps
            time_pattern = re.compile(r'^\d{1,2}:\d{2}\s*[AP]M$', re.IGNORECASE)
            
            # First line is usually sender
            potential_sender = lines[0]
            
            # Validate sender (not timestamp, not URL, reasonable length)
            if (not time_pattern.match(potential_sender) and
                not potential_sender.startswith('http') and
                '://' not in potential_sender and
                1 < len(potential_sender) < 50 and
                not potential_sender.lower() in ['you', 'me', 'pin', 'keep']):
                sender = potential_sender
                remaining_lines = lines[1:]
            else:
                # First line is not sender, use "Unknown"
                sender = "Unknown"
                remaining_lines = lines
            
            # Extract time and message from remaining lines
            for line in remaining_lines:
                # Skip "You" labels
                if line.lower() in ['you', 'me']:
                    continue
                
                # Check if it's a timestamp
                if time_pattern.match(line):
                    time_str = line
                    continue
                
                # Skip if it's just the sender name repeated
                if sender and line == sender:
                    continue
                
                # It's part of the message
                message_lines.append(line)
            
            # Join message lines
            message = ' '.join(message_lines).strip()
            
            # Final cleanup
            if not message or len(message) < 1:
                return
            
            # Remove sender from beginning of message if present
            if sender and message.startswith(sender):
                message = message[len(sender):].strip()
                if message.startswith(':') or message.startswith('-'):
                    message = message[1:].strip()
            
            # Don't save if message is empty or just the sender name
            if not message or message.lower() == sender.lower():
                return
            
            # Normalize for deduplication
            sender_norm = sender.strip().lower()
            message_norm = ' '.join(message.strip().lower().split())  # Normalize whitespace
            
            # Create dedup key (ignore time for better detection of duplicates)
            dedup_key = f"{sender_norm}|{message_norm}"
            
            # Check if this is a duplicate
            if dedup_key in self.seen_messages:
                # Duplicate - skip silently
                return
            
            # New message - save it
            self.seen_messages.add(dedup_key)
            
            chat_entry = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'event': 'Chat Message',
                'sender': sender.strip(),
                'message': message.strip(),
                'time': time_str or datetime.now().strftime('%I:%M %p')
            }
            
            self.chat_log.append(chat_entry)
            print(f'💬 NEW: {sender}: {message}')
            
            # Save immediately to file
            self._save_chat_messages_immediate()
            
        except Exception as e:
            print(f'⚠️  Message parsing error: {str(e)}')

    def _save_chat_messages_immediate(self):
        """Save chat messages immediately to file (real-time) in JSON array format"""
        try:
            if not self.chat_messages_path:
                return
            
            chat_messages_path = self.chat_messages_path
            
            # Read existing JSON structure
            import json
            try:
                with open(chat_messages_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                # If file doesn't exist or is corrupt, create new structure
                from datetime import datetime
                data = {
                    "meeting_id": self.current_meeting_id if hasattr(self, 'current_meeting_id') else "meet-UNKN",
                    "date": datetime.now().strftime('%d-%m-%Y'),
                    "chat_log": []
                }
            
            # Process new messages from chat_log
            for entry in self.chat_log:
                if entry.get('event') == 'Chat Message':
                    sender = entry.get('sender', '').strip()
                    message = entry.get('message', '').strip()
                    
                    # Filter out noise senders
                    if sender.lower() in ["pin", "keep", "messages", "chat"]:
                        continue
                    
                    # Filter out noise messages
                    noise_phrases = ["keep Pin message", "Pin message", "keep", "message", "send"]
                    should_skip = False
                    for phrase in noise_phrases:
                        if message.lower() == phrase.lower():
                            should_skip = True
                            break
                        if message.endswith(phrase):
                            message = message[:-len(phrase)].strip()
                    
                    if should_skip:
                        continue
                        
                    # Skip if message is only the sender name
                    if message.lower() == sender.lower():
                        continue
                    
                    # Skip empty messages
                    if not message or len(message) < 2:
                        continue
                    
                    # Deduplication - check both sender and message
                    dedup_key = f"{sender}|{message}"
                    if dedup_key in self.saved_chat_entries:
                        continue
                    self.saved_chat_entries.add(dedup_key)

                    # Format: Sender Name : Message Text (clean format without extra quotes)
                    safe_message = ' '.join(message.split())
                    formatted_message = f'{sender} : {safe_message}'
                    
                    # Add to chat_log array if not already present
                    if formatted_message not in data['chat_log']:
                        data['chat_log'].append(formatted_message)
            
            # Write back to file
            with open(chat_messages_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        except Exception as e:
            # Log error but don't crash
            print(f'⚠️  Error saving chat messages: {str(e)}')
