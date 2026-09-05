import os
import sys
import json
import logging
import platform

logger = logging.getLogger(__name__)

if platform.system() == "Windows":
    CONFIG_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "Vocara")
else:
    CONFIG_DIR = os.path.expanduser("~/.config/vocara")

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DICT_FILE = os.path.join(CONFIG_DIR, "dictionary.json")

DEFAULT_CONFIG = {
    "activation_mode": "hold",  # 'hold', 'toggle', or 'always_on'
    "shortcut": ["mouse.Button.x2"],  # Default to Mouse 5
    "start_on_boot": False,
    "auto_enter": False,
    "start_invisible": False,
    "play_beeps": True,
    # --- Whisper Engine & Model Options ---
    "engine": "faster-whisper",  # 'faster-whisper' or 'openai-whisper'
    "model_size": "base",        # 'tiny', 'base', 'small', 'medium', 'turbo', 'large-v3'
    "compute_type": "auto",      # 'auto', 'int8', 'float16', 'float32'
    "device": "auto",            # 'auto', 'cuda', 'cpu'
    "vad_filter": True,          # Filter out non-speech silence automatically
    "language": None,            # None (auto-detect) or 'en', etc.
    "input_device": None,        # Audio device index or None for default
    "hud_position": None,        # [x, y] or None
    "hud_theme": "dark"          # 'dark'
}

def ensure_config_dir():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)

def load_config():
    ensure_config_dir()
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            config = DEFAULT_CONFIG.copy()
            config.update(data)
            return config
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return DEFAULT_CONFIG.copy()

def save_config(config):
    ensure_config_dir()
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save config: {e}")

def load_dictionary():
    ensure_config_dir()
    
    old_dict = "dictionary.json"
    if os.path.exists(old_dict) and not os.path.exists(DICT_FILE):
        try:
            os.rename(old_dict, DICT_FILE)
        except Exception:
            pass

    if not os.path.exists(DICT_FILE):
        default_vocab = ["Vocara", "Whisper", "Wayland", "PipeWire", "PySide6", "GitHub"]
        save_dictionary(default_vocab)
        return default_vocab
    try:
        with open(DICT_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load dictionary: {e}")
        return []

def save_dictionary(words):
    ensure_config_dir()
    try:
        with open(DICT_FILE, 'w') as f:
            json.dump(words, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save dictionary: {e}")

def get_audio_input_devices():
    """Returns a list of input devices available on the system."""
    devices = []
    try:
        import sounddevice as sd
        default_in = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else sd.default.device
        all_devs = sd.query_devices()
        for idx, dev in enumerate(all_devs):
            if dev.get('max_input_channels', 0) > 0:
                devices.append({
                    "index": idx,
                    "name": dev.get('name', f"Device {idx}"),
                    "channels": dev.get('max_input_channels', 1),
                    "is_default": (idx == default_in),
                    "samplerate": int(dev.get('default_samplerate', 16000))
                })
    except Exception as e:
        logger.warning(f"Error querying audio devices: {e}")
    return devices

def update_autostart(enable: bool):
    """Enable or disable startup on boot."""
    try:
        if platform.system() == "Linux":
            autostart_dir = os.path.expanduser("~/.config/autostart")
            desktop_file = os.path.join(autostart_dir, "vocara.desktop")
            if enable:
                os.makedirs(autostart_dir, exist_ok=True)
                main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
                python_bin = sys.executable
                content = f"""[Desktop Entry]
Type=Application
Name=Vocara
Comment=Privacy-First Local AI Dictation
Exec={python_bin} {main_py}
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
"""
                with open(desktop_file, 'w') as f:
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
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
            )
            app_name = "Vocara"
            if enable:
                python_bin = sys.executable
                main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
                cmd = f'"{python_bin}" "{main_py}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"Failed to update autostart: {e}")
