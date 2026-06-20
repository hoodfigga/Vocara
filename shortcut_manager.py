from pynput import keyboard, mouse
import threading
import logging

logger = logging.getLogger(__name__)

class ShortcutManager:
    def __init__(self, target_shortcut, callback, is_toggle_mode=False):
        """
        target_shortcut: list of string representations of keys/buttons
        callback: function(bool is_active)
        """
        self.target_shortcut = set(target_shortcut)
        self.callback = callback
        self.is_toggle_mode = is_toggle_mode
        
        self.current_keys = set()
        self.is_active = False
        self.lock = threading.Lock()
        
        self.kb_listener = keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release)
        self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
        
    def start(self):
        if not hasattr(self.kb_listener, 'is_alive') or not self.kb_listener.is_alive():
            self.kb_listener = keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release)
            self.kb_listener.start()
        if not hasattr(self.mouse_listener, 'is_alive') or not self.mouse_listener.is_alive():
            self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
            self.mouse_listener.start()
        
    def stop(self):
        if hasattr(self.kb_listener, 'stop'):
            self.kb_listener.stop()
        if hasattr(self.mouse_listener, 'stop'):
            self.mouse_listener.stop()

    def update_config(self, target_shortcut, is_toggle_mode):
        with self.lock:
            self.target_shortcut = set(target_shortcut)
            self.is_toggle_mode = is_toggle_mode
            self.current_keys.clear()
            self.is_active = False

    def _normalize_key(self, key):
        try:
            return f"keyboard.{key.name}"
        except AttributeError:
            try:
                return f"keyboard.char.{key.char.lower()}"
            except AttributeError:
                return str(key)

    def _normalize_mouse(self, button):
        return f"mouse.{str(button)}"

    def _check_activation(self):
        match = self.target_shortcut.issubset(self.current_keys) and len(self.target_shortcut) > 0
        
        if self.is_toggle_mode:
            if match and not self.is_active:
                self.is_active = True
                self.callback(True)
            elif not match and self.is_active:
                self.is_active = False
        else:
            if match and not self.is_active:
                self.is_active = True
                self.callback(True)
            elif not match and self.is_active:
                self.is_active = False
                self.callback(False)

    def on_key_press(self, key):
        k = self._normalize_key(key)
        logger.info(f"Key pressed: {k}")
        with self.lock:
            self.current_keys.add(k)
            self._check_activation()

    def on_key_release(self, key):
        k = self._normalize_key(key)
        with self.lock:
            if k in self.current_keys:
                self.current_keys.remove(k)
            self._check_activation()

    def on_mouse_click(self, x, y, button, pressed):
        b = self._normalize_mouse(button)
        logger.info(f"Mouse event: {b}, pressed: {pressed}")
        with self.lock:
            if pressed:
                self.current_keys.add(b)
            else:
                if b in self.current_keys:
                    self.current_keys.remove(b)
            self._check_activation()

class RebindListener:
    """Listens for the next keystroke or mouse click to bind a new shortcut."""
    def __init__(self, callback):
        self.callback = callback
        self.captured = set()
        self.done = False
        
        self.kb_listener = keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release)
        self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
        
    def start(self):
        self.kb_listener.start()
        self.mouse_listener.start()
        
    def stop(self):
        self.kb_listener.stop()
        self.mouse_listener.stop()

    def _normalize_key(self, key):
        try:
            return f"keyboard.{key.name}"
        except AttributeError:
            try:
                return f"keyboard.char.{key.char.lower()}"
            except AttributeError:
                return str(key)
                
    def _normalize_mouse(self, button):
        return f"mouse.{str(button)}"

    def _finish(self):
        if not self.done and len(self.captured) > 0:
            self.done = True
            self.stop()
            self.callback(list(self.captured))

    def on_key_press(self, key):
        if self.done: return
        k = self._normalize_key(key)
        logger.info(f"Rebind key pressed: {k}")
        self.captured.add(k)

    def on_key_release(self, key):
        if self.done: return
        self._finish()

    def on_mouse_click(self, x, y, button, pressed):
        if self.done: return
        b = self._normalize_mouse(button)
        logger.info(f"Rebind mouse event: {b}, pressed: {pressed}")
        if pressed:
            if str(button) == "Button.left":
                pass
            else:
                self.captured.add(b)
        else:
            if len(self.captured) > 0:
                self._finish()

def get_friendly_name(shortcut_list):
    names = []
    for s in shortcut_list:
        if s.startswith("keyboard.char."):
            names.append(s.split(".")[-1].upper())
        elif s.startswith("keyboard."):
            names.append(s.split(".")[-1].title())
        elif s.startswith("mouse.Button."):
            btn = s.split(".")[-1]
            if btn == 'x1': names.append('Mouse 4')
            elif btn == 'x2': names.append('Mouse 5')
            elif btn == 'left': names.append('Left Click')
            elif btn == 'right': names.append('Right Click')
            elif btn == 'middle': names.append('Middle Click')
            else: names.append(f'Mouse {btn}')
        else:
            names.append(s)
    return " + ".join(names)
