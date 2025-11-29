# Elite Dangerous Mining Scanner v8 - PySide6 Edition

Modern Python application for monitoring Elite Dangerous journal files and detecting valuable materials during mining.

## Quick Start (Windows)

### First Time Setup

1. **Download all files** to a folder (e.g., `C:\ED_Mining_Scanner\`)

2. **Double-click `start.bat`**
   - Automatically creates Python virtual environment
   - Checks Python version (requires 3.10+)
   - Installs all dependencies
   - Starts background log reader
   - Launches UI

That's it! The batch file handles everything automatically.

### Subsequent Launches

Just run `start.bat` - it will:
- Skip venv creation (already exists)
- Update dependencies if needed
- Start/check log reader service
- Launch UI

### Stopping the Application

**Option 1: Using batch file**
