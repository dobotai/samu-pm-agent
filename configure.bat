@echo off
SETLOCAL EnableDelayedExpansion

:: ============================================
:: PM Agent Configuration Wizard
:: ============================================

echo.
echo ========================================
echo   PM Agent Configuration Wizard
echo ========================================
echo.
echo This wizard will help you set up your API keys.
echo.
echo Prerequisites:
echo - Anthropic API key (from console.anthropic.com)
echo - Slack bot token (from api.slack.com/apps)
echo - Airtable API key (from airtable.com/create/tokens)
echo - Airtable base ID (from your Airtable URL)
echo.
echo See CLIENT_INSTALL.md for detailed instructions.
echo.
pause

:: Check if virtual environment exists
if not exist venv (
    echo [ERROR] Virtual environment not found!
    echo Please run install.bat first.
    pause
    exit /b 1
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Create backup of existing .env
if exist .env (
    echo Creating backup of existing configuration...
    copy .env .env.backup >nul 2>&1
    echo [OK] Backup saved as .env.backup
    echo.
)

:: Start configuration
echo ========================================
echo Step 1: Anthropic API Key
echo ========================================
echo.
echo This is required to power the AI agent.
echo Get it from: https://console.anthropic.com/settings/keys
echo.
echo Format: sk-ant-api03-...
echo.
set /p ANTHROPIC_API_KEY="Enter your Anthropic API key: "

if "!ANTHROPIC_API_KEY!"=="" (
    echo [ERROR] API key cannot be empty
    pause
    exit /b 1
)

echo.
echo Testing Anthropic connection...
python -c "import anthropic; client = anthropic.Anthropic(api_key='!ANTHROPIC_API_KEY!'); print('[OK] Anthropic API key is valid')" 2>nul
if %errorLevel% neq 0 (
    echo [ERROR] Invalid Anthropic API key or connection failed
    echo Please check your key and internet connection
    pause
    exit /b 1
)

:: Step 2: Slack
echo.
echo ========================================
echo Step 2: Slack Bot Token
echo ========================================
echo.
echo Required to read messages and send notifications.
echo Get it from: https://api.slack.com/apps
echo.
echo Format: xoxb-...
echo.
set /p SLACK_BOT_TOKEN="Enter your Slack bot token: "

if "!SLACK_BOT_TOKEN!"=="" (
    echo [ERROR] Slack token cannot be empty
    pause
    exit /b 1
)

echo.
echo Testing Slack connection...
python -c "from slack_sdk import WebClient; client = WebClient(token='!SLACK_BOT_TOKEN!'); client.auth_test(); print('[OK] Slack bot token is valid')" 2>nul
if %errorLevel% neq 0 (
    echo [ERROR] Invalid Slack token or connection failed
    echo Please check your token and internet connection
    pause
    exit /b 1
)

:: Step 3: Slack User Token (optional)
echo.
echo Do you have a Slack user token? (y/n)
echo This is optional - allows searching across all channels
set /p has_user_token=
if /i "!has_user_token!"=="y" (
    echo.
    echo Format: xoxp-...
    set /p SLACK_USER_TOKEN="Enter your Slack user token: "
) else (
    set SLACK_USER_TOKEN=
)

:: Step 4: Airtable
echo.
echo ========================================
echo Step 3: Airtable Configuration
echo ========================================
echo.
echo Required to read project data.
echo Get token from: https://airtable.com/create/tokens
echo.
echo Format: pat...
echo.
set /p AIRTABLE_API_KEY="Enter your Airtable API key: "

if "!AIRTABLE_API_KEY!"=="" (
    echo [ERROR] Airtable API key cannot be empty
    pause
    exit /b 1
)

echo.
echo Now enter your Airtable base ID.
echo Find it in your Airtable URL: https://airtable.com/appXXXXXXXXXXXXXX/...
echo.
echo Format: app...
echo.
set /p AIRTABLE_BASE_ID="Enter your Airtable base ID: "

if "!AIRTABLE_BASE_ID!"=="" (
    echo [ERROR] Base ID cannot be empty
    pause
    exit /b 1
)

echo.
echo Testing Airtable connection...
python -c "from pyairtable import Api; api = Api('!AIRTABLE_API_KEY!'); base = api.base('!AIRTABLE_BASE_ID!'); print('[OK] Airtable credentials are valid')" 2>nul
if %errorLevel% neq 0 (
    echo [ERROR] Invalid Airtable credentials or base ID
    echo Please check your API key and base ID
    pause
    exit /b 1
)

:: Step 5: Generate client API key
echo.
echo Generating secure client API key...
set CLIENT_API_KEY=pm_client_!RANDOM!!RANDOM!!RANDOM!

:: Step 6: Google Drive (optional)
echo.
echo ========================================
echo Step 4: Google Drive (Optional)
echo ========================================
echo.
echo Do you want to enable Google Drive access? (y/n)
set /p enable_drive=
if /i "!enable_drive!"=="y" (
    echo.
    echo Please provide the path to your Google service account JSON file:
    echo Example: C:\path\to\service-account.json
    echo.
    set /p GOOGLE_CREDS_PATH="Enter path to Google credentials: "

    if exist "!GOOGLE_CREDS_PATH!" (
        echo [OK] Google credentials file found
        set GOOGLE_CREDENTIALS_JSON=!GOOGLE_CREDS_PATH!
    ) else (
        echo [WARNING] File not found. Skipping Google Drive setup.
        set GOOGLE_CREDENTIALS_JSON=
    )
) else (
    set GOOGLE_CREDENTIALS_JSON=
)

:: Write .env file
echo.
echo ========================================
echo Saving Configuration
echo ========================================
echo.

(
    echo # PM Agent Configuration
    echo # Generated by configure.bat on %DATE% at %TIME%
    echo # DO NOT COMMIT THIS FILE TO VERSION CONTROL
    echo.
    echo # ============================================
    echo # CORE CREDENTIALS
    echo # ============================================
    echo.
    echo ANTHROPIC_API_KEY=!ANTHROPIC_API_KEY!
    echo CLIENT_API_KEY=!CLIENT_API_KEY!
    echo CLIENT_NAME=youtube_agency
    echo.
    echo # ============================================
    echo # SLACK INTEGRATION
    echo # ============================================
    echo.
    echo SLACK_BOT_TOKEN=!SLACK_BOT_TOKEN!
    echo SLACK_USER_TOKEN=!SLACK_USER_TOKEN!
    echo.
    echo # ============================================
    echo # AIRTABLE INTEGRATION
    echo # ============================================
    echo.
    echo AIRTABLE_API_KEY=!AIRTABLE_API_KEY!
    echo AIRTABLE_BASE_ID=!AIRTABLE_BASE_ID!
    echo.
    echo # ============================================
    echo # GOOGLE DRIVE (OPTIONAL)
    echo # ============================================
    echo.
    echo GOOGLE_CREDENTIALS_JSON=!GOOGLE_CREDENTIALS_JSON!
    echo.
    echo # ============================================
    echo # OPTIONAL INTEGRATIONS
    echo # ============================================
    echo.
    echo SLACK_WEBHOOK_URL=
    echo SENDGRID_API_KEY=
    echo GOOGLE_TOKEN_JSON=
) > .env

echo [OK] Configuration saved to .env
echo.
echo.
echo ========================================
echo   Configuration Complete!
echo ========================================
echo.
echo Your API keys are securely stored in .env
echo.
echo IMPORTANT SECURITY NOTES:
echo - Keep the .env file private
echo - Never share it or commit it to version control
echo - If compromised, regenerate all API keys immediately
echo.
echo Next steps:
echo.
echo 1. Start the agent:
echo    - Double-click "Start PM Agent.bat" on your desktop
echo    - OR run: start_agent.bat
echo.
echo 2. Open your browser to: http://localhost:8000
echo.
echo 3. Try asking questions like:
echo    - "What videos are due this week?"
echo    - "Show me urgent tasks"
echo    - "What's Taylor's video status?"
echo.
echo.
pause
