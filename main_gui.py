"""
AutoMeet Attender - GUI Entry Point
This version launches the GUI by default when the EXE is double-clicked
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# Force GUI mode by default
if len(sys.argv) == 1:
    sys.argv.append('gui')

# Import and run main
from main import main

if __name__ == '__main__':
    main()
