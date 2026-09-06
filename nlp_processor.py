import logging
import re
import time

from pynput.keyboard import Key

logger = logging.getLogger(__name__)


class NLPProcessor:
    def __init__(self, simulator, command_callback=None):
        self.simulator = simulator
        self.keyboard = simulator.keyboard
        self.command_callback = command_callback
        self.suppress_leading_space = False
        self.is_first_word = True
        self.is_paused = False

    def _notify_command(self, name):
        """Reports a spoken-command badge to the UI; UI errors must never
        interrupt the dictation flow."""
        if self.command_callback:
            try:
                self.command_callback(name)
            except Exception:
                pass

    def simulate_hotkey(self, modifier, key, secondary_key=None):
        time.sleep(0.04)
        self.keyboard.press(modifier)
        if secondary_key:
            self.keyboard.press(secondary_key)
        self.keyboard.press(key)

        self.keyboard.release(key)
        if secondary_key:
            self.keyboard.release(secondary_key)
        self.keyboard.release(modifier)
        time.sleep(0.04)

    def process(self, text):
        if not text:
            return

        cleaned = re.sub(r"[.!?]+$", "", text.strip()).lower()

        # --- Pause / Resume Commands ---
        if re.match(r"(?i)^(vocara|vokara|bokara|bakara)\s+pause$", cleaned) or cleaned == "pause dictation":
            logger.info("NLP: Executing 'vocara pause'")
            self.is_paused = True
            self._notify_command("Vocara Paused")
            return

        if (
            re.match(r"(?i)^(vocara|vokara|bokara|bakara)\s+resume$", cleaned)
            or cleaned == "resume dictation"
        ):
            logger.info("NLP: Executing 'vocara resume'")
            self.is_paused = False
            self.is_first_word = True
            self._notify_command("Vocara Resumed")
            return

        if self.is_paused:
            logger.info("NLP: Ignored text while paused.")
            return

        # --- System Hotkeys (Command Injection) ---
        if cleaned == "scratch that":
            logger.info("NLP: Executing 'scratch that'")
            self.simulate_hotkey(Key.ctrl, Key.backspace)
            self.suppress_leading_space = True
            self._notify_command("Scratch That (Delete Word)")
            return

        if cleaned == "strike line":
            logger.info("NLP: Executing 'strike line'")
            self.simulate_hotkey(Key.shift, Key.home)
            self.keyboard.press(Key.backspace)
            self.keyboard.release(Key.backspace)
            self.is_first_word = True
            self._notify_command("Strike Line (Clear Line)")
            return

        if cleaned == "undo last":
            logger.info("NLP: Executing 'undo last'")
            self.simulate_hotkey(Key.ctrl, "z")
            self._notify_command("Undo Last")
            return

        if cleaned == "select all":
            logger.info("NLP: Executing 'select all'")
            self.simulate_hotkey(Key.ctrl, "a")
            self._notify_command("Select All")
            return

        if cleaned == "save document":
            logger.info("NLP: Executing 'save document'")
            self.simulate_hotkey(Key.ctrl, "s")
            self._notify_command("Save Document")
            return

        if (
            re.match(r"(?i)^(vocara|vokara|bokara|bakara)\s+(clear|clean)$", cleaned)
            or cleaned == "clear sentence"
        ):
            logger.info("NLP: Executing 'vocara clear'")
            for _ in range(15):
                self.simulate_hotkey(Key.ctrl, Key.backspace)
            self.is_first_word = True
            self._notify_command("Vocara Clear")
            return

        # --- Inline Smart Punctuation & Spacing ---
        # 'quote <text> unquote' (Whisper may add commas: 'quote, <text>, unquote')
        # -> '"<text>"'. 'open quote' must not be treated as the opener of a wrap.
        wrap_state = {"empty": False}

        def wrap_quote(match):
            inner = match.group("inner").strip()
            # Drop punctuation Whisper sprinkled around the quoted span
            inner = re.sub(r"^[\s,.;:!?\-\u2014]+|[\s,.;:!?\-\u2014]+$", "", inner)
            if not inner:
                wrap_state["empty"] = True
                return '""'
            return f'"{inner}"'

        wrap_pattern = re.compile(
            r"(?i)(?<!open\s)\b(?:quote|quot|court)\b"
            r"(?P<inner>.*?)"
            r"\b(?:unquote|un-quote|end quote|close quote|and quote|on quote)\b"
        )
        text = wrap_pattern.sub(wrap_quote, text)

        if wrap_state["empty"]:
            # Empty wrap: type "" and leave the cursor inside the quotes
            self.simulator.type_text('""')
            self.keyboard.press(Key.left)
            self.keyboard.release(Key.left)
            self.suppress_leading_space = True
            self.is_first_word = False
            return

        text = re.sub(r"(?i)\bopen (quote|code)[.!?,\s]*", '"', text)
        text = re.sub(r"(?i)\bopen bracket[.!?,\s]*", "(", text)
        text = re.sub(r"(?i)[\s]*\bclose (quote|code)\b", '"', text)
        text = re.sub(r"(?i)[\s]*\bclose bracket\b", ")", text)

        # --- Standard Text Typing ---
        text = text.strip()
        prefix = "" if self.is_first_word or self.suppress_leading_space else " "
        if re.match(r'^[.,!?;:)("]', text):
            prefix = ""
        self.simulator.type_text(prefix + text)
        self.suppress_leading_space = False
        self.is_first_word = False
