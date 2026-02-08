@echo off
SETLOCAL EnableDelayedExpansion

:: ============================================
:: PM Agent Installer for Windows
:: ============================================

echo.
echo ========================================
echo   PM Agent Installation Wizard
echo ========================================
echo.

:: Check for admin rights (optional but recommended)
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [WARNING] Not running as administrator.
    echo Some features might not work. Continue anyway? (y/n)
    set /p continue=
    if /i not "!continue!"=="y" exit /b
)

:: Step 1: Check if Python is installed
echo [1/5] Checking for Python...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo [ERROR] Python not found!
    echo.
    echo Please install Python 3.10 or newer:
    echo 1. Go to https://www.python.org/downloads/
    echo 2. Download Python 3.10 or newer
    echo 3. During installation, CHECK "Add Python to PATH"
    echo 4. Run this installer again
    echo.
    pause
    exit /b 1
) else (
    python --version
    echo [OK] Python found
)

:: Step 2: Create virtual environment
echo.
echo [2/5] Creating isolated Python environment...
if exist venv (
    echo [WARNING] Virtual environment already exists. Recreating...
    rmdir /s /q venv
)
python -m venv venv
if %errorLevel% neq 0 (
    echo [ERROR] Failed to create virtual environment
    pause
    exit /b 1
)
echo [OK] Environment created

:: Step 3: Activate virtual environment and upgrade pip
echo.
echo [3/5] Activating environment and upgrading installer...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip setuptools wheel >nul 2>&1
echo [OK] Environment ready

:: Step 4: Install dependencies
echo.
echo [4/5] Installing required packages (this may take 2-3 minutes)...
pip install -r requirements.txt
if %errorLevel% neq 0 (
    echo [ERROR] Failed to install dependencies
    echo Check your internet connection and try again
    pause
    exit /b 1
)
echo [OK] All packages installed

:: Step 5: Create necessary directories
echo.
echo [5/5] Setting up folders...
if not exist .tmp mkdir .tmp
if not exist .tmp\logs mkdir .tmp\logs
if not exist .tmp\sessions mkdir .tmp\sessions
if not exist config\clients mkdir config\clients
echo [OK] Folders created

:: Create .env template if it doesn't exist
if not exist .env (
    echo.
    echo Creating configuration template...
    (
        echo # PM Agent Configuration
        echo # Fill in your API keys using configure.bat
        echo.
        echo ANTHROPIC_API_KEY=
        echo CLIENT_API_KEY=pm_client_key_!RANDOM!!RANDOM!
        echo CLIENT_NAME=youtube_agency
        echo.
        echo SLACK_BOT_TOKEN=
        echo SLACK_USER_TOKEN=
        echo.
        echo AIRTABLE_API_KEY=
        echo AIRTABLE_BASE_ID=
        echo.
        echo GOOGLE_CREDENTIALS_JSON=
    ) > .env
    echo [OK] Configuration template created
)

:: Create desktop shortcut
echo.
echo Creating desktop shortcut...
set DESKTOP=%USERPROFILE%\Desktop
set SCRIPT_DIR=%CD%

:: Create start script
(
    echo @echo off
    echo cd /d "%SCRIPT_DIR%"
    echo call venv\Scripts\activate.bat
    echo echo.
    echo echo ========================================
    echo echo   PM Agent Server Starting...
    echo echo ========================================
    echo echo.
    echo python execution/api_server.py
    echo pause
) > "start_agent.bat"

:: Create chat script
(
    echo @echo off
    echo cd /d "%SCRIPT_DIR%"
    echo call venv\Scripts\activate.bat
    echo python -c "from execution.orchestrator import interactive_chat; interactive_chat()"
) > "agent_chat.bat"

:: Try to create desktop shortcut (may fail without admin rights)
if exist "%DESKTOP%" (
    copy start_agent.bat "%DESKTOP%\Start PM Agent.bat" >nul 2>&1
    if %errorLevel% equ 0 (
        echo [OK] Desktop shortcut created
    ) else (
        echo [WARNING] Could not create desktop shortcut
        echo You can run start_agent.bat from this folder instead
    )
)

:: Installation complete
echo.
echo.
echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo Next steps:
echo.
echo 1. Get your API keys (see CLIENT_INSTALL.md for instructions):
echo    - Anthropic API key
echo    - Slack bot token
echo    - Airtable API key and base ID
echo.
echo 2. Run: configure.bat
echo    This will help you enter your API keys
echo.
echo 3. Start the agent:
echo    - Double-click "Start PM Agent.bat" on your desktop
echo    - OR run: start_agent.bat
echo.
echo 4. Open your browser to: http://localhost:8000
echo.
echo.
echo For detailed instructions, see CLIENT_INSTALL.md
echo.
pause
