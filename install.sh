#!/bin/bash
set -e

echo "======================================"
echo "    Vocara AI Dictation Installer     "
echo "======================================"

# Check requirements
if ! command -v python3 &> /dev/null; then
    echo "[-] Python3 could not be found. Please install Python3."
    exit 1
fi

if ! dpkg -s python3-venv &> /dev/null && ! command -v virtualenv &> /dev/null; then
    echo "[-] Python3 venv is missing. Please install it (e.g. sudo apt install python3-venv)."
    exit 1
fi

if ! dpkg -s libxcb-cursor0 &> /dev/null; then
    echo "[!] Missing Qt6 dependency 'libxcb-cursor0'. You may need to run: sudo apt install libxcb-cursor0"
fi

# Detect GPU
GPU_VENDOR="UNKNOWN"
if lspci | grep -i vga | grep -i amd > /dev/null; then
    GPU_VENDOR="AMD"
elif lspci | grep -i vga | grep -i nvidia > /dev/null; then
    GPU_VENDOR="NVIDIA"
fi

echo "[+] Detected GPU Vendor: $GPU_VENDOR"

# Setup virtual environment
echo "[+] Setting up virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install base dependencies
echo "[+] Installing core dependencies (Whisper, PySide6, Audio libs)..."
pip install --upgrade pip
pip install pynput sounddevice "numpy<2" openai-whisper PySide6

# Install PyTorch mapped to hardware
echo "[+] Installing hardware-accelerated PyTorch..."
if [ "$GPU_VENDOR" == "AMD" ]; then
    echo "    -> Using AMD ROCm architecture."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm5.6
elif [ "$GPU_VENDOR" == "NVIDIA" ]; then
    echo "    -> Using NVIDIA CUDA architecture."
    pip install torch torchvision torchaudio
else
    echo "    -> Using CPU architecture."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
fi

# Create Desktop Shortcut
echo "[+] Creating Application Menu shortcut..."
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
CURRENT_DIR=$(pwd)
DESKTOP_FILE="$DESKTOP_DIR/vocara.desktop"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Vocara
Comment=Voice-to-Text powered by Whisper
Exec=$CURRENT_DIR/venv/bin/python3 $CURRENT_DIR/main.py
Terminal=false
Categories=Utility;
EOF

chmod +x "$DESKTOP_FILE"
echo "[+] Shortcut created at $DESKTOP_FILE"

echo "======================================"
echo "[+] Installation Complete!"
echo "    You can now launch 'Vocara AI Dictation' from your application menu."
echo "======================================"
