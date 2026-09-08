"""Tests for the background typing worker and the always-on pause/resume flow.

Uses fake simulators so no real keystrokes are injected.
"""

import threading
import time

import pytest

pytest.importorskip("pynput", reason="pynput needs an available input backend")

from nlp_processor import NLPProcessor  # noqa: E402
from typing_worker import TypingWorker  # noqa: E402


class FakeKeyboard:
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
        self.lock = threading.Lock()

    def type_text(self, text):
        with self.lock:
            self.typed += text
        self.keyboard.events.append(("type_text", text))


@pytest.fixture
def nlp():
    sim = FakeSimulator()
    proc = NLPProcessor(sim, command_callback=lambda name: None)
    return proc, sim


def _drain_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_worker_types_text_off_thread(nlp):
    proc, sim = nlp
    worker = TypingWorker(proc, lambda: False)
    worker.submit("hello world")
    try:
        assert _drain_until(lambda: sim.typed == "hello world")
        # The worker thread is not the main thread, proving typing happens
        # off the GUI thread.
        assert worker.is_alive()
    finally:
        worker.stop()


def test_worker_preserves_order(nlp):
    proc, sim = nlp
    worker = TypingWorker(proc, lambda: False)
    for text in ("one", "two", "three"):
        worker.submit(text)
    try:
        assert _drain_until(lambda: sim.typed == "one two three")
    finally:
        worker.stop()


def test_worker_auto_enter_presses_enter(nlp):
    proc, sim = nlp
    worker = TypingWorker(proc, lambda: True)
    worker.submit("press return")
    try:
        assert _drain_until(lambda: any(k == "enter" for _, k in sim.keyboard.events))
        assert proc.is_first_word is True
    finally:
        worker.stop()


def test_worker_respects_pause_state(nlp):
    proc, sim = nlp
    proc.is_paused = True
    worker = TypingWorker(proc, lambda: False)
    worker.submit("vocara resume")
    try:
        assert _drain_until(lambda: not proc.is_paused)
        # Text typed after resume; the resume command itself types nothing.
        worker.submit("back again")
        assert _drain_until(lambda: sim.typed == "back again")
    finally:
        worker.stop()


def test_worker_stop_terminates_cleanly(nlp):
    proc, sim = nlp
    worker = TypingWorker(proc, lambda: False)
    worker.submit("bye")
    assert _drain_until(lambda: sim.typed == "bye")
    worker.stop()
    assert not worker.is_alive()


def test_paused_nlp_still_accepts_resume_command(nlp):
    """Regression: always-on mode used to drop phrases while NLP-paused, so
    'vocara resume' was never transcribed and voice pause could never be
    voice-resumed. NLPProcessor must keep processing commands while paused."""
    proc, sim = nlp
    proc.process("vocara pause")
    assert proc.is_paused

    proc.process("vocara resume")
    assert not proc.is_paused
    assert sim.typed == ""  # neither command typed anything
