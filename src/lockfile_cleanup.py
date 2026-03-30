"""
Browser Profile Lockfile Cleanup Utility

Handles detection and removal of stale lockfiles in the Playwright browser profile directory.
This prevents "browser already running" errors when previous sessions didn't close cleanly.
"""
import os
import time
from pathlib import Path
from typing import Optional


def is_process_running(pid: int) -> bool:
    """
    Check if a process with the given PID is currently running.
    
    Args:
        pid (int): Process ID to check
        
    Returns:
        bool: True if process is running, False otherwise
    """
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        # Fallback if psutil not available - assume process might be running
        # This is safer than assuming it's not running
        print("⚠️  psutil not installed - cannot verify process status")
        return False


def get_lockfile_pid(lockfile_path: Path) -> Optional[int]:
    """
    Try to extract the PID from a Chrome lockfile.
    Chrome lockfiles typically contain the process ID.
    
    Args:
        lockfile_path (Path): Path to the lockfile
        
    Returns:
        Optional[int]: Process ID if found, None otherwise
    """
    try:
        # Chrome lockfiles are usually symbolic links or contain the PID
        if lockfile_path.is_symlink():
            target = os.readlink(str(lockfile_path))
            # Try to extract PID from symlink target
            if target.isdigit():
                return int(target)
        
        # Try reading the file content
        if lockfile_path.is_file():
            try:
                content = lockfile_path.read_text(errors='ignore').strip()
                if content.isdigit():
                    return int(content)
            except:
                pass
        
        return None
    except Exception as e:
        print(f"⚠️  Could not read lockfile PID: {str(e)}")
        return None


def cleanup_browser_lockfile(profile_dir: Path, force: bool = False) -> bool:
    """
    Clean up stale browser profile lockfile if it exists.
    
    Args:
        profile_dir (Path): Path to the browser profile directory
        force (bool): If True, remove lockfile even if process appears to be running
        
    Returns:
        bool: True if cleanup was performed or not needed, False if cleanup failed
    """
    lockfile_path = profile_dir / "lockfile"
    
    # Check if lockfile exists
    if not lockfile_path.exists():
        # No lockfile - all good
        return True
    
    print(f"🔒 Detected lockfile: {lockfile_path}")
    
    # Try to determine if the lock is stale
    pid = get_lockfile_pid(lockfile_path)
    is_stale = True
    
    if pid:
        print(f"🔍 Lockfile references PID: {pid}")
        is_running = is_process_running(pid)
        
        if is_running:
            print(f"⚠️  Process {pid} is still running")
            is_stale = False
        else:
            print(f"✓ Process {pid} is not running - lockfile is stale")
            is_stale = True
    else:
        print("🔍 Could not determine lockfile owner - assuming stale")
        is_stale = True
    
    # Remove lockfile if stale or force is specified
    if is_stale or force:
        try:
            # Try to remove the lockfile
            lockfile_path.unlink(missing_ok=True)
            print(f"✅ Removed lockfile: {lockfile_path}")
            
            # Wait a moment to ensure filesystem syncs
            time.sleep(0.5)
            
            # Verify removal
            if lockfile_path.exists():
                print(f"⚠️  Lockfile still exists after removal attempt")
                return False
            
            return True
        except Exception as e:
            print(f"❌ Failed to remove lockfile: {str(e)}")
            return False
    else:
        print(f"⚠️  Lockfile appears to be in use - skipping cleanup")
        print(f"💡 If you're sure no browser is running, manually delete: {lockfile_path}")
        return False


def cleanup_with_retry(profile_dir: Path, max_retries: int = 3, retry_delay: float = 1.0) -> bool:
    """
    Attempt to clean up lockfile with retries.
    
    Args:
        profile_dir (Path): Path to the browser profile directory
        max_retries (int): Maximum number of retry attempts
        retry_delay (float): Seconds to wait between retries
        
    Returns:
        bool: True if cleanup succeeded, False otherwise
    """
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"🔄 Lockfile cleanup retry {attempt}/{max_retries}")
            time.sleep(retry_delay)
        
        success = cleanup_browser_lockfile(profile_dir, force=False)
        
        if success:
            return True
    
    # Final attempt with force
    print("🔨 Final cleanup attempt with force=True")
    return cleanup_browser_lockfile(profile_dir, force=True)


if __name__ == "__main__":
    # Test/manual cleanup mode
    import sys
    
    if len(sys.argv) > 1:
        profile_path = Path(sys.argv[1])
    else:
        # Default to playwright_profile in parent directory
        profile_path = Path(__file__).parent.parent / "playwright_profile"
    
    print(f"🧹 Browser Profile Lockfile Cleanup")
    print(f"📁 Profile directory: {profile_path}")
    print()
    
    if not profile_path.exists():
        print(f"❌ Profile directory does not exist: {profile_path}")
        sys.exit(1)
    
    success = cleanup_with_retry(profile_path)
    
    if success:
        print()
        print("✅ Lockfile cleanup completed successfully")
        sys.exit(0)
    else:
        print()
        print("❌ Lockfile cleanup failed")
        sys.exit(1)
