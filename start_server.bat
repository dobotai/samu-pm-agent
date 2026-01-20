@echo off
echo Starting PM Agent Server...
echo.
echo Server will run at: http://localhost:8000
echo Press Ctrl+C to stop the server.
echo.
cd /d "%~dp0"
python execution/api_server.py
pause
