#!/bin/bash
# Builds the Linux standalone bundle with the same flags CI uses.
# Usage: ./build_linux.sh   (outputs dist/Vocara and dist/Vocara-Linux-x86_64.tar.gz)
set -e
cd "$(dirname "$0")"

PY=".venv/bin/python"
if [ ! -x "$PY" ] && [ -x "venv/bin/python" ]; then
    # install.sh creates venv/; use it when .venv/ is absent.
    PY="venv/bin/python"
fi
if [ ! -x "$PY" ]; then
    echo "[-] No virtual environment found. Run ./install.sh, or:"
    echo "    uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt pyinstaller"
    exit 1
fi

if ! "$PY" -c "import PyInstaller" 2>/dev/null; then
    echo "[+] Installing PyInstaller..."
    # .venv has no pip module; use uv (falling back to pip if present).
    if command -v uv &> /dev/null; then
        uv pip install --python "$PY" pyinstaller
    else
        "$PY" -m pip install pyinstaller || {
            echo "[-] Cannot install PyInstaller (no pip in .venv and no uv)."
            exit 1
        }
    fi
fi

echo "[+] Building standalone executable (via Vocara.spec)..."
"$PY" -m PyInstaller --noconfirm Vocara.spec

echo "[+] Packing tarball..."
cd dist
tar -czf Vocara-Linux-x86_64.tar.gz Vocara
cd ..

echo "[+] Done: dist/Vocara-Linux-x86_64.tar.gz"
