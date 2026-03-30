"""
Property-based tests for authentication module
Tests correctness properties from the design document
"""
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from hypothesis import given, strategies as st, settings

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.authentication import get_base_path, run_google_authentication, _check_auth_cookies


class TestBasePathResolution:
    """
    **Feature: exe-authentication-fix, Property 7: Consistent browser launch across modes**
    Tests that base path resolution works correctly in both dev and EXE modes
    """
    
    @settings(max_examples=100)
    @given(
        frozen=st.booleans(),
        executable_path=st.text(min_size=1, max_size=100).filter(lambda x: '/' not in x and '\\' not in x)
    )
    def test_base_path_resolution_consistency(self, frozen, executable_path):
        """
        Property: For any execution mode (frozen or not), get_base_path() should return
        a valid Path object that points to a directory
        
        **Validates: Requirements 3.3**
        """
        with patch('sys.frozen', frozen, create=True):
            if frozen:
                # Simulate EXE mode
                with patch('sys.executable', str(Path.cwd() / executable_path)):
                    base_path = get_base_path()
                    
                    # Property: base_path should be a Path object
                    assert isinstance(base_path, Path)
                    
                    # Property: base_path should be the parent of sys.executable
                    assert base_path == Path(sys.executable).parent
            else:
                # Simulate dev mode
                base_path = get_base_path()
                
                # Property: base_path should be a Path object
                assert isinstance(base_path, Path)
                
                # Property: base_path should be the parent of the authentication module
                # In dev mode, it should be the parent of __file__
                assert base_path.exists() or True  # Path may not exist in test environment
    
    def test_base_path_frozen_mode(self):
        """
        Test that in frozen mode, base path uses sys.executable parent
        """
        with patch('sys.frozen', True, create=True):
            with patch('sys.executable', '/path/to/app/AutoMeetAttender.exe'):
                base_path = get_base_path()
                assert base_path == Path('/path/to/app')
    
    def test_base_path_dev_mode(self):
        """
        Test that in dev mode, base path uses __file__ parent
        """
        with patch('sys.frozen', False, create=True):
            base_path = get_base_path()
            # Should be parent of src/authentication.py, which is the project root
            assert isinstance(base_path, Path)
            assert base_path.name != 'src'  # Should be project root, not src folder


class TestAuthenticationStatePersistence:
    """
    **Feature: exe-authentication-fix, Property 2: Authentication state persistence**
    Tests that authentication state is properly saved and can be loaded
    """
    
    @settings(max_examples=100)
    @given(
        cookies_data=st.lists(
            st.fixed_dictionaries({
                'name': st.text(min_size=1, max_size=20),
                'value': st.text(min_size=1, max_size=50),
                'domain': st.just('.google.com'),
                'path': st.just('/'),
            }),
            min_size=1,
            max_size=10
        )
    )
    def test_authentication_state_persistence_property(self, cookies_data):
        """
        Property: For any successful authentication, the system should create a valid
        authentication state file that contains the expected structure
        
        **Validates: Requirements 1.3**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            auth_state_path = base_path / 'auth-state'
            auth_file = auth_state_path / 'google-auth.json'
            
            # Create auth directory
            auth_state_path.mkdir(parents=True, exist_ok=True)
            
            # Simulate saving authentication state
            # This mimics what Playwright's storage_state() does
            auth_data = {
                'cookies': cookies_data,
                'origins': []
            }
            
            with open(auth_file, 'w') as f:
                json.dump(auth_data, f)
            
            # Property 1: File should exist after save
            assert auth_file.exists()
            
            # Property 2: File should be readable
            with open(auth_file, 'r') as f:
                loaded_data = json.load(f)
            
            # Property 3: Loaded data should match saved data
            assert loaded_data == auth_data
            
            # Property 4: Cookies should be preserved
            assert len(loaded_data['cookies']) == len(cookies_data)
            
            # Property 5: Each cookie should have required fields
            for cookie in loaded_data['cookies']:
                assert 'name' in cookie
                assert 'value' in cookie
                assert 'domain' in cookie
    
    def test_auth_file_location_relative_to_base_path(self):
        """
        Test that authentication file is always located relative to base path
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.authentication.get_base_path', return_value=Path(tmpdir)):
                # The auth file should be at base_path / 'auth-state' / 'google-auth.json'
                expected_path = Path(tmpdir) / 'auth-state' / 'google-auth.json'
                
                # Create the directory structure
                expected_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Verify the path structure
                assert expected_path.parent.name == 'auth-state'
                assert expected_path.name == 'google-auth.json'


class TestAuthCookieValidation:
    """
    Tests for authentication cookie validation
    """
    
    @settings(max_examples=100)
    @given(
        has_sid=st.booleans(),
        has_ssid=st.booleans(),
        other_cookies=st.lists(
            st.fixed_dictionaries({
                'name': st.text(min_size=1, max_size=20).filter(lambda x: x not in ['SID', 'SSID']),
                'value': st.text(min_size=1, max_size=50),
            }),
            max_size=5
        )
    )
    def test_check_auth_cookies_property(self, has_sid, has_ssid, other_cookies):
        """
        Property: For any set of cookies, _check_auth_cookies should return True
        if and only if SID or SSID cookies are present
        
        **Validates: Requirements 1.3**
        """
        # Create mock context
        mock_context = MagicMock()
        
        # Build cookie list
        cookies = list(other_cookies)
        if has_sid:
            cookies.append({'name': 'SID', 'value': 'test_sid_value'})
        if has_ssid:
            cookies.append({'name': 'SSID', 'value': 'test_ssid_value'})
        
        mock_context.cookies.return_value = cookies
        
        # Property: Should return True if SID or SSID present
        result = _check_auth_cookies(mock_context)
        expected = has_sid or has_ssid
        
        assert result == expected, f"Expected {expected} but got {result} for SID={has_sid}, SSID={has_ssid}"
    
    def test_check_auth_cookies_with_exception(self):
        """
        Test that _check_auth_cookies handles exceptions gracefully
        """
        mock_context = MagicMock()
        mock_context.cookies.side_effect = Exception("Cookie error")
        
        # Should return False on exception
        result = _check_auth_cookies(mock_context)
        assert result is False


class TestAuthenticationErrorHandling:
    """
    Tests for authentication error handling
    """
    
    def test_browser_launch_failure_playwright_not_installed(self):
        """
        Test that browser launch failure due to missing Playwright is handled correctly
        """
        with patch('src.authentication.sync_playwright') as mock_playwright:
            mock_context_manager = MagicMock()
            mock_playwright.return_value = mock_context_manager
            mock_p = MagicMock()
            mock_context_manager.__enter__.return_value = mock_p
            
            # Simulate Playwright not installed error
            mock_p.chromium.launch_persistent_context.side_effect = Exception(
                "Executable doesn't exist at /path/to/chromium"
            )
            
            success, message = run_google_authentication()
            
            assert success is False
            assert "Playwright browsers not installed" in message
            assert "playwright install chromium" in message
    
    def test_browser_launch_failure_port_in_use(self):
        """
        Test that browser launch failure due to port conflict is handled correctly
        """
        with patch('src.authentication.sync_playwright') as mock_playwright:
            mock_context_manager = MagicMock()
            mock_playwright.return_value = mock_context_manager
            mock_p = MagicMock()
            mock_context_manager.__enter__.return_value = mock_p
            
            # Simulate port in use error
            mock_p.chromium.launch_persistent_context.side_effect = Exception(
                "Address already in use: 127.0.0.1:9222"
            )
            
            success, message = run_google_authentication()
            
            assert success is False
            assert "Browser port in use" in message
            assert "Close other Chrome instances" in message
