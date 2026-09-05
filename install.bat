@echo off
setlocal enabledelayedexpansion

echo ======================================
echo     Vocara AI Dictation Installer     
echo ======================================

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [-] Python is not installed or not in PATH. Please install Python 3.10+ from python.org.
    pause
    exit /b 1
)

:: Create Virtual Environment if not present
if not exist "venv" (
    echo [+] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [-] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate Virtual Environment
call venv\Scripts\activate

:: Upgrade pip and install requirements
echo [+] Installing core dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo ======================================
echo [+] Installation Complete!
echo     To start Vocara, run:
echo     venv\Scripts\python.exe main.py
echo ======================================
pause
