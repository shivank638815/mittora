"""
Setup script for Google Authentication
Thin wrapper around authentication module for command-line usage
"""
import sys
from src.authentication import run_google_authentication


if __name__ == '__main__':
    print('🔧 Starting Google Authentication Setup...\n')
    
    success, message = run_google_authentication(
        progress_callback=lambda msg: print(msg)
    )
    
    if success:
        print('\n✅ Authentication setup completed successfully!')
        sys.exit(0)
    else:
        print(f'\n❌ Authentication setup failed: {message}')
        sys.exit(1)
