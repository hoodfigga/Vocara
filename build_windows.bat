@echo off
setlocal enabledelayedexpansion

echo ==========================================
echo    Vocara Windows Release Build Script    
echo ==========================================

:: Activate virtual environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo [+] Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
)

:: Ensure PyInstaller is installed
pip install pyinstaller

echo [+] Building standalone Windows executable...
pyinstaller --noconfirm --onedir --windowed --name Vocara --icon=assets/icon.ico --add-data "assets;assets" main.py

if exist "dist\Vocara\Vocara.exe" (
    echo.
    echo ==========================================
    echo [SUCCESS] Build complete!
    echo Standalone executable located at:
    echo dist\Vocara\Vocara.exe
    echo ==========================================
) else (
    echo.
    echo [-] Build failed. Please inspect the output above.
)
pause
