"""Background keystroke injection for transcribed text.

pynput's Controller.type() blocks for tens of milliseconds per phrase (and
proportionally longer for big ones), and NLPProcessor's hotkey commands add
their own sleeps. Running that on the Qt GUI thread froze the HUD, the VU
meter, and the tray mid-utterance. This worker drains a queue on a plain
daemon thread so the GUI never blocks; texts are injected strictly in order.
"""

import logging
import queue
import threading
import time

from pynput.keyboard import Key

logger = logging.getLogger(__name__)

_SENTINEL = None


class TypingWorker(threading.Thread):
    def __init__(self, nlp_engine, auto_enter_provider):
        """
        nlp_engine: NLPProcessor that transforms + injects the text.
        auto_enter_provider: zero-arg callable returning bool — consulted per
            utterance so settings changes apply without rebuilding the worker.
        """
        super().__init__(daemon=True, name="TypingWorker")
        self.nlp_engine = nlp_engine
        self.auto_enter_provider = auto_enter_provider
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        # NOTE: not named '_started' — that collides with Thread internals.
        self._launched = False

    def submit(self, text):
        if not text:
            return
        with self._lock:
            if not self._launched:
                self._launched = True
                self.start()
        self._queue.put(text)

    def stop(self):
        """Signals the worker to exit after the current utterance."""
        with self._lock:
            if self._launched:
                self._queue.put(_SENTINEL)
                self.join(timeout=2.0)

    def run(self):
        while True:
            text = self._queue.get()
            if text is _SENTINEL:
                return
            try:
                self._type(text)
            except Exception as e:
                logger.error(f"Typing worker error: {e}")

    def _type(self, text):
        # Let focus settle back onto the target window before injecting.
        time.sleep(0.04)
        self.nlp_engine.process(text)

        if self.auto_enter_provider() and not self.nlp_engine.is_paused:
            time.sleep(0.04)
            keyboard = self.nlp_engine.keyboard
            keyboard.press(Key.enter)
            keyboard.release(Key.enter)
            self.nlp_engine.is_first_word = True
