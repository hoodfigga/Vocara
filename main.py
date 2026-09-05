import sys
import os
import time
import json
import logging
import platform
import numpy as np

if platform.system() == "Linux":
    os.environ["HSA_OVERRIDE_GFX_VERSION"] = "10.3.0"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("Vocara")

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSystemTrayIcon, QMenu, QDialog, QMessageBox,
    QSizePolicy, QProgressBar, QFrame, QToolTip
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QPoint, QMetaObject, Slot, QRectF
from PySide6.QtGui import QIcon, QAction, QColor, QPainter, QPainterPath, QLinearGradient, QFont, QPen, QClipboard
from PySide6.QtNetwork import QLocalSocket, QLocalServer

from pynput import keyboard

from config import load_config, save_config, update_autostart, load_dictionary
from transcriber import WhisperTranscriber
from audio_handler import AudioRecorder, VADThread
from type_simulator import TypeSimulator
from nlp_processor import NLPProcessor
from shortcut_manager import ShortcutManager, get_friendly_name
from settings_dialog import SettingsDialog
from dictionary_dialog import DictionaryDialog

def is_fullscreen():
    """Checks whether the currently active window is in fullscreen mode."""
    if platform.system() == "Windows":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd: return False
            screen_width = user32.GetSystemMetrics(0)
            screen_height = user32.GetSystemMetrics(1)
            import ctypes.wintypes
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            return (w >= screen_width and h >= screen_height)
        except Exception:
            return False
    elif platform.system() == "Linux":
        try:
            import subprocess
            out = subprocess.check_output(["xprop", "-root", "_NET_ACTIVE_WINDOW"], stderr=subprocess.DEVNULL).decode()
            active_win_id = out.split("#")[1].strip()
            if active_win_id == "0x0": return False
            win_props = subprocess.check_output(["xprop", "-id", active_win_id, "_NET_WM_STATE"], stderr=subprocess.DEVNULL).decode()
            return "_NET_WM_STATE_FULLSCREEN" in win_props
        except Exception:
            return False
    return False

def create_app_icon():
    """Generates a crisp, modern vector-based microphone icon for tray and window."""
    size = 64
    pixmap = QIcon()
    from PySide6.QtGui import QPixmap
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)

    # Rounded mic body
    painter.setBrush(QColor("#6366f1"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(22, 10, 20, 30, 10, 10)

    # Arc stand
    pen = QPen(QColor("#f4f4f5"), 3.5)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawArc(14, 20, 36, 26, 0, -180 * 16)

    # Stem and base
    painter.drawLine(32, 46, 32, 54)
    painter.drawLine(20, 54, 44, 54)
    painter.end()

    return QIcon(pm)

class AudioVUBar(QWidget):
    """Refined, responsive horizontal audio level meter."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0.0
        self.setFixedHeight(6)
        self.setMinimumWidth(80)

        # Smooth decay timer
        self.decay_timer = QTimer(self)
        self.decay_timer.timeout.connect(self._decay)
        self.decay_timer.start(30)

    def set_level(self, val: float):
        # Peak hold with quick rise
        if val > self.level:
            self.level = val
        else:
            self.level = max(0.0, self.level * 0.75 + val * 0.25)
        self.update()

    def _decay(self):
        if self.level > 0.01:
            self.level = max(0.0, self.level - 0.04)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background track
        track_rect = QRectF(0, 0, self.width(), self.height())
        painter.setBrush(QColor("#1f2026"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(track_rect, 3, 3)

        # Active level fill
        if self.level > 0.01:
            fill_width = max(6.0, self.width() * min(1.0, self.level))
            fill_rect = QRectF(0, 0, fill_width, self.height())

            gradient = QLinearGradient(0, 0, self.width(), 0)
            gradient.setColorAt(0.0, QColor("#10b981"))
            gradient.setColorAt(0.7, QColor("#38bdf8"))
            gradient.setColorAt(1.0, QColor("#f43f5e"))

            painter.setBrush(gradient)
            painter.drawRoundedRect(fill_rect, 3, 3)

class ProcessingThread(QThread):
    finished = Signal(str)
    
    def __init__(self, transcriber, audio_array):
        super().__init__()
        self.transcriber = transcriber
        self.audio_array = audio_array
        
    def run(self):
        try:
            text = self.transcriber.transcribe(self.audio_array)
        except Exception as e:
            logger.error(f"Processing thread error: {e}")
            text = ""
        self.finished.emit(text)

class ModelLoaderThread(QThread):
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        try:
            transcriber = WhisperTranscriber(
                model_size=self.config.get("model_size", "base"),
                engine=self.config.get("engine", "faster-whisper"),
                device=self.config.get("device", "auto"),
                compute_type=self.config.get("compute_type", "auto"),
                vad_filter=self.config.get("vad_filter", True),
                language=self.config.get("language")
            )
            self.loaded.emit(transcriber)
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            self.failed.emit(str(e))

class VocaraHUD(QWidget):
    """
    Refined, modern desktop HUD for Vocara.
    Designed with high-density information architecture, subtle borders,
    clear state communication, live audio metering, and quick controls.
    """
    audio_level_signal = Signal(float)

    def __init__(self):
        super().__init__()
        self.config = load_config()

        # Frameless, floating utility window
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(380)

        self.old_pos = None
        self.transcriber = None
        self.is_recording = False
        self.is_suspended = False
        self.is_manually_paused = False
        self.was_visible_before_suspend = False
        self.vad_queue = []
        self.is_processing_vad = False
        self.vad_thread = None
        self.last_transcript = ""

        self.audio_level_signal.connect(self._on_audio_level)

        self.simulator = TypeSimulator()
        self.nlp_engine = NLPProcessor(self.simulator, command_callback=self.on_nlp_command)
        self.recorder = AudioRecorder(
            device_index=self.config.get("input_device"),
            level_callback=lambda lvl: self.audio_level_signal.emit(lvl)
        )

        self._build_ui()
        self._apply_theme()
        self._restore_position()

        # Setup System Tray
        self.setup_tray()

        # Fullscreen detection timer
        self.fullscreen_timer = QTimer(self)
        self.fullscreen_timer.timeout.connect(self._check_fullscreen_status)
        self.fullscreen_timer.start(2000)

        # Global Ghost Mode listener (<ctrl>+<alt>+v)
        self.ghost_listener = keyboard.GlobalHotKeys({
            '<ctrl>+<alt>+v': self.toggle_visibility
        })
        self.ghost_listener.start()

        # Shortcut manager for Push-to-Talk or Toggle
        self.shortcut_manager = ShortcutManager(
            self.config.get("shortcut", []),
            self._handle_ptt,
            is_toggle_mode=(self.config.get("activation_mode") == "toggle")
        )
        self.shortcut_manager.start()

        # Initial model loading
        self.load_engine_model()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        # Main HUD container
        self.container = QWidget(self)
        self.container.setObjectName("hudContainer")
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(16, 14, 16, 14)
        container_layout.setSpacing(10)

        # --- Top Header Bar ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        # Vocara brand mark
        brand_label = QLabel("Vocara", self.container)
        brand_label.setObjectName("brandLabel")
        top_bar.addWidget(brand_label)

        # Engine & Model Pill Badge
        self.model_badge = QLabel("loading engine...", self.container)
        self.model_badge.setObjectName("modelBadge")
        top_bar.addWidget(self.model_badge)

        top_bar.addStretch()

        # Ghost Mode / Hide button
        self.hide_btn = QPushButton("—", self.container)
        self.hide_btn.setObjectName("toolBtn")
        self.hide_btn.setToolTip("Hide to Tray (Ctrl+Alt+V to restore)")
        self.hide_btn.setFocusPolicy(Qt.NoFocus)
        self.hide_btn.clicked.connect(self.hide)
        top_bar.addWidget(self.hide_btn)

        container_layout.addLayout(top_bar)

        # --- Status & Audio VU Meter Bar ---
        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        self.status_dot = QLabel("●", self.container)
        self.status_dot.setObjectName("statusDot")
        status_row.addWidget(self.status_dot)

        self.status_text = QLabel("Initializing AI Engine...", self.container)
        self.status_text.setObjectName("statusText")
        status_row.addWidget(self.status_text)

        status_row.addStretch()

        # Real-time VU meter
        self.vu_bar = AudioVUBar(self.container)
        status_row.addWidget(self.vu_bar)

        container_layout.addLayout(status_row)

        # --- Primary Action Trigger Button ---
        self.action_btn = QPushButton("Preparing...", self.container)
        self.action_btn.setObjectName("actionBtn")
        self.action_btn.setEnabled(False)
        self.action_btn.setFocusPolicy(Qt.NoFocus)
        self.action_btn.clicked.connect(self.on_action_btn_clicked)
        container_layout.addWidget(self.action_btn)

        # --- Live / Last Transcript Banner ---
        self.transcript_frame = QFrame(self.container)
        self.transcript_frame.setObjectName("transcriptFrame")
        transcript_layout = QHBoxLayout(self.transcript_frame)
        transcript_layout.setContentsMargins(10, 6, 8, 6)
        transcript_layout.setSpacing(8)

        self.transcript_label = QLabel("Ready for speech. Transcribed text will appear here.", self.transcript_frame)
        self.transcript_label.setObjectName("transcriptLabel")
        self.transcript_label.setWordWrap(True)
        transcript_layout.addWidget(self.transcript_label, 1)

        self.copy_btn = QPushButton("Copy", self.transcript_frame)
        self.copy_btn.setObjectName("copyBtn")
        self.copy_btn.setToolTip("Copy transcript to clipboard")
        self.copy_btn.setFocusPolicy(Qt.NoFocus)
        self.copy_btn.clicked.connect(self.copy_transcript_to_clipboard)
        transcript_layout.addWidget(self.copy_btn)

        container_layout.addWidget(self.transcript_frame)

        # --- Bottom Action Controls Toolbar ---
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)

        # Pause / Resume Toggle
        self.pause_btn = QPushButton("Pause", self.container)
        self.pause_btn.setObjectName("bottomBtn")
        self.pause_btn.setToolTip("Pause or Resume dictation listening")
        self.pause_btn.setFocusPolicy(Qt.NoFocus)
        self.pause_btn.clicked.connect(self.on_pause_clicked)
        bottom_bar.addWidget(self.pause_btn)

        # Vocabulary / Dictionary Manager
        self.dict_btn = QPushButton("Vocabulary", self.container)
        self.dict_btn.setObjectName("bottomBtn")
        self.dict_btn.setToolTip("Manage custom jargon and acronyms")
        self.dict_btn.setFocusPolicy(Qt.NoFocus)
        self.dict_btn.clicked.connect(self.open_dictionary)
        bottom_bar.addWidget(self.dict_btn)

        # Settings Dialog
        self.settings_btn = QPushButton("Settings", self.container)
        self.settings_btn.setObjectName("bottomBtn")
        self.settings_btn.setToolTip("Configure activation, models, and audio")
        self.settings_btn.setFocusPolicy(Qt.NoFocus)
        self.settings_btn.clicked.connect(self.open_settings)
        bottom_bar.addWidget(self.settings_btn)

        bottom_bar.addStretch()

        # Shortcut badge
        self.shortcut_badge = QLabel(self.container)
        self.shortcut_badge.setObjectName("shortcutBadge")
        self._update_shortcut_badge()
        bottom_bar.addWidget(self.shortcut_badge)

        container_layout.addLayout(bottom_bar)
        root_layout.addWidget(self.container)

    def _apply_theme(self):
        """Applies a clean, modern developer-grade design stylesheet."""
        self.setStyleSheet("""
            QWidget#hudContainer {
                background-color: rgba(18, 19, 22, 240);
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 14px;
            }
            QLabel#brandLabel {
                color: #f4f4f5;
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }
            QLabel#modelBadge {
                color: #818cf8;
                background-color: rgba(99, 102, 241, 0.12);
                border: 1px solid rgba(99, 102, 241, 0.25);
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
            }
            QLabel#statusDot {
                font-size: 12px;
                color: #10b981;
            }
            QLabel#statusText {
                color: #d4d4d8;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton#toolBtn {
                background: transparent;
                border: none;
                color: #71717a;
                font-size: 13px;
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 4px;
            }
            QPushButton#toolBtn:hover {
                background-color: rgba(255, 255, 255, 0.08);
                color: #f4f4f5;
            }
            QPushButton#actionBtn {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                color: #f4f4f5;
                border-radius: 8px;
                padding: 9px 14px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#actionBtn:hover {
                background-color: #3f3f46;
                border-color: #52525b;
            }
            QPushButton#actionBtn:pressed {
                background-color: #18181b;
            }
            QPushButton#actionBtn:disabled {
                color: #71717a;
                border-color: #27272a;
                background-color: #18191e;
            }
            QPushButton#actionBtn.recording {
                background-color: #dc2626;
                border: 1px solid #ef4444;
                color: #ffffff;
            }
            QPushButton#actionBtn.recording:hover {
                background-color: #b91c1c;
            }
            QFrame#transcriptFrame {
                background-color: rgba(28, 29, 34, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 6px;
            }
            QLabel#transcriptLabel {
                color: #a1a1aa;
                font-size: 11px;
                line-height: 1.3;
            }
            QPushButton#copyBtn {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                color: #d4d4d8;
                font-size: 10px;
                font-weight: 600;
                padding: 3px 8px;
            }
            QPushButton#copyBtn:hover {
                background-color: #3f3f46;
                color: #ffffff;
            }
            QPushButton#bottomBtn {
                background-color: rgba(39, 39, 42, 0.6);
                border: 1px solid rgba(63, 63, 70, 0.5);
                border-radius: 6px;
                color: #d4d4d8;
                font-size: 11px;
                font-weight: 500;
                padding: 5px 10px;
            }
            QPushButton#bottomBtn:hover {
                background-color: #3f3f46;
                color: #f4f4f5;
                border-color: #71717a;
            }
            QLabel#shortcutBadge {
                color: #71717a;
                font-size: 10px;
                font-family: monospace;
            }
            QToolTip {
                background-color: #18191e;
                color: #f4f4f5;
                border: 1px solid #27272a;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
        """)

    def _restore_position(self):
        pos = self.config.get("hud_position")
        if pos and isinstance(pos, list) and len(pos) == 2:
            self.move(pos[0], pos[1])
        else:
            # Default to bottom right corner
            screen = QApplication.primaryScreen().geometry()
            self.move(screen.width() - self.width() - 30, screen.height() - 260)

    def _save_position(self):
        self.config["hud_position"] = [self.x(), self.y()]
        save_config(self.config)

    def _update_shortcut_badge(self):
        mode = self.config.get("activation_mode", "hold")
        if mode == "always_on":
            self.shortcut_badge.setText("VAD Active")
        else:
            name = get_friendly_name(self.config.get("shortcut", []))
            self.shortcut_badge.setText(f"[{name}]")

    def load_engine_model(self):
        """Loads or reloads the transcription model in background."""
        self.status_text.setText("Loading AI Engine...")
        self.status_dot.setStyleSheet("color: #f59e0b;")
        self.action_btn.setText("Loading Model...")
        self.action_btn.setEnabled(False)

        self.loader_thread = ModelLoaderThread(self.config)
        self.loader_thread.loaded.connect(self.on_model_loaded)
        self.loader_thread.failed.connect(self.on_model_failed)
        self.loader_thread.start()

    def on_model_loaded(self, transcriber):
        self.transcriber = transcriber
        engine_name = getattr(transcriber, 'actual_engine', self.config.get('engine', 'faster-whisper'))
        device_name = getattr(transcriber, 'actual_device', 'cpu')
        model_name = getattr(transcriber, 'model_size', self.config.get('model_size', 'base'))

        self.model_badge.setText(f"{engine_name} • {model_name} ({device_name})")
        self.status_dot.setStyleSheet("color: #10b981;")
        self.status_text.setText("Ready")

        self._manage_vad_thread()
        self._update_action_button()

    def on_model_failed(self, error_msg):
        self.status_dot.setStyleSheet("color: #ef4444;")
        self.status_text.setText("Engine Error")
        self.action_btn.setText("Engine Failed to Load")
        self.action_btn.setEnabled(False)
        logger.error(f"Engine failed to load: {error_msg}")

    def _update_action_button(self):
        if not self.transcriber:
            return

        if self.is_manually_paused:
            self.action_btn.setText("Dictation Paused")
            self.action_btn.setEnabled(False)
            self.action_btn.setProperty("class", "")
            self.action_btn.setStyle(self.action_btn.style())
            return

        mode = self.config.get("activation_mode", "hold")
        if mode == "always_on":
            self.action_btn.setText("Always-On Listening")
            self.action_btn.setEnabled(False)
            self.action_btn.setProperty("class", "")
        elif self.is_recording:
            self.action_btn.setText("■ Stop & Transcribe")
            self.action_btn.setEnabled(True)
            self.action_btn.setProperty("class", "recording")
        else:
            action_verb = "Press" if mode == "toggle" else "Hold"
            key_name = get_friendly_name(self.config.get("shortcut", []))
            self.action_btn.setText(f"{action_verb} {key_name} to Dictate")
            self.action_btn.setEnabled(True)
            self.action_btn.setProperty("class", "")

        self.action_btn.setStyle(self.action_btn.style())

    @Slot(float)
    def _on_audio_level(self, level: float):
        self.vu_bar.set_level(level)

    def on_nlp_command(self, command_name: str):
        """Displays temporary badge when a voice macro executes."""
        self.status_text.setText(f"⚡ {command_name}")
        self.status_dot.setStyleSheet("color: #818cf8;")
        QTimer.singleShot(2500, self._restore_status_text)

    def _restore_status_text(self):
        if self.is_manually_paused:
            self.status_dot.setStyleSheet("color: #71717a;")
            self.status_text.setText("Paused")
        elif self.is_recording:
            self.status_dot.setStyleSheet("color: #ef4444;")
            self.status_text.setText("Recording...")
        elif self.is_processing_vad:
            self.status_dot.setStyleSheet("color: #f59e0b;")
            self.status_text.setText("Transcribing...")
        else:
            self.status_dot.setStyleSheet("color: #10b981;")
            self.status_text.setText("Ready")

    def on_action_btn_clicked(self):
        if self.is_manually_paused or not self.transcriber:
            return
        if not self.is_recording:
            self.start_dictation()
        else:
            self.stop_dictation()

    def _handle_ptt(self, is_active):
        if getattr(self, 'is_manually_paused', False):
            return
        if is_active:
            QMetaObject.invokeMethod(self, "start_dictation", Qt.QueuedConnection)
        else:
            QMetaObject.invokeMethod(self, "stop_dictation", Qt.QueuedConnection)

    @Slot()
    def start_dictation(self):
        if self.is_recording or not self.transcriber:
            return
        self.is_recording = True
        self.status_dot.setStyleSheet("color: #ef4444;")
        self.status_text.setText("Recording...")
        self._update_action_button()

        if self.config.get("play_beeps", True):
            self.recorder.play_cue("start")
        self.recorder.start_recording()

    @Slot()
    def stop_dictation(self):
        if not self.is_recording:
            return
        self.is_recording = False
        self.status_dot.setStyleSheet("color: #f59e0b;")
        self.status_text.setText("Transcribing...")
        self.action_btn.setText("Processing audio...")
        self.action_btn.setEnabled(False)

        if self.config.get("play_beeps", True):
            self.recorder.play_cue("stop")
        audio_array = self.recorder.stop_recording()

        self.processing_thread = ProcessingThread(self.transcriber, audio_array)
        self.processing_thread.finished.connect(self._on_processing_complete)
        self.processing_thread.start()

    def _on_processing_complete(self, text):
        self.status_dot.setStyleSheet("color: #10b981;")
        self.status_text.setText("Ready")
        self._update_action_button()

        if text:
            self.last_transcript = text
            self.transcript_label.setText(text)
            self.transcript_label.setStyleSheet("color: #f4f4f5; font-size: 11px;")

            def type_and_enter():
                self.nlp_engine.process(text)
                if self.config.get("auto_enter", False) and not self.nlp_engine.is_paused:
                    time.sleep(0.04)
                    from pynput.keyboard import Key
                    self.simulator.keyboard.press(Key.enter)
                    self.simulator.keyboard.release(Key.enter)
                    self.nlp_engine.is_first_word = True

            QTimer.singleShot(80, type_and_enter)
        else:
            self.transcript_label.setText("(No speech detected)")
            self.transcript_label.setStyleSheet("color: #71717a; font-size: 11px;")

        if self.config.get("activation_mode") == "always_on":
            self.is_processing_vad = False
            self._process_next_vad()

    @Slot()
    def on_pause_clicked(self):
        self.is_manually_paused = not self.is_manually_paused
        if self.is_manually_paused:
            self.pause_btn.setText("Resume")
            self.status_dot.setStyleSheet("color: #71717a;")
            self.status_text.setText("App Paused")
        else:
            self.pause_btn.setText("Pause")
            self.status_dot.setStyleSheet("color: #10b981;")
            self.status_text.setText("Ready")

        self._manage_vad_thread()
        self._update_action_button()

    def _manage_vad_thread(self):
        if getattr(self, 'is_manually_paused', False):
            if self.vad_thread and self.vad_thread.isRunning():
                self.vad_thread.stop()
                self.vad_thread = None
            if getattr(self, 'shortcut_manager', None):
                self.shortcut_manager.stop()
            return

        if self.config.get("activation_mode") == "always_on" and not self.is_suspended:
            if not self.vad_thread or not self.vad_thread.isRunning():
                self.vad_thread = VADThread(device_index=self.config.get("input_device"))
                self.vad_thread.phrase_detected.connect(self.on_vad_phrase)
                self.vad_thread.level_updated.connect(self._on_audio_level)
                self.vad_thread.start()
                if getattr(self, 'shortcut_manager', None):
                    self.shortcut_manager.stop()
        else:
            if self.vad_thread and self.vad_thread.isRunning():
                self.vad_thread.stop()
                self.vad_thread = None
            if getattr(self, 'shortcut_manager', None):
                self.shortcut_manager.start()

    @Slot(np.ndarray)
    def on_vad_phrase(self, audio_array):
        if not self.transcriber or self.nlp_engine.is_paused or self.is_manually_paused:
            return
        self.vad_queue.append(audio_array)
        self._process_next_vad()

    def _process_next_vad(self):
        if self.is_processing_vad or not self.vad_queue:
            return
        self.is_processing_vad = True
        audio_array = self.vad_queue.pop(0)

        self.status_dot.setStyleSheet("color: #f59e0b;")
        self.status_text.setText("Transcribing speech...")

        self.processing_thread = ProcessingThread(self.transcriber, audio_array)
        self.processing_thread.finished.connect(self._on_processing_complete)
        self.processing_thread.start()

    @Slot()
    def _check_fullscreen_status(self):
        if self.config.get("activation_mode") != "always_on":
            return
        is_fs = is_fullscreen()
        if is_fs and not self.is_suspended:
            self.is_suspended = True
            if self.isVisible():
                self.was_visible_before_suspend = True
                self.hide()
            self._manage_vad_thread()
            self.status_dot.setStyleSheet("color: #52525b;")
            self.status_text.setText("Suspended (Fullscreen)")
        elif not is_fs and self.is_suspended:
            self.is_suspended = False
            self._manage_vad_thread()
            self.status_dot.setStyleSheet("color: #10b981;")
            self.status_text.setText("Ready")
            if getattr(self, 'was_visible_before_suspend', False):
                self.show()
                self.was_visible_before_suspend = False

    def copy_transcript_to_clipboard(self):
        if self.last_transcript:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.last_transcript)
            orig_text = self.copy_btn.text()
            self.copy_btn.setText("Copied!")
            QTimer.singleShot(1500, lambda: self.copy_btn.setText(orig_text))

    def open_dictionary(self):
        dialog = DictionaryDialog(self, on_dict_updated_cb=self.on_dictionary_updated)
        dialog.exec()

    def on_dictionary_updated(self, words):
        logger.info(f"Personal vocabulary updated: {len(words)} terms registered.")

    def open_settings(self):
        dialog = SettingsDialog(self, self.config, self.on_config_changed)
        dialog.exec()

    def on_config_changed(self, new_config):
        old_engine = self.config.get("engine")
        old_model = self.config.get("model_size")
        old_compute = self.config.get("compute_type")
        old_device = self.config.get("device")
        old_input = self.config.get("input_device")

        self.config = new_config
        self.recorder.set_device(self.config.get("input_device"))

        self.shortcut_manager.update_config(
            self.config.get("shortcut", []),
            (self.config.get("activation_mode") == "toggle")
        )
        self._update_shortcut_badge()
        update_autostart(self.config.get("start_on_boot", False))

        # Check if engine parameters changed and reload model if necessary
        model_changed = (
            old_engine != self.config.get("engine") or
            old_model != self.config.get("model_size") or
            old_compute != self.config.get("compute_type") or
            old_device != self.config.get("device")
        )

        if model_changed:
            self.load_engine_model()
        else:
            self._manage_vad_thread()
            self._update_action_button()

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(create_app_icon())

        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background-color: #18191e;
                border: 1px solid #27272a;
                color: #f4f4f5;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 14px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #312e81;
                color: #ffffff;
            }
        """)

        toggle_action = QAction("Show / Hide Vocara", self)
        toggle_action.triggered.connect(self.toggle_visibility)
        tray_menu.addAction(toggle_action)

        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self.open_settings)
        tray_menu.addAction(settings_action)

        dict_action = QAction("Vocabulary...", self)
        dict_action.triggered.connect(self.open_dictionary)
        tray_menu.addAction(dict_action)

        tray_menu.addSeparator()

        quit_action = QAction("Quit Vocara", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_visibility()

    def toggle_visibility(self):
        QMetaObject.invokeMethod(self, "_do_toggle_visibility", Qt.QueuedConnection)

    @Slot()
    def _do_toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()

    # --- Frameless Dragging and Moving ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        if self.old_pos is not None:
            self.old_pos = None
            self._save_position()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setWindowIcon(create_app_icon())

    # Enforce single instance
    socket = QLocalSocket()
    socket.connectToServer("VocaraSingleInstance")
    if socket.waitForConnected(400):
        logger.info("Another instance of Vocara is already running.")
        sys.exit(0)

    # Clean up any stale pipe from previous abnormal exit (critical on Windows)
    QLocalServer.removeServer("VocaraSingleInstance")
    server = QLocalServer()
    server.listen("VocaraSingleInstance")
    app.setQuitOnLastWindowClosed(False)

    window = VocaraHUD()
    update_autostart(window.config.get("start_on_boot", False))

    if window.config.get("start_invisible", False):
        window.hide()
    else:
        window.show()

    sys.exit(app.exec())
