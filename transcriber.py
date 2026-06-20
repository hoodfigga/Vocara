
import re
import logging
import json
import os

logger = logging.getLogger(__name__)

BASE_PROMPT = "Hello! Let's write out some thoughts, including technical terms like GTK, PipeWire, Python, Wayland, and X11. It's a nice day, isn't it?"

from config import DICT_FILE as DICTIONARY_FILE

class WhisperTranscriber:
    def __init__(self, model_size="base"):
        import whisper
        import torch
        
        models_dir = os.path.join(os.path.expanduser('~'), '.local', 'share', 'Vocara', 'Models')
        os.makedirs(models_dir, exist_ok=True)
        
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading Whisper model '{model_size}' into {models_dir}")
        
        self.model = whisper.load_model(model_size, device=self.device, download_root=models_dir)
        logger.info("Offline Whisper model loaded successfully.")

    def process_cancellation(self, text):
        """
        Smart cancellation logic.
        If the text ends with 'cancel that' (ignoring punctuation/case),
        it finds the last full stop BEFORE the cancellation phrase and deletes everything after it.
        """
        trigger = "cancel that"
        
        match = re.search(r'(?i)\s*' + trigger + r'[.!?]*$', text)
        if not match:
            return text
            
        base_text = text[:match.start()].strip()
        
        search_text = re.sub(r'[.!?]+$', '', base_text)
        
        last_terminator = max(search_text.rfind('.'), search_text.rfind('?'), search_text.rfind('!'))
        
        if last_terminator == -1:
            return ""
            
        return base_text[:last_terminator+1].strip()

    def _get_dynamic_prompt(self):
        prompt = BASE_PROMPT
        if os.path.exists(DICTIONARY_FILE):
            try:
                with open(DICTIONARY_FILE, 'r') as f:
                    words = json.load(f)
                if words:
                    prompt += " Please prioritize these specific terms if they match the audio: " + ", ".join(words) + "."
            except Exception as e:
                logger.error(f"Failed to load personal dictionary: {e}")
        return prompt

    def transcribe(self, audio_array):
        if len(audio_array) == 0:
            return ""
            
        logger.info("Transcribing audio...")
        result = self.model.transcribe(
            audio_array, 
            fp16=False,
            initial_prompt=self._get_dynamic_prompt()
        )
        
        raw_text = result["text"].strip()
        logger.info(f"Raw transcription: {raw_text}")
        
        final_text = self.process_cancellation(raw_text)
        if final_text != raw_text:
            logger.info(f"Processed transcription (Cancelled): {final_text}")
            
        return final_text
