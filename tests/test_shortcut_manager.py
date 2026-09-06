"""Tests for shortcut normalization, activation logic, and friendly names."""

import pytest

pytest.importorskip("pynput", reason="pynput needs an available input backend")

from shortcut_manager import ShortcutManager, get_friendly_name, normalize_key, normalize_mouse  # noqa: E402


class FakeKey:
    """Stands in for pynput's KeyCode / Key objects."""

    def __init__(self, name=None, char=None):
        if name is not None:
            self.name = name
        if char is not None:
            self.char = char

    def __str__(self):
        return f"<FakeKey {getattr(self, 'name', getattr(self, 'char', '?'))}>"


class FakeButton:
    def __init__(self, label):
        self.label = label

    def __str__(self):
        return f"Button.{self.label}"


def test_normalize_named_and_char_keys():
    assert normalize_key(FakeKey(name="ctrl_l")) == "keyboard.ctrl_l"
    assert normalize_key(FakeKey(char="A")) == "keyboard.char.a"


def test_normalize_control_character_folds_to_letter():
    # Ctrl+A is delivered as \x01; it must map to the same id as a bare 'a'
    assert normalize_key(FakeKey(char="\x01")) == "keyboard.char.a"
    assert normalize_key(FakeKey(char="\x1a")) == "keyboard.char.z"


def test_normalize_mouse():
    assert normalize_mouse(FakeButton("x2")) == "mouse.Button.x2"


def _manager(shortcut, toggle=False):
    events = []
    mgr = ShortcutManager(shortcut, events.append, is_toggle_mode=toggle)
    return mgr, events


def test_hold_mode_press_and_release():
    mgr, events = _manager(["mouse.Button.x2"])
    mgr.on_mouse_click(0, 0, FakeButton("x2"), True)
    assert events == [True]
    mgr.on_mouse_click(0, 0, FakeButton("x2"), False)
    assert events == [True, False]


def test_hold_mode_ignores_repeat_press():
    mgr, events = _manager(["keyboard.char.q"])
    key = FakeKey(char="q")
    mgr.on_key_press(key)
    mgr.on_key_press(key)  # auto-repeat must not re-fire
    assert events == [True]


def test_toggle_mode_fires_once_per_press():
    mgr, events = _manager(["keyboard.char.q"], toggle=True)
    key = FakeKey(char="q")
    mgr.on_key_press(key)
    mgr.on_key_release(key)
    assert events == [True]  # no False on release
    mgr.on_key_press(key)
    mgr.on_key_release(key)
    assert events == [True, True]  # each press fires exactly once


def test_combination_requires_all_keys():
    mgr, events = _manager(["keyboard.ctrl_l", "keyboard.char.d"])
    ctrl, d = FakeKey(name="ctrl_l"), FakeKey(char="d")
    mgr.on_key_press(ctrl)
    assert events == []  # partial match does not fire
    mgr.on_key_press(d)
    assert events == [True]
    mgr.on_key_release(d)
    assert events == [True, False]


def test_empty_shortcut_never_fires():
    mgr, events = _manager([])
    mgr.on_key_press(FakeKey(char="a"))
    assert events == []


def test_callback_exception_does_not_break_listener():
    def boom(_):
        raise RuntimeError("callback failed")

    mgr = ShortcutManager(["keyboard.char.a"], boom)
    mgr.on_key_press(FakeKey(char="a"))  # must not propagate
    mgr.on_key_release(FakeKey(char="a"))


def test_update_config_clears_stuck_state():
    mgr, events = _manager(["keyboard.char.a"])
    mgr.on_key_press(FakeKey(char="a"))
    assert mgr.is_active is True
    mgr.update_config(["keyboard.char.b"], False)
    assert mgr.is_active is False
    assert mgr.current_keys == set()


def test_friendly_names():
    assert get_friendly_name(["mouse.Button.x2"]) == "Mouse 5"
    assert get_friendly_name(["mouse.Button.x1"]) == "Mouse 4"
    assert get_friendly_name(["keyboard.ctrl_l", "keyboard.char.d"]) == "Ctrl_L + D"
    assert get_friendly_name([]) == "Unbound"
