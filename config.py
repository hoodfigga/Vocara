import os
import json
import logging

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.expanduser("~/.config/vocara")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DICT_FILE = os.path.join(CONFIG_DIR, "dictionary.json")

DEFAULT_CONFIG = {
    "activation_mode": "hold", # 'hold' or 'toggle'
    "shortcut": ["mouse.Button.x2"], # Default to Mouse 5
    "start_on_boot": False,
    "auto_enter": False,
    "start_invisible": False
}

def ensure_config_dir():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

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
        return []
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
