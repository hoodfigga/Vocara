#!/bin/bash
set -e

echo "======================================"
echo "    Vocara AI Dictation Installer     "
echo "======================================"

# Check requirements
if ! command -v python3 &> /dev/null; then
    echo "[-] Python3 could not be found. Please install Python 3.10+."
    exit 1
fi

# Hint at system dependencies (names differ per distribution)
if command -v apt &> /dev/null; then
    MISSING=""
    [ ! -e /usr/lib/x86_64-linux-gnu/libportaudio.so.2 ] && [ ! -e /usr/lib/x86_64-linux-gnu/libportaudio.so ] && MISSING="libportaudio2 $MISSING"
    [ ! -d /usr/lib/x86_64-linux-gnu/qt6/plugins/platforms 2>/dev/null ] && true
    dpkg -s libxcb-cursor0 &> /dev/null || MISSING="libxcb-cursor0 $MISSING"
    if [ -n "$MISSING" ]; then
        echo "[!] Missing system packages: $MISSING"
        echo "    Fix with: sudo apt install $MISSING"
        echo "    (The app may fail to launch or record without them.)"
    fi
fi

# Detect GPU (only used for the optional openai-whisper fallback engine;
# faster-whisper runs on CPU/CUDA regardless)
GPU_VENDOR="CPU"
if command -v lspci &> /dev/null; then
    if lspci | grep -i vga | grep -i nvidia > /dev/null; then
        GPU_VENDOR="NVIDIA"
    elif lspci | grep -i vga | grep -i amd > /dev/null; then
        GPU_VENDOR="AMD"
    fi
fi
echo "[+] Detected GPU Vendor: $GPU_VENDOR"

# Setup virtual environment
echo "[+] Setting up virtual environment..."
if [ ! -d "venv" ]; then
    if ! python3 -m venv venv 2> /tmp/vocara_venv_err.log; then
        echo "[-] Failed to create the virtual environment. Common fixes:"
        echo "    Debian/Ubuntu: sudo apt install python3-venv"
        echo "    Fedora:        sudo dnf install python3-pip"
        cat /tmp/vocara_venv_err.log
        exit 1
    fi
fi
source venv/bin/activate

# Install core dependencies (faster-whisper engine, Qt HUD, audio I/O, hotkeys)
echo "[+] Installing core dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Optional: PyTorch + openai-whisper fallback engine (large download).
# Skip with: VOCARA_SKIP_TORCH=1 ./install.sh
if [ "${VOCARA_SKIP_TORCH:-0}" = "1" ]; then
    echo "[+] Skipping optional PyTorch (VOCARA_SKIP_TORCH=1)."
else
    echo "[+] Installing optional PyTorch (openai-whisper fallback engine)..."
    if [ "$GPU_VENDOR" == "AMD" ]; then
        pip install torch --index-url https://download.pytorch.org/whl/rocm6.2 \
            || echo "[!] ROCm PyTorch install failed; continuing without the fallback engine."
    elif [ "$GPU_VENDOR" == "NVIDIA" ]; then
        pip install torch \
            || echo "[!] PyTorch install failed; continuing without the fallback engine."
    else
        pip install torch --index-url https://download.pytorch.org/whl/cpu \
            || echo "[!] PyTorch install failed; continuing without the fallback engine."
    fi
    pip install openai-whisper \
        || echo "[!] openai-whisper not installed; faster-whisper remains the only engine."
fi

# Create Application Menu shortcut
echo "[+] Creating application menu shortcut..."
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
CURRENT_DIR=$(pwd)
DESKTOP_FILE="$DESKTOP_DIR/vocara.desktop"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Vocara
Comment=Privacy-First Local Voice-to-Text powered by Whisper
Exec="$CURRENT_DIR/venv/bin/python3" "$CURRENT_DIR/main.py"
Terminal=false
Categories=Utility;
EOF

chmod +x "$DESKTOP_FILE"
update-desktop-database "$DESKTOP_DIR" 2> /dev/null || true
echo "[+] Shortcut created at $DESKTOP_FILE"

echo "======================================"
echo "[+] Installation Complete!"
echo "    Launch 'Vocara' from your application menu,"
echo "    or run: ./venv/bin/python main.py"
echo "======================================"
