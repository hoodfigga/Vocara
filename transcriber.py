import os
import sys
import platform
import re
import json
import logging
import numpy as np

logger = logging.getLogger(__name__)

BASE_PROMPT = "Hello! Let's write out some thoughts, including technical terms like GTK, PipeWire, Python, Wayland, and X11. It's a nice day, isn't it?"

from config import DICT_FILE as DICTIONARY_FILE

class WhisperTranscriber:
    def __init__(self, model_size="base", engine="faster-whisper", device="auto", compute_type="auto", vad_filter=True, language=None):
        """
        Initializes the transcription engine.
        Defaults to faster-whisper (CTranslate2) with seamless fallback to openai-whisper.
        Supports models: 'tiny', 'base', 'small', 'medium', 'turbo', 'large-v3'.
        """
        self.model_size = model_size
        self.engine_type = engine
        self.requested_device = device
        self.compute_type = compute_type
        self.vad_filter = vad_filter
        self.language = language
        
        if platform.system() == "Windows":
            self.models_dir = os.path.join(os.getenv('LOCALAPPDATA', os.path.expanduser('~')), 'Vocara', 'Models')
        else:
            self.models_dir = os.path.join(os.path.expanduser('~'), '.local', 'share', 'Vocara', 'Models')
        os.makedirs(self.models_dir, exist_ok=True)
        
        self.model = None
        self.actual_device = "cpu"
        self.actual_engine = "unknown"
        
        self._load_engine()

    def _determine_device_and_compute(self):
        """Resolves target device and compute precision."""
        device = self.requested_device
        compute = self.compute_type

        if device == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                else:
                    device = "cpu"
            except Exception:
                device = "cpu"

        if compute == "auto":
            if device == "cuda":
                compute = "float16"
            else:
                compute = "int8"

        return device, compute

    def _load_engine(self):
        """Attempts to load the selected engine with fallback."""
        device, compute = self._determine_device_and_compute()

        if self.engine_type == "faster-whisper":
            try:
                self._load_faster_whisper(device, compute)
                return
            except Exception as e:
                logger.warning(f"Failed to load faster-whisper on {device} ({e}). Retrying on CPU...")
                try:
                    self._load_faster_whisper("cpu", "int8")
                    return
                except Exception as e2:
                    logger.warning(f"faster-whisper CPU load failed: {e2}. Falling back to openai-whisper...")
        
        # Fallback to standard openai-whisper
        try:
            self._load_openai_whisper(device)
        except Exception as e:
            logger.error(f"Failed to load openai-whisper: {e}. Retrying CPU...")
            self._load_openai_whisper("cpu")

    def _load_faster_whisper(self, device, compute):
        from faster_whisper import WhisperModel

        logger.info(f"Loading faster-whisper model '{self.model_size}' [device={device}, compute_type={compute}]")
        self.model = WhisperModel(
            self.model_size,
            device=device,
            compute_type=compute,
            download_root=self.models_dir
        )
        self.actual_device = device
        self.actual_engine = "faster-whisper"
        logger.info(f"faster-whisper '{self.model_size}' loaded successfully on {device} ({compute}).")

    def _load_openai_whisper(self, device):
        import whisper
        import torch

        if device == "cuda" and not torch.cuda.is_available():
            device = "cpu"

        # Model name translation for openai-whisper if 'turbo' requested
        model_name = "large-v3-turbo" if self.model_size == "turbo" else self.model_size
        logger.info(f"Loading openai-whisper model '{model_name}' on {device}")
        self.model = whisper.load_model(model_name, device=device, download_root=self.models_dir)
        self.actual_device = device
        self.actual_engine = "openai-whisper"
        logger.info(f"openai-whisper '{model_name}' loaded successfully on {device}.")

    def process_cancellation(self, text):
        """
        Smart cancellation logic.
        If the text ends with 'cancel that' or 'scratch that' (ignoring punctuation/case),
        it finds the last full stop BEFORE the cancellation phrase and deletes everything after it.
        """
        triggers = [r'cancel that', r'scratch that']
        pattern = r'(?i)\s*(?:' + '|'.join(triggers) + r')[.!?]*$'
        
        match = re.search(pattern, text)
        if not match:
            return text
            
        base_text = text[:match.start()].strip()
        search_text = re.sub(r'[.!?]+$', '', base_text)
        last_terminator = max(search_text.rfind('.'), search_text.rfind('?'), search_text.rfind('!'))
        
        if last_terminator == -1:
            return ""
            
        return base_text[:last_terminator + 1].strip()

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
        """Transcribes a 16kHz mono float32 numpy audio array."""
        if audio_array is None or len(audio_array) == 0:
            return ""

        # Normalize audio if necessary
        if np.max(np.abs(audio_array)) > 0:
            # Ensure float32 format
            audio_array = audio_array.astype(np.float32)

        prompt = self._get_dynamic_prompt()

        if self.actual_engine == "faster-whisper":
            try:
                segments, info = self.model.transcribe(
                    audio_array,
                    initial_prompt=prompt,
                    vad_filter=self.vad_filter,
                    language=self.language
                )
                raw_text = " ".join([seg.text.strip() for seg in segments if seg.text]).strip()
            except Exception as e:
                logger.error(f"faster-whisper transcription error: {e}")
                raw_text = ""
        else:
            try:
                result = self.model.transcribe(
                    audio_array,
                    fp16=False,
                    initial_prompt=prompt,
                    language=self.language
                )
                raw_text = result.get("text", "").strip()
            except Exception as e:
                logger.error(f"openai-whisper transcription error: {e}")
                raw_text = ""

        logger.info(f"Raw transcription: {raw_text}")
        final_text = self.process_cancellation(raw_text)
        if final_text != raw_text:
            logger.info(f"Processed transcription (Cancelled): {final_text}")

        return final_text
