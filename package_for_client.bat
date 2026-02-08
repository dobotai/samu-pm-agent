@echo off
SETLOCAL EnableDelayedExpansion

:: ============================================
:: Client Package Builder
:: Creates a clean package ready to send to client
:: ============================================

echo.
echo ========================================
echo   Client Package Builder
echo ========================================
echo.

:: Set package name
set PACKAGE_NAME=pm-agent-client-package
set TIMESTAMP=%DATE:~-4%%DATE:~4,2%%DATE:~7,2%
set OUTPUT_DIR=..\%PACKAGE_NAME%

echo This will create a clean package in:
echo %OUTPUT_DIR%
echo.
echo WARNING: Your .env file with API keys will NOT be included.
echo The client will need to create their own .env file.
echo.
set /p confirm="Continue? (y/n) "
if /i not "!confirm!"=="y" exit /b

:: Create output directory
echo.
echo [1/6] Creating package directory...
if exist "%OUTPUT_DIR%" (
    echo Cleaning existing package directory...
    rmdir /s /q "%OUTPUT_DIR%"
)
mkdir "%OUTPUT_DIR%"
echo [OK] Directory created

:: Copy core files
echo.
echo [2/6] Copying core files...
xcopy /E /I /Q /EXCLUDE:package_exclude.txt . "%OUTPUT_DIR%" >nul 2>&1
if %errorLevel% neq 0 (
    echo [WARNING] Some files might not have copied
)
echo [OK] Core files copied

:: Remove sensitive files
echo.
echo [3/6] Removing sensitive files...
del /F /Q "%OUTPUT_DIR%\.env" 2>nul
del /F /Q "%OUTPUT_DIR%\.env.backup" 2>nul
del /F /Q "%OUTPUT_DIR%\credentials.json" 2>nul
del /F /Q "%OUTPUT_DIR%\token.json" 2>nul
rmdir /S /Q "%OUTPUT_DIR%\.tmp" 2>nul
rmdir /S /Q "%OUTPUT_DIR%\.git" 2>nul
rmdir /S /Q "%OUTPUT_DIR%\venv" 2>nul
rmdir /S /Q "%OUTPUT_DIR%\__pycache__" 2>nul

:: Remove test files
del /F /Q "%OUTPUT_DIR%\test_*.py" 2>nul
del /F /Q "%OUTPUT_DIR%\package_for_client.bat" 2>nul
del /F /Q "%OUTPUT_DIR%\package_for_client.sh" 2>nul
echo [OK] Sensitive files removed

:: Create .tmp directory structure
echo.
echo [4/6] Creating empty directories...
mkdir "%OUTPUT_DIR%\.tmp" 2>nul
mkdir "%OUTPUT_DIR%\.tmp\logs" 2>nul
mkdir "%OUTPUT_DIR%\.tmp\sessions" 2>nul
echo [OK] Directories created

:: Create placeholder .env
echo.
echo [5/6] Creating configuration template...
(
    echo # PM Agent Configuration
    echo # Run configure.bat to set up your API keys
    echo.
    echo ANTHROPIC_API_KEY=
    echo CLIENT_API_KEY=
    echo CLIENT_NAME=youtube_agency
    echo.
    echo SLACK_BOT_TOKEN=
    echo SLACK_USER_TOKEN=
    echo.
    echo AIRTABLE_API_KEY=
    echo AIRTABLE_BASE_ID=
    echo.
    echo GOOGLE_CREDENTIALS_JSON=
) > "%OUTPUT_DIR%\.env"
echo [OK] Template created

:: Create verification file
echo.
echo [6/6] Creating package manifest...
(
    echo PM Agent Client Package
    echo Generated: %DATE% %TIME%
    echo.
    echo INSTALLATION INSTRUCTIONS:
    echo 1. Read CLIENT_PACKAGE_README.md
    echo 2. Follow CLIENT_INSTALL.md for detailed setup
    echo 3. Run install.bat ^(Windows^) or install.sh ^(Mac/Linux^)
    echo 4. Run configure.bat/sh to enter API keys
    echo 5. Start the agent with start_agent.bat/sh
    echo.
    echo SUPPORT: Contact your agent provider for assistance
) > "%OUTPUT_DIR%\START_HERE.txt"
echo [OK] Manifest created

:: Summary
echo.
echo.
echo ========================================
echo   Package Created Successfully!
echo ========================================
echo.
echo Location: %OUTPUT_DIR%
echo.
echo Next steps:
echo 1. Review %OUTPUT_DIR% to verify everything looks correct
echo 2. Check DEPLOYMENT_CHECKLIST.md for final verification
echo 3. Create ZIP file or send via Git
echo.
echo To create a ZIP file:
echo    Right-click the folder ^> Send to ^> Compressed folder
echo.
echo The package is ready to send to your client!
echo.
pause
