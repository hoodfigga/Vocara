import json
import logging
import os
import platform
import re

import numpy as np

from config import DICT_FILE as DICTIONARY_FILE

logger = logging.getLogger(__name__)

BASE_PROMPT = "Hello! Let's write out some thoughts, including technical terms like GTK, PipeWire, Python, Wayland, and X11. It's a nice day, isn't it?"

# Whisper's initial_prompt is capped by the model's context; keep the injected
# vocabulary well inside it so long dictionaries cannot crowd out the audio.
MAX_PROMPT_CHARS = 800


class WhisperTranscriber:
    def __init__(
        self,
        model_size="base",
        engine="faster-whisper",
        device="auto",
        compute_type="auto",
        vad_filter=True,
        language=None,
    ):
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
            self.models_dir = os.path.join(
                os.getenv("LOCALAPPDATA", os.path.expanduser("~")), "Vocara", "Models"
            )
        else:
            self.models_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "Vocara", "Models")
        os.makedirs(self.models_dir, exist_ok=True)

        self.model = None
        self.actual_device = "cpu"
        self.actual_engine = "unknown"
        self._prompt_cache = (None, BASE_PROMPT)  # (dictionary mtime, prompt)

        self._load_engine()

    def _determine_device_and_compute(self):
        """Resolves target device and compute precision."""
        device = self.requested_device
        compute = self.compute_type

        if device == "auto":
            device = "cuda" if self._cuda_available() else "cpu"

        if compute == "auto":
            compute = "float16" if device == "cuda" else "int8"

        return device, compute

    @staticmethod
    def _cuda_available():
        """Checks for a CUDA device via CTranslate2 (a faster-whisper dependency),
        falling back to torch if available. Avoids requiring a full PyTorch
        install just to probe the GPU."""
        try:
            import ctranslate2

            return ctranslate2.get_cuda_device_count() > 0
        except Exception:
            pass
        try:
            import torch

            return torch.cuda.is_available()
        except Exception:
            return False

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

        logger.info(
            f"Loading faster-whisper model '{self.model_size}' [device={device}, compute_type={compute}]"
        )
        self.model = WhisperModel(
            self.model_size, device=device, compute_type=compute, download_root=self.models_dir
        )
        self.actual_device = device
        self.actual_engine = "faster-whisper"
        logger.info(f"faster-whisper '{self.model_size}' loaded successfully on {device} ({compute}).")

    def _load_openai_whisper(self, device):
        import torch
        import whisper

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
        If the text ends with 'cancel that' (ignoring punctuation/case), it finds
        the last full stop BEFORE the cancellation phrase and deletes everything
        after it. 'scratch that' is intentionally NOT a cancellation trigger:
        it is handled by NLPProcessor as a delete-last-word command.
        """
        triggers = [r"cancel that"]
        pattern = r"(?i)\s*(?:" + "|".join(triggers) + r")[.!?]*$"

        match = re.search(pattern, text)
        if not match:
            return text

        base_text = text[: match.start()].strip()
        search_text = re.sub(r"[.!?]+$", "", base_text)
        last_terminator = max(search_text.rfind("."), search_text.rfind("?"), search_text.rfind("!"))

        if last_terminator == -1:
            return ""

        return base_text[: last_terminator + 1].strip()

    def _get_dynamic_prompt(self):
        """Builds the Whisper initial_prompt from the user dictionary.

        The file is re-read only when its mtime changes, so the hot dictation
        path does not hit the disk on every utterance.
        """
        try:
            mtime = os.path.getmtime(DICTIONARY_FILE)
        except OSError:
            self._prompt_cache = (None, BASE_PROMPT)
            return BASE_PROMPT

        cached_mtime, cached_prompt = self._prompt_cache
        if cached_mtime == mtime:
            return cached_prompt

        prompt = BASE_PROMPT
        try:
            with open(DICTIONARY_FILE, encoding="utf-8") as f:
                words = json.load(f)
            if isinstance(words, list) and words:
                suffix = " Please prioritize these specific terms if they match the audio: "
                budget = MAX_PROMPT_CHARS - len(prompt) - len(suffix) - 1
                kept, used = [], 0
                for word in (str(w).strip() for w in words):
                    if not word:
                        continue
                    cost = len(word) + 2
                    if used + cost > budget:
                        logger.warning(
                            "Dictionary truncated to %d of %d terms to fit the Whisper prompt.",
                            len(kept),
                            len(words),
                        )
                        break
                    kept.append(word)
                    used += cost
                if kept:
                    prompt += suffix + ", ".join(kept) + "."
        except Exception as e:
            logger.error(f"Failed to load personal dictionary: {e}")

        self._prompt_cache = (mtime, prompt)
        return prompt

    def transcribe(self, audio_array):
        """Transcribes a 16kHz mono float32 numpy audio array."""
        if audio_array is None or len(audio_array) == 0:
            return ""

        # Whisper expects contiguous mono float32 samples
        audio_array = np.ascontiguousarray(audio_array, dtype=np.float32)

        prompt = self._get_dynamic_prompt()

        if self.actual_engine == "faster-whisper":
            try:
                segments, info = self.model.transcribe(
                    audio_array, initial_prompt=prompt, vad_filter=self.vad_filter, language=self.language
                )
                raw_text = " ".join([seg.text.strip() for seg in segments if seg.text]).strip()
            except Exception as e:
                logger.error(f"faster-whisper transcription error: {e}")
                raw_text = ""
        else:
            try:
                result = self.model.transcribe(
                    audio_array, fp16=False, initial_prompt=prompt, language=self.language
                )
                raw_text = result.get("text", "").strip()
            except Exception as e:
                logger.error(f"openai-whisper transcription error: {e}")
                raw_text = ""

        logger.debug("Transcription completed")
        final_text = self.process_cancellation(raw_text)
        if final_text != raw_text:
            logger.info("Cancelled utterance discarded")

        return final_text
