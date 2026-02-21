# Discord Bot Startup Script for PowerShell
# Run as: powershell -ExecutionPolicy Bypass -File start_bot.ps1

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "Discord Music Bot - Startup" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[+] Found Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[!] Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "[*] Install from: https://www.python.org/" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if requirements are installed
Write-Host "[*] Checking dependencies..." -ForegroundColor Yellow

$depsInstalled = python -c "import discord; import yt_dlp" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Dependencies not installed" -ForegroundColor Red
    Write-Host "[*] Installing dependencies..." -ForegroundColor Yellow
    pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[!] Failed to install dependencies" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Check if FFmpeg is installed
try {
    $ffmpegVersion = ffmpeg -version 2>&1 | Select-Object -First 1
    Write-Host "[+] Found FFmpeg" -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "[!] WARNING: FFmpeg is not installed or not in PATH" -ForegroundColor Yellow
    Write-Host "[*] The bot requires FFmpeg for audio processing" -ForegroundColor Yellow
    Write-Host "[*] Download from: https://ffmpeg.org/download.html" -ForegroundColor Yellow
    Write-Host "[*] Or install via Chocolatey: choco install ffmpeg" -ForegroundColor Yellow
    Write-Host ""
}

# Check if bot token is set
if (-not $env:DISCORD_BOT_TOKEN) {
    Write-Host ""
    Write-Host "[!] ERROR: DISCORD_BOT_TOKEN environment variable is not set" -ForegroundColor Red
    Write-Host "[*] Methods to set token:" -ForegroundColor Yellow
    Write-Host "   1. Create .env file and copy .env.example contents" -ForegroundColor Cyan
    Write-Host "   2. Set environment variable:" -ForegroundColor Cyan
    Write-Host '      $env:DISCORD_BOT_TOKEN = "your_token_here"' -ForegroundColor Cyan
    Write-Host "   3. Or edit bot.py and replace YOUR_BOT_TOKEN_HERE" -ForegroundColor Cyan
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "[+] All checks passed!" -ForegroundColor Green
Write-Host "[*] Starting Discord Music Bot..." -ForegroundColor Yellow
Write-Host ""

python bot.py

Read-Host "Press Enter to exit"
