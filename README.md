# Vocara: Privacy-First Local Voice Dictation

<p align="center">
  <img src="assets/logo_cropped.png" alt="Vocara Logo" width="320">
</p>

Vocara is a privacy-first local dictation application powered by modern Whisper models. Everything runs entirely on your local hardware — no audio or text ever leaves your machine.

## Features

- **Fast Whisper Engine**: Powered by `faster-whisper` (CTranslate2) with int8/float16 quantization, with automatic fallback support for `openai-whisper`.
- **Model Support**: `tiny`, `base`, `small`, `medium`, `turbo` (large-v3-turbo), and `large-v3`.
- **Desktop HUD**: A dark graphite floating HUD bar with real-time VU audio metering, status indicators, and quick controls.
- **Dynamic Vocabulary & Jargon**: Add custom technical terminology, acronyms, and unique names that are dynamically injected into Whisper's prompt for better recognition accuracy.
- **Voice Commands & Smart Editing**: Spoken commands including:
  - `scratch that` (deletes last word)
  - `strike line` (erases current line)
  - `undo last` (Ctrl+Z)
  - `select all` / `save document` (Ctrl+A / Ctrl+S)
  - `vocara clear` (clears recent text)
  - `vocara pause` / `vocara resume`
  - `open quote` / `close quote` and `quote ... unquote`
  - `cancel that` (discards the current utterance before it is typed)
- **Always-On VAD Mode**: Automatically detects speech, transcribes, and types it for you without touching your keyboard.
- **Push-to-Talk & Toggle**: Configurable hotkeys (e.g. Mouse 5, Ctrl+Space).
- **Fullscreen Auto-Suspension**: Automatically pauses always-on listening while gaming or watching movies in fullscreen.
- **Ghost Mode**: Minimize to tray anytime and toggle visibility with `Ctrl+Alt+V`.

## Prerequisites

- **Python 3.10+**
- **Linux**: `libportaudio2` (audio) and an X11 session (global hotkeys and the tray icon are not supported on pure Wayland); `xprop` is used for fullscreen detection.
- **Hardware**: Runs on CPU (fast with int8 quantized models) and on NVIDIA CUDA GPUs. AMD GPUs work only through the optional openai-whisper fallback engine with a ROCm build of PyTorch — the default faster-whisper engine is CPU/CUDA only.

## Installation

### Linux
```bash
git clone https://github.com/hoodfigga/Vocara.git
cd Vocara
chmod +x install.sh
./install.sh
```
Then launch Vocara from your application menu, or run:
```bash
./venv/bin/python main.py
```

To skip the optional PyTorch download (large, only needed for the openai-whisper fallback engine):
```bash
VOCARA_SKIP_TORCH=1 ./install.sh
```

### Windows
```cmd
git clone https://github.com/hoodfigga/Vocara.git
cd Vocara
install.bat
```
*Or manually install dependencies: `pip install -r requirements.txt`*

Launch Vocara:
```cmd
venv\Scripts\python main.py
```

## Building Standalone Binaries

Prebuilt binaries are attached to each [GitHub Release](https://github.com/hoodfigga/Vocara/releases) (built by CI on every version tag).

To build locally:
- **Windows**: `build_windows.bat`
- **Linux**: `pyinstaller --noconfirm --onedir --windowed --name Vocara --icon=assets/icon.png --add-data "assets:assets" main.py`

## Privacy & Security

Vocara does not transmit audio or text data to external servers or cloud services. All processing, voice activity detection, and speech-to-text inference execute 100% locally on your machine.

## Troubleshooting

- **No audio input / recording fails**: On Linux, install `libportaudio2` and check your input device in Settings → Audio Device.
- **Hotkeys don't trigger**: Global hotkeys require X11 on Linux. On Wayland, pynput cannot capture global input; switch to an X11 session or use the HUD's action button.
- **Fullscreen suspension not working**: Install `xprop` (usually in `x11-utils`).
- **Model download is slow on first run**: Whisper models are downloaded once from Hugging Face into `~/.local/share/Vocara/Models` (Linux) or `%LOCALAPPDATA%\Vocara\Models` (Windows) and cached afterwards.

## License

GPL-3.0 — see [LICENSE](LICENSE).
