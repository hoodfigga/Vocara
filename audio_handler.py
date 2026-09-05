import sounddevice as sd
import numpy as np
import queue
import logging
import time
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
                    pass

    def start_recording(self):
        logger.info(f"Starting audio recording on device={self.device_index}...")
        self.audio_queue = queue.Queue()
        self.is_recording = True
        
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate, 
                channels=1, 
                dtype='float32', 
                device=self.device_index,
                callback=self._audio_callback
            )
            self.stream.start()
        except Exception as e:
            logger.error(f"Failed to open audio input stream: {e}. Retrying default device...")
            self.stream = sd.InputStream(
                samplerate=self.sample_rate, 
                channels=1, 
                dtype='float32', 
                device=None,
                callback=self._audio_callback
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
            
        audio_buffer = np.empty((0, 1), dtype=np.float32)
        while not self.audio_queue.empty():
            try:
                chunk = self.audio_queue.get_nowait()
                audio_buffer = np.append(audio_buffer, chunk, axis=0)
            except queue.Empty:
                break
            
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
    
    def __init__(self, sample_rate=16000, silence_timeout=2.0, energy_threshold=0.015, device_index=None):
        super().__init__()
        self.sample_rate = sample_rate
        self.silence_timeout = silence_timeout
        self.energy_threshold = energy_threshold
        self.device_index = device_index
        
        self.is_running = False
        self.is_speaking = False
        self.silence_start_time = None
        self.audio_buffer = np.empty((0, 1), dtype=np.float32)
        
        self.audio_queue = queue.Queue()
        self.stream = None

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"VAD status: {status}")
        self.audio_queue.put(indata.copy())

    def run(self):
        self.is_running = True
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate, 
                channels=1, 
                dtype='float32', 
                device=self.device_index,
                callback=self._audio_callback
            )
            self.stream.start()
        except Exception as e:
            logger.warning(f"VAD failed on device={self.device_index}: {e}. Retrying default...")
            try:
                self.stream = sd.InputStream(
                    samplerate=self.sample_rate, 
                    channels=1, 
                    dtype='float32', 
                    device=None,
                    callback=self._audio_callback
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
                    self.audio_buffer = np.append(self.audio_buffer, chunk, axis=0)
                else:
                    if self.is_speaking:
                        self.audio_buffer = np.append(self.audio_buffer, chunk, axis=0)
                        
                        if self.silence_start_time is None:
                            self.silence_start_time = time.time()
                        elif time.time() - self.silence_start_time > self.silence_timeout:
                            if len(self.audio_buffer) > self.sample_rate * 0.4:
                                self.phrase_detected.emit(self.audio_buffer.flatten())
                            
                            self.is_speaking = False
                            self.silence_start_time = None
                            self.audio_buffer = np.empty((0, 1), dtype=np.float32)
            except queue.Empty:
                pass
                
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass

    def stop(self):
        self.is_running = False
        self.wait(1000)
