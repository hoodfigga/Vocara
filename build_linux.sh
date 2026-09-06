#!/bin/bash
# Builds the Linux standalone bundle with the same flags CI uses.
# Usage: ./build_linux.sh   (outputs dist/Vocara and dist/Vocara-Linux-x86_64.tar.gz)
set -e
cd "$(dirname "$0")"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "[-] .venv not found. Run ./install.sh first."
    exit 1
fi

echo "[+] Installing PyInstaller..."
$PY -m pip install --upgrade pip
$PY -m pip install pyinstaller 2>/dev/null || $PY -m pip install pyinstaller

echo "[+] Building standalone executable..."
$PY -m PyInstaller --noconfirm --onedir --windowed --name Vocara \
    --icon=assets/icon.png --add-data "assets:assets" main.py

echo "[+] Packing tarball..."
cd dist
tar -czf Vocara-Linux-x86_64.tar.gz Vocara
cd ..

echo "[+] Done: dist/Vocara-Linux-x86_64.tar.gz"
