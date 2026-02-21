@echo off
REM Discord Bot Startup Script for Windows

echo.
echo ===============================================
echo Discord Music Bot - Startup
echo ===============================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python is not installed or not in PATH
    echo Please install Python from https://www.python.org/
    pause
    exit /b 1
)

REM Check if requirements are installed
echo [*] Checking dependencies...
pip show discord.py >nul 2>&1
if errorlevel 1 (
    echo [!] Dependencies not installed
    echo [*] Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [!] Failed to install dependencies
        pause
        exit /b 1
    )
)

REM Check if FFmpeg is installed
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [!] WARNING: FFmpeg is not installed or not in PATH
    echo [*] The bot requires FFmpeg for audio processing
    echo [*] Download from https://ffmpeg.org/download.html
    echo [*] Or install via: choco install ffmpeg
    echo.
    pause
)

REM Check if bot token is set
if "%DISCORD_BOT_TOKEN%"=="" (
    echo.
    echo [!] ERROR: DISCORD_BOT_TOKEN environment variable is not set
    echo [*] Methods to set token:
    echo    1. Create .env file and copy .env.example contents
    echo    2. Set environment variable:
    echo       set DISCORD_BOT_TOKEN=your_token_here
    echo    3. Or edit bot.py and replace YOUR_BOT_TOKEN_HERE
    echo.
    pause
    exit /b 1
)

echo.
echo [+] All checks passed!
echo [*] Starting Discord Music Bot...
echo.

python bot.py

pause
