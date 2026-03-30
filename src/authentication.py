"""
Authentication module for Google Meet
Handles browser-based authentication with progress callback support
"""
import sys
import time
import webbrowser
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️  Playwright not available, using system browser fallback")


def get_base_path():
    """
    Get the base path for the application (works in both dev and EXE mode)
    
    Returns:
        Path: Base directory path
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled EXE
        return Path(sys.executable).parent
    else:
        # Running as script
        return Path(__file__).parent.parent


def check_playwright_browsers():
    """
    Check if Playwright browsers are installed
    
    Returns:
        bool: True if browsers are available, False otherwise
    """
    try:
        if not PLAYWRIGHT_AVAILABLE:
            return False
        
        # Try to get browser executable path
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # This will fail if browsers aren't installed
            executable_path = p.chromium.executable_path
            return executable_path is not None
    except Exception:
        return False


def run_google_authentication(progress_callback=None):
    """
    Run Google authentication flow with browser
    
    Args:
        progress_callback: Optional callback function(message: str) for progress updates
        
    Returns:
        tuple: (success: bool, message: str)
    """
    def emit_progress(message):
        """Helper to emit progress messages"""
        if progress_callback:
            progress_callback(message)
        else:
            print(message)
    
    # Check if Playwright is available
    if not PLAYWRIGHT_AVAILABLE:
        error_msg = (
            'Playwright is not installed.\n\n'
            'Please install it by running:\n'
            'pip install playwright\n'
            'playwright install chromium'
        )
        emit_progress(f'❌ {error_msg}')
        return False, error_msg
    
    # Try Playwright method
    try:
        return run_google_authentication_playwright(progress_callback)
    except Exception as e:
        error_details = str(e)
        emit_progress(f'❌ Authentication failed: {error_details}')
        
        # Provide helpful error messages
        if "executable doesn't exist" in error_details.lower() or "executable doesn't exist" in error_details.lower():
            error_msg = (
                'Playwright browsers are not installed.\n\n'
                'Please run this command in terminal:\n'
                'playwright install chromium\n\n'
                'Then try authentication again.'
            )
        else:
            error_msg = f'Authentication error: {error_details}'
        
        return False, error_msg


def run_google_authentication_playwright(progress_callback=None):
    """
    Run Google authentication flow with Playwright browser
    
    Args:
        progress_callback: Optional callback function(message: str) for progress updates
        
    Returns:
        tuple: (success: bool, message: str)
    """
    def emit_progress(message):
        """Helper to emit progress messages"""
        if progress_callback:
            progress_callback(message)
        else:
            print(message)
    
    try:
        emit_progress('🔧 Setting up Google Authentication...')
        emit_progress('⚠️  IMPORTANT: Google blocks automated login attempts.')
        emit_progress('📝 You will need to LOGIN MANUALLY in the browser that opens.')
        
        # Get base path and setup directories
        base_path = get_base_path()
        auth_state_path = base_path / 'auth-state'
        auth_file = auth_state_path / 'google-auth.json'
        profile_dir = base_path / 'playwright_profile'
        
        # Clear old authentication to force fresh login
        emit_progress('🧹 Clearing old authentication data...')
        if auth_file.exists():
            auth_file.unlink()
            emit_progress('   Removed old auth file')
        
        if profile_dir.exists():
            import shutil
            try:
                shutil.rmtree(profile_dir)
                emit_progress('   Removed old browser profile')
            except Exception as e:
                emit_progress(f'   ⚠️  Could not remove profile: {e}')
        
        # Create auth-state directory if it doesn't exist
        auth_state_path.mkdir(parents=True, exist_ok=True)
        
        with sync_playwright() as p:
            # Try to find system Chrome first (user-friendly option)
            import os
            user_home = Path.home()
            
            # Common Chrome installation paths
            chrome_paths = [
                Path(os.environ.get('PROGRAMFILES', 'C:\\Program Files')) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
                Path(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)')) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
                Path(os.environ.get('LOCALAPPDATA', '')) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
            ]
            
            browser_exe = None
            browser_name = None
            
            # First, try to find Chrome (best for authentication)
            for chrome_path in chrome_paths:
                if chrome_path.exists():
                    browser_exe = chrome_path
                    browser_name = "Chrome"
                    emit_progress(f'✅ Found Chrome at: {browser_exe}')
                    emit_progress('   Using your regular Chrome browser for easy login!')
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
                            emit_progress(f'✅ Found Chromium at: {browser_exe}')
                            break
            
            # If neither found, show error
            if not browser_exe:
                error_msg = (
                    'No browser found!\n\n'
                    'Please install one of:\n'
                    '1. Google Chrome (recommended) - https://www.google.com/chrome/\n'
                    '2. Playwright Chromium - Run: playwright install chromium'
                )
                emit_progress(f'❌ {error_msg}')
                return False, error_msg
            
            # Use persistent context with playwright_profile directory
            user_data_dir = str(base_path / 'playwright_profile')
            
            emit_progress('🌐 Launching browser...')
            emit_progress(f'📁 Profile directory: {user_data_dir}')
            
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=False,
                    executable_path=str(browser_exe),  # Use found browser (Chrome or Chromium)
                    args=[
                        '--start-maximized',
                        '--disable-blink-features=AutomationControlled',
                        '--use-fake-ui-for-media-stream',  # Auto-accept media permissions
                    ],
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    no_viewport=True,  # Use native window size
                    timeout=60000,  # 60 second timeout
                )
                emit_progress('✅ Browser launched successfully!')
            except Exception as e:
                error_msg = str(e)
                emit_progress(f'❌ Browser launch error: {error_msg}')
                
                if "executable doesn't exist" in error_msg.lower():
                    return False, f"Chromium not found at: {chromium_exe}\n\nRun: playwright install chromium"
                elif "address already in use" in error_msg.lower():
                    return False, "Browser port in use. Close other Chrome instances and retry."
                elif "timeout" in error_msg.lower():
                    return False, "Browser launch timed out. Try closing other Chrome windows and retry."
                else:
                    return False, f"Browser launch failed: {error_msg}"
            
            # Get page from persistent context
            if len(context.pages) > 0:
                page = context.pages[0]
            else:
                page = context.new_page()
            
            try:
                emit_progress('🌐 Opening Google Sign In page...')
                emit_progress('=' * 60)
                emit_progress('  👉 PLEASE LOGIN MANUALLY IN THE BROWSER WINDOW')
                emit_progress('  1. Enter your email and password')
                emit_progress('  2. Complete any 2FA verification')
                emit_progress('  3. IMPORTANT: Wait for redirect to Google Account page')
                emit_progress('  4. DO NOT close the browser - script will auto-detect')
                emit_progress('  5. Browser will close automatically when done')
                emit_progress('=' * 60)
                
                page.goto('https://accounts.google.com/signin', wait_until='domcontentloaded')
                
                emit_progress('⏳ Waiting for you to complete login...')
                emit_progress('   (This may take up to 5 minutes)')
                
                # Wait for successful login
                login_detected = _wait_for_login(page, context, emit_progress)
                
                if not login_detected:
                    # Even if timeout, try to check authentication
                    emit_progress('⚠️  Timeout waiting for redirect. Checking authentication...')
                    if not _check_auth_cookies(context):
                        raise Exception('Login not completed. Please try again and wait for Google Account page.')
                    
                    emit_progress('✅ Authentication cookies found!')
                
                emit_progress('✅ Login detected!')
                emit_progress('💾 Saving authentication state...')
                
                # Save authentication state
                context.storage_state(path=str(auth_file))
                emit_progress(f'💾 Authentication state saved to: {auth_file}')
                
                # Wait longer to ensure persistent profile saves completely
                emit_progress('⏳ Ensuring profile saves completely (45 seconds)...')
                time.sleep(45)
                
                emit_progress('=' * 60)
                emit_progress('  ✨ Setup complete! You can now run the application')
                emit_progress('=' * 60)
                
                return True, 'Authentication completed successfully'
            
            except Exception as error:
                error_msg = f'Setup failed: {str(error)}'
                emit_progress(f'❌ {error_msg}')
                emit_progress('💡 Troubleshooting:')
                emit_progress('- Make sure you completed the login in the browser')
                emit_progress('- Try running authentication again')
                emit_progress('- Check your internet connection')
                emit_progress('- Verify your Google account credentials are correct')
                return False, error_msg
            
            finally:
                try:
                    emit_progress('🔒 Closing browser...')
                    context.close()
                except Exception as error:
                    emit_progress(f'⚠️  Error closing browser: {str(error)}')
    
    except Exception as e:
        error_msg = f'Authentication failed: {str(e)}'
        emit_progress(f'❌ {error_msg}')
        return False, error_msg


def _wait_for_login(page, context, emit_progress, timeout=300):
    """
    Wait for successful login detection
    
    Args:
        page: Playwright page object
        context: Playwright context object
        emit_progress: Progress callback function
        timeout: Timeout in seconds (default 5 minutes)
        
    Returns:
        bool: True if login detected, False if timeout
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            url = page.url
            
            # Check if redirected to account page
            if any(pattern in url for pattern in [
                'myaccount.google.com',
                'accounts.google.com/ManageAccount',
                'myaccount.google.com/intro'
            ]):
                return True
            
            # Check for auth cookies
            if _check_auth_cookies(context) and 'google.com' in url:
                time.sleep(2)  # Wait a bit more to ensure login is complete
                return True
            
            time.sleep(1)
        
        except Exception:
            time.sleep(1)
            continue
    
    return False


def _check_auth_cookies(context):
    """
    Check if authentication cookies are present
    
    Args:
        context: Playwright context object
        
    Returns:
        bool: True if auth cookies found, False otherwise
    """
    try:
        cookies = context.cookies()
        return any(
            'SID' in c['name'] or 'SSID' in c['name'] 
            for c in cookies
        )
    except Exception:
        return False
