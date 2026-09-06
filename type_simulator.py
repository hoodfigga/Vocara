import logging
import time

from pynput.keyboard import Controller, Key

logger = logging.getLogger(__name__)


class TypeSimulator:
    def __init__(self):
        self.keyboard = Controller()

    def type_text(self, text):
        """
        Simulates typing of the transcribed text into the currently active window.
        Uses native pynput keystrokes with smooth character delivery.
        """
        if not text:
            return

        logger.info(f"Simulating keystrokes for {len(text)} characters...")
        time.sleep(0.04)

        try:
            self.keyboard.type(text)
            logger.info("Keystrokes simulated successfully.")
        except Exception as e:
            logger.warning(f"pynput typing encountered an issue: {e}. Attempting fallback paste...")
            try:
                # Fallback for complex Unicode or Windows SendInput limitations
                from PySide6.QtWidgets import QApplication

                clipboard = QApplication.clipboard()
                orig_clip = clipboard.text()
                clipboard.setText(text)

                # Send Ctrl+V
                ctrl_key = Key.ctrl
                self.keyboard.press(ctrl_key)
                self.keyboard.press("v")
                self.keyboard.release("v")
                self.keyboard.release(ctrl_key)

                # Restore clipboard after brief delay
                time.sleep(0.08)
                if orig_clip:
                    clipboard.setText(orig_clip)
                logger.info("Fallback paste completed.")
            except Exception as e2:
                logger.error(f"Fallback paste failed: {e2}")
