import json
import logging
import os
import platform
import sys
import tempfile

logger = logging.getLogger(__name__)

if platform.system() == "Windows":
    CONFIG_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "Vocara")
else:
    CONFIG_DIR = os.path.expanduser("~/.config/vocara")

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DICT_FILE = os.path.join(CONFIG_DIR, "dictionary.json")

ACTIVATION_MODES = ("hold", "toggle", "always_on")
MODEL_SIZES = ("tiny", "base", "small", "medium", "turbo", "large-v3")
ENGINES = ("faster-whisper", "openai-whisper")
COMPUTE_TYPES = ("auto", "int8", "float16", "float32")
DEVICES = ("auto", "cuda", "cpu")

DEFAULT_CONFIG = {
    "activation_mode": "hold",  # 'hold', 'toggle', or 'always_on'
    "shortcut": ["mouse.Button.x2"],  # Default to Mouse 5
    "start_on_boot": False,
    "auto_enter": False,
    "start_invisible": False,
    "play_beeps": True,
    # --- Whisper Engine & Model Options ---
    "engine": "faster-whisper",  # 'faster-whisper' or 'openai-whisper'
    "model_size": "base",  # 'tiny', 'base', 'small', 'medium', 'turbo', 'large-v3'
    "compute_type": "auto",  # 'auto', 'int8', 'float16', 'float32'
    "device": "auto",  # 'auto', 'cuda', 'cpu'
    "vad_filter": True,  # Filter out non-speech silence automatically
    "language": None,  # None (auto-detect) or 'en', etc.
    "input_device": None,  # Audio device index or None for default
    # --- Always-On (VAD) tuning ---
    "vad_energy_threshold": 0.015,  # RMS level above which speech is assumed
    "vad_silence_timeout": 2.0,  # Seconds of silence that end a phrase
    "hud_position": None,  # [x, y] or None
    "hud_theme": "dark",  # 'dark'
}

# Config keys whose value must belong to a fixed set; anything else is reset.
_ENUM_KEYS = {
    "activation_mode": ACTIVATION_MODES,
    "model_size": MODEL_SIZES,
    "engine": ENGINES,
    "compute_type": COMPUTE_TYPES,
    "device": DEVICES,
}


def ensure_config_dir():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)


def _write_json_atomic(path, payload):
    """Writes JSON via a temp file + rename so an interrupted write cannot
    truncate or corrupt an existing config."""
    ensure_config_dir()
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".vocara-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def validate_config(data):
    """Merges user data over the defaults, dropping values of the wrong type or
    outside the allowed set. Never raises: a bad config degrades to defaults."""
    config = DEFAULT_CONFIG.copy()
    if not isinstance(data, dict):
        return config

    for key, value in data.items():
        if key not in DEFAULT_CONFIG:
            continue  # ignore unknown/stale keys
        default = DEFAULT_CONFIG[key]
        if key in _ENUM_KEYS:
            if value in _ENUM_KEYS[key]:
                config[key] = value
            continue
        if isinstance(default, bool):
            if isinstance(value, bool):
                config[key] = value
            continue
        if key == "shortcut":
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                config[key] = value
            continue
        if key in ("vad_energy_threshold", "vad_silence_timeout"):
            if isinstance(value, (int, float)) and value > 0:
                config[key] = float(value)
            continue
        if key == "hud_position":
            if isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) for v in value):
                config[key] = value
            continue
        config[key] = value

    return config


def load_config():
    ensure_config_dir()
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return validate_config(json.load(f))
    except Exception as e:
        logger.error(f"Failed to load config ({e}); falling back to defaults.")
        return DEFAULT_CONFIG.copy()


def save_config(config):
    try:
        _write_json_atomic(CONFIG_FILE, config)
    except Exception as e:
        logger.error(f"Failed to save config: {e}")


def load_dictionary():
    ensure_config_dir()

    if not os.path.exists(DICT_FILE):
        default_vocab = ["Vocara", "Whisper", "Wayland", "PipeWire", "PySide6", "GitHub"]
        save_dictionary(default_vocab)
        return default_vocab
    try:
        with open(DICT_FILE, encoding="utf-8") as f:
            words = json.load(f)
        if not isinstance(words, list):
            raise ValueError("dictionary.json must contain a JSON list")
        return [str(w) for w in words]
    except Exception as e:
        logger.error(f"Failed to load dictionary: {e}")
        return []


def save_dictionary(words):
    try:
        _write_json_atomic(DICT_FILE, words)
    except Exception as e:
        logger.error(f"Failed to save dictionary: {e}")


def get_audio_input_devices():
    """Returns a list of input devices available on the system."""
    devices = []
    try:
        import sounddevice as sd

        default_in = (
            sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else sd.default.device
        )
        all_devs = sd.query_devices()
        for idx, dev in enumerate(all_devs):
            if dev.get("max_input_channels", 0) > 0:
                devices.append(
                    {
                        "index": idx,
                        "name": dev.get("name", f"Device {idx}"),
                        "channels": dev.get("max_input_channels", 1),
                        "is_default": (idx == default_in),
                        "samplerate": int(dev.get("default_samplerate", 16000)),
                    }
                )
    except Exception as e:
        logger.warning(f"Error querying audio devices: {e}")
    return devices


def _launch_command():
    """Returns the command used to relaunch Vocara, as a list of argv parts.

    Handles both source checkouts (python + main.py) and frozen PyInstaller
    bundles, where sys.executable IS the application and main.py does not exist.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable]
    main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
    return [sys.executable, main_py]


def _quote(part):
    return f'"{part}"' if " " in part else part


def update_autostart(enable: bool):
    """Enable or disable startup on boot."""
    try:
        if platform.system() == "Linux":
            autostart_dir = os.path.expanduser("~/.config/autostart")
            desktop_file = os.path.join(autostart_dir, "vocara.desktop")
            if enable:
                os.makedirs(autostart_dir, exist_ok=True)
                exec_line = " ".join(_quote(p) for p in _launch_command())
                content = f"""[Desktop Entry]
Type=Application
Name=Vocara
Comment=Privacy-First Local AI Dictation
Exec={exec_line}
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
"""
                with open(desktop_file, "w", encoding="utf-8") as f:
                    f.write(content)
            else:
                if os.path.exists(desktop_file):
                    os.remove(desktop_file)
        elif platform.system() == "Windows":
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
            )
            app_name = "Vocara"
            try:
                if enable:
                    cmd = " ".join(f'"{p}"' for p in _launch_command())
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, app_name)
                    except FileNotFoundError:
                        pass
            finally:
                winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"Failed to update autostart: {e}")
