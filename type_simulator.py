from pynput.keyboard import Controller
import time
import logging

logger = logging.getLogger(__name__)

class TypeSimulator:
    def __init__(self):
        self.keyboard = Controller()

    def type_text(self, text):
        if not text:
            return
            
        logger.info("Simulating keystrokes...")
        time.sleep(0.05)
        self.keyboard.type(text)
        logger.info("Keystrokes simulated successfully.")
