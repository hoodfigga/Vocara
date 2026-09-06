import logging
import threading

from pynput import keyboard, mouse

logger = logging.getLogger(__name__)


def normalize_key(key):
    """Maps a pynput key event to a stable string id.

    Modified letter keys (Ctrl+A) arrive as control characters ('\\x01'), which
    would never match the id recorded during rebinding; those are folded back to
    the corresponding letter so combinations bind consistently.
    """
    name = getattr(key, "name", None)
    if name:
        return f"keyboard.{name}"
    char = getattr(key, "char", None)
    if char:
        if len(char) == 1 and 1 <= ord(char) <= 26:
            char = chr(ord(char) + 96)  # \x01 -> 'a'
        return f"keyboard.char.{char.lower()}"
    return str(key)


def normalize_mouse(button):
    return f"mouse.{str(button)}"


class ShortcutManager:
    def __init__(self, target_shortcut, callback, is_toggle_mode=False):
        """
        target_shortcut: list of string representations of keys/buttons
        callback: function(bool is_active)

        In hold mode the callback receives True on press and False on release.
        In toggle mode it receives True once per fresh press; the consumer owns
        the start/stop state, so the two can never drift out of sync.
        """
        self.target_shortcut = set(target_shortcut)
        self.callback = callback
        self.is_toggle_mode = is_toggle_mode

        self.current_keys = set()
        self.is_active = False  # shortcut is physically held
        self.lock = threading.Lock()

        self.kb_listener = None
        self.mouse_listener = None

    def start(self):
        if self.kb_listener is None or not self.kb_listener.is_alive():
            self.kb_listener = keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release)
            self.kb_listener.start()
        if self.mouse_listener is None or not self.mouse_listener.is_alive():
            self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
            self.mouse_listener.start()

    def stop(self):
        for listener in (self.kb_listener, self.mouse_listener):
            if listener is not None:
                try:
                    listener.stop()
                except Exception as e:
                    logger.debug(f"Error stopping listener: {e}")
        with self.lock:
            self.current_keys.clear()
            self.is_active = False

    def update_config(self, target_shortcut, is_toggle_mode):
        with self.lock:
            self.target_shortcut = set(target_shortcut)
            self.is_toggle_mode = is_toggle_mode
            self.current_keys.clear()
            self.is_active = False

    def _evaluate(self):
        """Recomputes activation state. Returns the value to hand the callback,
        or None when nothing changed. Must be called while holding the lock;
        the callback itself is invoked outside it."""
        match = bool(self.target_shortcut) and self.target_shortcut.issubset(self.current_keys)

        if match and not self.is_active:
            self.is_active = True
            return True

        if not match and self.is_active:
            self.is_active = False
            # Toggle mode ignores the release: the press alone flips the state.
            if not self.is_toggle_mode:
                return False
        return None

    def _dispatch(self, value):
        if value is None:
            return
        try:
            self.callback(value)
        except Exception as e:
            logger.error(f"Shortcut callback failed: {e}")

    def on_key_press(self, key):
        k = normalize_key(key)
        logger.debug(f"Key pressed: {k}")
        with self.lock:
            self.current_keys.add(k)
            result = self._evaluate()
        self._dispatch(result)

    def on_key_release(self, key):
        k = normalize_key(key)
        with self.lock:
            self.current_keys.discard(k)
            result = self._evaluate()
        self._dispatch(result)

    def on_mouse_click(self, x, y, button, pressed):
        b = normalize_mouse(button)
        logger.debug(f"Mouse event: {b}, pressed: {pressed}")
        with self.lock:
            if pressed:
                self.current_keys.add(b)
            else:
                self.current_keys.discard(b)
            result = self._evaluate()
        self._dispatch(result)


class RebindListener:
    """Listens for the next keystroke or mouse click to bind a new shortcut."""

    def __init__(self, callback):
        self.callback = callback
        self.captured = set()
        self.done = False
        self.lock = threading.Lock()

        self.kb_listener = keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release)
        self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)

    def start(self):
        self.kb_listener.start()
        self.mouse_listener.start()

    def stop(self):
        for listener in (self.kb_listener, self.mouse_listener):
            try:
                listener.stop()
            except Exception as e:
                logger.debug(f"Error stopping rebind listener: {e}")

    def _finish(self):
        with self.lock:
            if self.done or not self.captured:
                return
            self.done = True
            captured = list(self.captured)
        self.stop()
        try:
            self.callback(captured)
        except Exception as e:
            logger.error(f"Rebind callback failed: {e}")

    def on_key_press(self, key):
        if self.done:
            return
        k = normalize_key(key)
        logger.debug(f"Rebind key pressed: {k}")
        self.captured.add(k)

    def on_key_release(self, key):
        if self.done:
            return
        self._finish()

    def on_mouse_click(self, x, y, button, pressed):
        if self.done:
            return
        b = normalize_mouse(button)
        logger.debug(f"Rebind mouse event: {b}, pressed: {pressed}")
        if pressed:
            # Left click is reserved for interacting with the dialog itself
            if str(button) != "Button.left":
                self.captured.add(b)
        else:
            self._finish()


_MOUSE_LABELS = {
    "x1": "Mouse 4",
    "x2": "Mouse 5",
    "left": "Left Click",
    "right": "Right Click",
    "middle": "Middle Click",
}


def get_friendly_name(shortcut_list):
    if not shortcut_list:
        return "Unbound"
    names = []
    for s in shortcut_list:
        if s.startswith("keyboard.char."):
            names.append(s.split(".")[-1].upper())
        elif s.startswith("keyboard."):
            names.append(s.split(".")[-1].title())
        elif s.startswith("mouse.Button."):
            btn = s.split(".")[-1]
            names.append(_MOUSE_LABELS.get(btn, f"Mouse {btn}"))
        else:
            names.append(s)
    return " + ".join(names)
