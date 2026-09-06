import logging
import queue
import time

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class AudioRecorder:
    def __init__(self, sample_rate=16000, device_index=None, level_callback=None):
        self.sample_rate = sample_rate
        self.device_index = device_index
        self.level_callback = level_callback
        self.audio_queue = queue.Queue()
        self.is_recording = False
        self.stream = None
        self._chunks = []

    def set_device(self, device_index):
        self.device_index = device_index

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"Audio status: {status}")
        if self.is_recording:
            self.audio_queue.put(indata.copy())
            if self.level_callback:
                rms = float(np.sqrt(np.mean(np.square(indata))))
                # Scale RMS (typical speech is 0.01 - 0.20) to roughly 0.0 - 1.0
                norm_level = min(1.0, max(0.0, rms * 7.0))
                try:
                    self.level_callback(norm_level)
                except Exception:
                    # The VU meter must never break the audio callback
                    pass

    def start_recording(self):
        logger.info(f"Starting audio recording on device={self.device_index}...")
        self.audio_queue = queue.Queue()
        self._chunks = []
        self.is_recording = True

        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=self.device_index,
                callback=self._audio_callback,
            )
            self.stream.start()
        except Exception as e:
            logger.error(f"Failed to open audio input stream: {e}. Retrying default device...")
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=None,
                callback=self._audio_callback,
            )
            self.stream.start()

    def stop_recording(self):
        logger.info("Stopping audio recording...")
        self.is_recording = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        # Drain any chunks still queued by the audio callback
        while True:
            try:
                self._chunks.append(self.audio_queue.get_nowait())
            except queue.Empty:
                break

        audio_buffer = (
            np.concatenate(self._chunks, axis=0) if self._chunks else np.empty((0, 1), dtype=np.float32)
        )
        self._chunks = []

        logger.info(f"Recorded {len(audio_buffer)} samples.")
        return audio_buffer.flatten()

    def play_cue(self, cue_type):
        try:
            playback_sr = 44100
            duration = 0.04  # 40 milliseconds
            freq = 660 if cue_type == "start" else 440
            t = np.linspace(0, duration, int(playback_sr * duration), False)

            note = np.sin(freq * t * 2 * np.pi)
            envelope = np.ones_like(note)
            fade_len = int(len(note) * 0.2)
            envelope[:fade_len] = np.linspace(0, 1, fade_len)
            envelope[-fade_len:] = np.linspace(1, 0, fade_len)

            audio = (note * envelope * 0.04).astype(np.float32)
            sd.play(audio, playback_sr)
        except Exception as e:
            logger.debug(f"Audio cue skipped: {e}")


class VADThread(QThread):
    phrase_detected = Signal(np.ndarray)
    level_updated = Signal(float)

    # Hard cap on a single buffered phrase (seconds). Prevents unbounded memory
    # growth if the energy threshold is set too low for the environment.
    MAX_PHRASE_SECONDS = 60

    def __init__(self, sample_rate=16000, silence_timeout=2.0, energy_threshold=0.015, device_index=None):
        super().__init__()
        self.sample_rate = sample_rate
        self.silence_timeout = silence_timeout
        self.energy_threshold = energy_threshold
        self.device_index = device_index

        self.is_running = False
        self.is_speaking = False
        self.silence_start_time = None
        self._chunks = []
        self._buffered_samples = 0

        self.audio_queue = queue.Queue()
        self.stream = None

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"VAD status: {status}")
        self.audio_queue.put(indata.copy())

    def run(self):
        self.is_running = True
        self._reset_phrase()
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=self.device_index,
                callback=self._audio_callback,
            )
            self.stream.start()
        except Exception as e:
            logger.warning(f"VAD failed on device={self.device_index}: {e}. Retrying default...")
            try:
                self.stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                    device=None,
                    callback=self._audio_callback,
                )
                self.stream.start()
            except Exception as e2:
                logger.error(f"VAD stream open failed: {e2}")
                return

        while self.is_running:
            try:
                chunk = self.audio_queue.get(timeout=0.08)
                rms = float(np.sqrt(np.mean(np.square(chunk))))
                norm_level = min(1.0, max(0.0, rms * 7.0))
                self.level_updated.emit(norm_level)

                if rms > self.energy_threshold:
                    self.is_speaking = True
                    self.silence_start_time = None
                    self._append(chunk)
                elif self.is_speaking:
                    self._append(chunk)

                    if self.silence_start_time is None:
                        self.silence_start_time = time.time()
                    elif time.time() - self.silence_start_time > self.silence_timeout:
                        self._flush_phrase()
            except queue.Empty:
                pass

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass

    def _append(self, chunk):
        """Buffers a chunk, flushing first if the phrase cap would be exceeded."""
        cap = self.sample_rate * self.MAX_PHRASE_SECONDS
        if self._buffered_samples > 0 and self._buffered_samples + len(chunk) > cap:
            logger.warning("VAD phrase exceeded max length; flushing early.")
            self._flush_phrase()
        self._chunks.append(chunk)
        self._buffered_samples += len(chunk)
        # A single chunk alone past the cap (never with real audio block sizes)
        if self._buffered_samples > cap:
            logger.warning("VAD chunk exceeded max phrase length; flushing.")
            self._flush_phrase()

    def _reset_phrase(self):
        self.is_speaking = False
        self.silence_start_time = None
        self._chunks = []
        self._buffered_samples = 0

    def _flush_phrase(self):
        """Emits the buffered phrase if it is long enough to be speech."""
        if self._chunks:
            phrase = np.concatenate(self._chunks, axis=0)
            if len(phrase) > self.sample_rate * 0.4:
                self.phrase_detected.emit(phrase.flatten())
        self._reset_phrase()

    def stop(self):
        self.is_running = False
        self.wait(2000)
