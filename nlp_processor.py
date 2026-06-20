import re
import time
import logging
from pynput.keyboard import Key, Controller

logger = logging.getLogger(__name__)

class NLPProcessor:
    def __init__(self, simulator):
        self.simulator = simulator
        self.keyboard = simulator.keyboard
        self.suppress_leading_space = False
        self.is_first_word = True
        self.is_paused = False

    def simulate_hotkey(self, modifier, key, secondary_key=None):
        time.sleep(0.05)
        self.keyboard.press(modifier)
        if secondary_key:
            self.keyboard.press(secondary_key)
        self.keyboard.press(key)
        
        self.keyboard.release(key)
        if secondary_key:
            self.keyboard.release(secondary_key)
        self.keyboard.release(modifier)
        time.sleep(0.05)

    def process(self, text):
        if not text:
            return

        cleaned = re.sub(r'[.!?]+$', '', text.strip()).lower()
        
        # --- Pause / Resume Commands ---
        if re.match(r'(?i)^(vocara|vokara|bokara|bakara)\s+pause$', cleaned) or cleaned == "pause dictation":
            logger.info("NLP: Executing 'vocara pause'")
            self.is_paused = True
            return

        if re.match(r'(?i)^(vocara|vokara|bokara|bakara)\s+resume$', cleaned) or cleaned == "resume dictation":
            logger.info("NLP: Executing 'vocara resume'")
            self.is_paused = False
            self.is_first_word = True
            return
            
        if self.is_paused:
            logger.info("NLP: Ignored text while paused.")
            return
        
        # --- System Hotkeys (Command Injection) ---
        if cleaned == "scratch that":
            logger.info("NLP: Executing 'scratch that'")
            self.simulate_hotkey(Key.ctrl, Key.backspace)
            self.suppress_leading_space = True 
            return
            
        if cleaned == "strike line":
            logger.info("NLP: Executing 'strike line'")
            self.simulate_hotkey(Key.shift, Key.home)
            self.keyboard.press(Key.backspace)
            self.keyboard.release(Key.backspace)
            self.is_first_word = True
            return
            
        if cleaned == "undo last":
            logger.info("NLP: Executing 'undo last'")
            self.simulate_hotkey(Key.ctrl, 'z')
            return
            
        if cleaned == "select all":
            logger.info("NLP: Executing 'select all'")
            self.simulate_hotkey(Key.ctrl, 'a')
            return
            
        if cleaned == "save document":
            logger.info("NLP: Executing 'save document'")
            self.simulate_hotkey(Key.ctrl, 's')
            return
            
        if re.match(r'(?i)^(vocara|vokara|bokara|bakara)\s+(clear|clean)$', cleaned) or cleaned == "clear sentence":
            logger.info("NLP: Executing 'vocara clear'")
            for _ in range(15):
                self.simulate_hotkey(Key.ctrl, Key.backspace)
            self.is_first_word = True
            return

        # --- Inline Smart Punctuation & Spacing ---
        
        text = re.sub(r'(?i)\bopen (quote|code)[.!?,\s]*', '"', text)
        
        text = re.sub(r'(?i)\bopen bracket[.!?,\s]*', '(', text)
        
        text = re.sub(r'(?i)[\s]*\bclose (quote|code)\b[.!?,\s]*', '" ', text)
        
        text = re.sub(r'(?i)[\s]*\bclose bracket\b[.!?,\s]*', ') ', text)
        
        match = re.search(r'(?i)\b(quote|quot|code|court)[,.\s]+(unquote|un-quote|on quote|and quote|and quot|on code|and code|un-gote|uncord)\b[.!?,\s]*', text)
        if match:
            before = text[:match.start()]
            after = text[match.end():]
            
            if before:
                prefix = "" if self.is_first_word or self.suppress_leading_space else " "
                if re.match(r'^[.,!?;:]', before):
                    prefix = ""
                self.simulator.type_text(prefix + before)
                self.suppress_leading_space = False
                self.is_first_word = False
                
            prefix = "" if self.is_first_word or self.suppress_leading_space else " "
            if after:
                self.simulator.type_text(prefix + f'"{after}"')
            else:
                self.simulator.type_text(prefix + '""')
                self.keyboard.press(Key.left)
                self.keyboard.release(Key.left)
                self.suppress_leading_space = True
                
            self.is_first_word = False
            return

        # --- Standard Text Typing ---
        prefix = "" if self.is_first_word or self.suppress_leading_space else " "
        
        if re.match(r'^[.,!?;:]', text):
            prefix = ""
            
        self.simulator.type_text(prefix + text)
        
        self.suppress_leading_space = False
        self.is_first_word = False
