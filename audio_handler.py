import sounddevice as sd
import numpy as np
import queue
import logging
import time
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

class AudioRecorder:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.audio_queue = queue.Queue()
        self.is_recording = False
        self.stream = None

    def _audio_callback(self, indata, frames, time, status):
        if status:
            logger.warning(f"Audio status: {status}")
        if self.is_recording:
            self.audio_queue.put(indata.copy())

    def start_recording(self):
        logger.info("Starting audio recording...")
        self.audio_queue = queue.Queue()
        self.is_recording = True
        
        self.stream = sd.InputStream(
            samplerate=self.sample_rate, 
            channels=1, 
            dtype='float32', 
            callback=self._audio_callback
        )
        self.stream.start()

    def stop_recording(self):
        logger.info("Stopping audio recording...")
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            
        audio_buffer = np.empty((0, 1), dtype=np.float32)
        while not self.audio_queue.empty():
            chunk = self.audio_queue.get()
            audio_buffer = np.append(audio_buffer, chunk, axis=0)
            
        logger.info(f"Recorded {len(audio_buffer)} samples.")
        return audio_buffer.flatten()

    def play_cue(self, cue_type):
        try:
            duration = 0.05 # 50 milliseconds
            freq = 600 if cue_type == "start" else 400
            t = np.linspace(0, duration, int(self.sample_rate * duration), False)
            
            note = np.sin(freq * t * 2 * np.pi)
            
            envelope = np.ones_like(note)
            fade_len = int(len(note) * 0.2)
            envelope[:fade_len] = np.linspace(0, 1, fade_len)
            envelope[-fade_len:] = np.linspace(1, 0, fade_len)
            
            audio = (note * envelope * 0.05).astype(np.float32)
            sd.play(audio, self.sample_rate)
        except Exception as e:
            logger.error(f"Failed to play audio cue: {e}")

class VADThread(QThread):
    phrase_detected = Signal(np.ndarray)
    
    def __init__(self, sample_rate=16000, silence_timeout=2.5, energy_threshold=0.015):
        super().__init__()
        self.sample_rate = sample_rate
        self.silence_timeout = silence_timeout
        self.energy_threshold = energy_threshold
        
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
        self.stream = sd.InputStream(
            samplerate=self.sample_rate, 
            channels=1, 
            dtype='float32', 
            callback=self._audio_callback
        )
        self.stream.start()
        
        while self.is_running:
            try:
                chunk = self.audio_queue.get(timeout=0.1)
                rms = np.sqrt(np.mean(np.square(chunk)))
                
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
                            if len(self.audio_buffer) > self.sample_rate * 0.5:
                                self.phrase_detected.emit(self.audio_buffer.flatten())
                            
                            self.is_speaking = False
                            self.silence_start_time = None
                            self.audio_buffer = np.empty((0, 1), dtype=np.float32)
            except queue.Empty:
                pass
                
        if self.stream:
            self.stream.stop()
            self.stream.close()

    def stop(self):
        self.is_running = False
        self.wait()
