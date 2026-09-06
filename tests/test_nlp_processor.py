"""Tests for NLPProcessor voice commands and smart typing, using a fake
simulator so no real keystrokes are ever injected."""

import pytest

pytest.importorskip("pynput", reason="pynput needs an available input backend")

from nlp_processor import NLPProcessor  # noqa: E402


class FakeKeyboard:
    """Records press/release/type calls instead of driving real input."""

    def __init__(self):
        self.events = []

    def press(self, key):
        self.events.append(("press", getattr(key, "name", str(key))))

    def release(self, key):
        self.events.append(("release", getattr(key, "name", str(key))))

    def type(self, text):
        self.events.append(("type", text))


class FakeSimulator:
    def __init__(self):
        self.keyboard = FakeKeyboard()
        self.typed = ""

    def type_text(self, text):
        self.typed += text
        self.keyboard.events.append(("type_text", text))


@pytest.fixture
def nlp():
    sim = FakeSimulator()
    notifications = []
    return NLPProcessor(sim, command_callback=notifications.append), sim, notifications


def test_plain_text_typing_spacing(nlp):
    proc, sim, _ = nlp
    proc.process("Hello")
    proc.process("world")
    assert sim.typed == "Hello world"


def test_punctuation_start_does_not_add_leading_space(nlp):
    proc, sim, _ = nlp
    proc.is_first_word = False
    proc.process("What?")  # normal: space separator
    proc.process(", really")  # starts with punctuation: no space added
    assert sim.typed == " What?, really"


def test_vocara_pause_and_resume(nlp):
    proc, sim, notifications = nlp
    proc.process("vocara pause")
    assert proc.is_paused is True
    assert "Vocara Paused" in notifications
    assert sim.typed == ""

    proc.process("this should be ignored")
    assert sim.typed == ""  # paused: nothing typed

    proc.process("vocara resume")
    assert proc.is_paused is False
    proc.process("back again")
    assert sim.typed == "back again"


def test_vocara_pause_phonetic_variants(nlp):
    proc, sim, _ = nlp
    proc.process("vokara pause")
    assert proc.is_paused is True
    proc.process("bakara resume")
    assert proc.is_paused is False


def test_scratch_that_deletes_word(nlp):
    proc, sim, notifications = nlp
    proc.process("scratch that")
    assert any("Scratch That" in n for n in notifications)
    # Ctrl+Backspace without any typed text
    keys = [e for e in sim.keyboard.events if e[0] in ("press", "release")]
    assert ("press", "ctrl") in keys
    assert ("press", "backspace") in keys
    assert sim.typed == ""


def test_strike_line_clears_line(nlp):
    proc, sim, _ = nlp
    proc.process("strike line")
    # Shift+Home then Backspace
    names = [k for kind, k in sim.keyboard.events]
    assert "shift" in names and "home" in names and "backspace" in names


def test_undo_and_save_hotkeys(nlp):
    proc, sim, notifications = nlp
    proc.process("undo last")
    assert any(e == ("press", "ctrl") for e in sim.keyboard.events)
    proc.process("save document")
    assert "Save Document" in notifications


def test_open_close_quote_replacement(nlp):
    proc, sim, _ = nlp
    proc.process("say open quote hello close quote")
    # 'open quote' -> '"', 'close quote' -> '"'
    assert '"' in sim.typed
    assert sim.typed.replace(" ", "").startswith("say")


def test_quote_unquote_wrapping(nlp):
    proc, sim, _ = nlp
    proc.process("quote hello there unquote")
    assert sim.typed == '"hello there"'


def test_quote_unquote_with_commas_and_context(nlp):
    proc, sim, _ = nlp
    proc.process("say quote, hello there, unquote now")
    assert sim.typed == 'say "hello there" now'


def test_quote_unquote_empty_opens_empty_quotes(nlp):
    proc, sim, _ = nlp
    proc.process("quote unquote")
    assert sim.typed == '""'
    # cursor moved back inside the quotes
    assert any(k == "left" for _, k in sim.keyboard.events)


def test_open_bracket_close_bracket(nlp):
    proc, sim, _ = nlp
    proc.process("open bracket hi close bracket")
    assert sim.typed == "(hi)"


def test_open_close_quote_keeps_following_spacing(nlp):
    proc, sim, _ = nlp
    proc.process("open quote hello close quote now")
    # 'open quote' -> '"', 'close quote' -> '"', space before 'now' preserved
    assert sim.typed == '"hello" now'


def test_vocara_clear_not_typed(nlp):
    proc, sim, _ = nlp
    proc.process("vocara clear")
    assert sim.typed == ""
    # repeated Ctrl+Backspace deletes recent words
    names = [k for kind, k in sim.keyboard.events]
    assert names.count("backspace") >= 2


def test_command_callback_errors_are_swallowed(nlp):
    proc, sim, _ = nlp

    def boom(_name):
        raise RuntimeError("ui died")

    proc.command_callback = boom
    proc.process("vocara pause")  # must not raise
