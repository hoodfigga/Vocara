import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QCheckBox, QTabWidget,
    QWidget, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame
)
from PySide6.QtCore import Qt, Signal
from config import save_config, get_audio_input_devices
from shortcut_manager import RebindListener, get_friendly_name

logger = logging.getLogger(__name__)

class SettingsDialog(QDialog):
    shortcut_captured_signal = Signal(list)

    def __init__(self, parent, config, on_config_changed_cb):
        super().__init__(parent)
        self.config = config.copy()
        self.on_config_changed_cb = on_config_changed_cb
        self.rebind_listener = None

        self.setWindowTitle("Vocara Settings")
        self.setFixedSize(540, 520)
        self.setModal(True)

        self.shortcut_captured_signal.connect(self._apply_shortcut)

        self.setStyleSheet("""
            QDialog {
                background-color: #121316;
                color: #e4e4e7;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 13px;
            }
            QTabWidget::pane {
                border: 1px solid #27272a;
                border-radius: 8px;
                background-color: #18191e;
                top: -1px;
                padding: 12px;
            }
            QTabBar::tab {
                background: #121316;
                color: #a1a1aa;
                padding: 8px 16px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background: #18191e;
                color: #ffffff;
                border: 1px solid #27272a;
                border-bottom: 1px solid #18191e;
            }
            QTabBar::tab:hover:!selected {
                color: #f4f4f5;
                background: #1c1d22;
            }
            QLabel {
                color: #d4d4d8;
            }
            QLabel.helper {
                color: #71717a;
                font-size: 11px;
            }
            QComboBox {
                background-color: #1c1d22;
                border: 1px solid #2e3038;
                border-radius: 6px;
                padding: 6px 12px;
                color: #f4f4f5;
                min-height: 24px;
            }
            QComboBox:hover {
                border-color: #3f3f46;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #1c1d22;
                border: 1px solid #27272a;
                color: #f4f4f5;
                selection-background-color: #312e81;
                selection-color: #ffffff;
                padding: 4px;
            }
            QCheckBox {
                color: #e4e4e7;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #3f3f46;
                background-color: #1c1d22;
            }
            QCheckBox::indicator:checked {
                background-color: #4f46e5;
                border-color: #6366f1;
            }
            QPushButton {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 7px 14px;
                color: #f4f4f5;
                font-weight: 500;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                border-color: #52525b;
            }
            QPushButton#primaryBtn {
                background-color: #4f46e5;
                border: 1px solid #6366f1;
                color: #ffffff;
            }
            QPushButton#primaryBtn:hover {
                background-color: #4338ca;
            }
            QTableWidget {
                background-color: #14151a;
                border: 1px solid #27272a;
                border-radius: 6px;
                gridline-color: #27272a;
                color: #f4f4f5;
            }
            QHeaderView::section {
                background-color: #1c1d22;
                color: #a1a1aa;
                padding: 6px;
                border: none;
                border-bottom: 1px solid #27272a;
                font-weight: 600;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        self.tabs = QTabWidget(self)
        main_layout.addWidget(self.tabs)

        self._build_general_tab()
        self._build_model_tab()
        self._build_audio_tab()
        self._build_commands_tab()

        # Bottom buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        save_btn = QPushButton("Save Changes", self)
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self.save_and_close)
        btn_box.addWidget(save_btn)

        main_layout.addLayout(btn_box)

    def _build_general_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        # Mode
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Hold to Record (Push-to-Talk)", "hold")
        self.mode_combo.addItem("Toggle (Press to Start / Stop)", "toggle")
        self.mode_combo.addItem("Always-On (Voice Activity Detection)", "always_on")
        curr_mode = self.config.get("activation_mode", "hold")
        idx = self.mode_combo.findData(curr_mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        form.addRow("Activation Mode:", self.mode_combo)

        # Shortcut
        shortcut_box = QVBoxLayout()
        self.bind_btn = QPushButton(get_friendly_name(self.config.get("shortcut", [])))
        self.bind_btn.clicked.connect(self.on_bind_clicked)
        self.bind_hint = QLabel("Click to rebind recording trigger", self)
        self.bind_hint.setProperty("class", "helper")
        self.bind_hint.setStyleSheet("color: #71717a; font-size: 11px;")
        shortcut_box.addWidget(self.bind_btn)
        shortcut_box.addWidget(self.bind_hint)
        form.addRow("Trigger Shortcut:", shortcut_box)

        layout.addLayout(form)

        # Checkboxes
        self.chk_enter = QCheckBox("Automatically press Enter after dictation")
        self.chk_enter.setChecked(self.config.get("auto_enter", False))
        layout.addWidget(self.chk_enter)

        self.chk_beeps = QCheckBox("Play subtle audio cues when recording starts / stops")
        self.chk_beeps.setChecked(self.config.get("play_beeps", True))
        layout.addWidget(self.chk_beeps)

        self.chk_boot = QCheckBox("Start Vocara automatically on system boot")
        self.chk_boot.setChecked(self.config.get("start_on_boot", False))
        layout.addWidget(self.chk_boot)

        self.chk_invis = QCheckBox("Start invisible in background (Ghost Mode)")
        self.chk_invis.setChecked(self.config.get("start_invisible", False))
        layout.addWidget(self.chk_invis)

        layout.addStretch()
        self.tabs.addTab(tab, "General")

    def _build_model_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        # Engine
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("faster-whisper (CTranslate2 - 4x Faster)", "faster-whisper")
        self.engine_combo.addItem("openai-whisper (PyTorch Standard)", "openai-whisper")
        curr_engine = self.config.get("engine", "faster-whisper")
        idx = self.engine_combo.findData(curr_engine)
        if idx >= 0:
            self.engine_combo.setCurrentIndex(idx)
        form.addRow("Speech Engine:", self.engine_combo)

        # Model Size
        self.model_combo = QComboBox()
        self.model_combo.addItem("turbo (large-v3-turbo: Best Accuracy & Speed)", "turbo")
        self.model_combo.addItem("base (Lightweight & Instant)", "base")
        self.model_combo.addItem("tiny (Ultra-Fast)", "tiny")
        self.model_combo.addItem("small (Balanced)", "small")
        self.model_combo.addItem("medium (High Accuracy)", "medium")
        self.model_combo.addItem("large-v3 (Maximum Accuracy)", "large-v3")
        curr_model = self.config.get("model_size", "base")
        idx = self.model_combo.findData(curr_model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        form.addRow("Model Size:", self.model_combo)

        # Compute precision
        self.compute_combo = QComboBox()
        self.compute_combo.addItem("Auto (Optimized for Hardware)", "auto")
        self.compute_combo.addItem("int8 (Fastest CPU/Quantized)", "int8")
        self.compute_combo.addItem("float16 (High-Speed GPU)", "float16")
        self.compute_combo.addItem("float32 (Full Precision)", "float32")
        curr_comp = self.config.get("compute_type", "auto")
        idx = self.compute_combo.findData(curr_comp)
        if idx >= 0:
            self.compute_combo.setCurrentIndex(idx)
        form.addRow("Compute Precision:", self.compute_combo)

        # Language
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Auto-Detect (Multilingual)", "")
        self.lang_combo.addItem("English (en)", "en")
        self.lang_combo.addItem("Spanish (es)", "es")
        self.lang_combo.addItem("French (fr)", "fr")
        self.lang_combo.addItem("German (de)", "de")
        self.lang_combo.addItem("Japanese (ja)", "ja")
        self.lang_combo.addItem("Chinese (zh)", "zh")
        curr_lang = self.config.get("language") or ""
        idx = self.lang_combo.findData(curr_lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        form.addRow("Language:", self.lang_combo)

        layout.addLayout(form)

        # VAD filter
        self.chk_vad_filter = QCheckBox("Filter non-speech audio (Silero VAD) to prevent hallucinations")
        self.chk_vad_filter.setChecked(self.config.get("vad_filter", True))
        layout.addWidget(self.chk_vad_filter)

        info_lbl = QLabel("Note: Changing the model or engine will trigger an automatic reload in the background.", self)
        info_lbl.setStyleSheet("color: #71717a; font-size: 11px; margin-top: 8px;")
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        layout.addStretch()
        self.tabs.addTab(tab, "AI Engine")

    def _build_audio_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        self.audio_combo = QComboBox()
        self.refresh_audio_devices()
        form.addRow("Input Microphone:", self.audio_combo)
        layout.addLayout(form)

        refresh_btn = QPushButton("Refresh Devices", self)
        refresh_btn.clicked.connect(self.refresh_audio_devices)
        layout.addWidget(refresh_btn)

        layout.addStretch()
        self.tabs.addTab(tab, "Audio Device")

    def refresh_audio_devices(self):
        self.audio_combo.clear()
        self.audio_combo.addItem("Default System Microphone", None)
        devices = get_audio_input_devices()
        curr_dev = self.config.get("input_device")
        sel_idx = 0
        for i, dev in enumerate(devices):
            label = f"{dev['name']} ({dev['channels']} ch)"
            if dev['is_default']:
                label += " [Default]"
            self.audio_combo.addItem(label, dev['index'])
            if curr_dev is not None and dev['index'] == curr_dev:
                sel_idx = i + 1

        self.audio_combo.setCurrentIndex(sel_idx)

    def _build_commands_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        desc = QLabel("Speak these commands while dictating to trigger formatting, navigation, or app controls:", self)
        desc.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        layout.addWidget(desc)

        table = QTableWidget(self)
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Voice Trigger", "Action Executed"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.NoSelection)

        commands = [
            ("scratch that", "Deletes the preceding word (Ctrl + Backspace)"),
            ("strike line", "Deletes the entire current line"),
            ("undo last", "Executes Undo (Ctrl + Z)"),
            ("select all", "Selects all text (Ctrl + A)"),
            ("save document", "Saves the active document (Ctrl + S)"),
            ("vocara clear", "Clears the recent sentence buffer"),
            ("vocara pause", "Temporarily pauses voice dictation"),
            ("vocara resume", "Resumes active dictation"),
            ("open quote / close quote", "Types quotation marks (\")"),
            ("quote <text> unquote", "Wraps the spoken phrase in quotes"),
            ("open / close bracket", "Types parentheses ( / )"),
            ("cancel that", "Erases the utterance before typing")
        ]

        table.setRowCount(len(commands))
        for row, (cmd, act) in enumerate(commands):
            item_cmd = QTableWidgetItem(cmd)
            item_cmd.setFlags(Qt.ItemIsEnabled)
            item_act = QTableWidgetItem(act)
            item_act.setFlags(Qt.ItemIsEnabled)
            table.setItem(row, 0, item_cmd)
            table.setItem(row, 1, item_act)

        layout.addWidget(table)
        self.tabs.addTab(tab, "Voice Commands")

    def on_bind_clicked(self):
        self.bind_btn.setText("Press combination now...")
        self.bind_hint.setText("Listening for key or mouse button...")
        self.bind_hint.setStyleSheet("color: #f59e0b; font-size: 11px;")
        self.bind_btn.setEnabled(False)

        self.rebind_listener = RebindListener(self.on_shortcut_captured)
        self.rebind_listener.start()

    def on_shortcut_captured(self, shortcut):
        self.shortcut_captured_signal.emit(shortcut)

    def _apply_shortcut(self, shortcut):
        self.config["shortcut"] = shortcut
        self.bind_btn.setText(get_friendly_name(shortcut))
        self.bind_btn.setEnabled(True)
        self.bind_hint.setText("Shortcut recorded successfully!")
        self.bind_hint.setStyleSheet("color: #10b981; font-size: 11px;")

    def save_and_close(self):
        # Update config dictionary
        self.config["activation_mode"] = self.mode_combo.currentData()
        self.config["auto_enter"] = self.chk_enter.isChecked()
        self.config["play_beeps"] = self.chk_beeps.isChecked()
        self.config["start_on_boot"] = self.chk_boot.isChecked()
        self.config["start_invisible"] = self.chk_invis.isChecked()
        
        self.config["engine"] = self.engine_combo.currentData()
        self.config["model_size"] = self.model_combo.currentData()
        self.config["compute_type"] = self.compute_combo.currentData()
        self.config["language"] = self.lang_combo.currentData() or None
        self.config["vad_filter"] = self.chk_vad_filter.isChecked()

        self.config["input_device"] = self.audio_combo.currentData()

        save_config(self.config)
        if self.on_config_changed_cb:
            self.on_config_changed_cb(self.config)
        self.accept()

    def closeEvent(self, event):
        if self.rebind_listener:
            self.rebind_listener.stop()
        super().closeEvent(event)
