============================================================
  Aarya StockSense Pro — Setup Instructions
============================================================

STEP 1 — Install Python (skip if already installed)
  - Go to: https://python.org/downloads
  - Download Python 3.10, 3.11, or 3.12
  - IMPORTANT: During install, check "Add Python to PATH"

STEP 2 — Run setup
  - Double-click setup.bat
  - Wait 2-3 minutes for packages to install
  - Shortcuts will be created automatically

STEP 3 — Add your API keys (first time only)
  Open the app → Settings tab → Alert Settings:
  - Email address(es) to receive alerts
  - Gmail App Password for the sending account
    (Google Account → Security → 2-Step Verification → App passwords)
  - Alpha Vantage key: https://alphavantage.co/support/#api-key (free)
  - Gemini key: https://aistudio.google.com/apikey (free)

STEP 4 — Open the app anytime
  - Press Windows key, type "Aarya", press Enter
  - OR double-click "Aarya StockSense Pro" on your Desktop
  - OR double-click run.bat

OPTIONAL — Automatic background emails
  - Right-click schedule_aarya.bat → Run as Administrator
  - The tool will then email you daily picks + alerts automatically
  - No need to open the app

============================================================
  FILES IN THIS FOLDER
============================================================
  run.bat              - Launch the app (use this daily)
  setup.bat            - First-time setup on any machine
  monitor.py           - Run manually for instant email check
  schedule_aarya.bat   - Set up automatic daily emails
  unschedule_aarya.bat - Turn off automatic emails
  aarya_config.json    - Your API keys and email settings
  monitor.log          - Log of background monitoring runs

============================================================
  NOTE: aarya_config.json contains your API keys and email
  credentials. Do not share this file publicly.
  The person you share with should add their own keys.
============================================================
