from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QCheckBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from config import save_config
from shortcut_manager import RebindListener, get_friendly_name

class SettingsDialog(QDialog):
    shortcut_captured_signal = Signal(list)

    def __init__(self, parent, config, on_config_changed_cb):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedSize(340, 260)
        
        self.shortcut_captured_signal.connect(self._apply_shortcut)
        
        self.config = config
        self.on_config_changed_cb = on_config_changed_cb
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Activation Mode:")
        mode_layout.addWidget(mode_label)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Hold to Record", "Toggle (Press to Start/Stop)", "Always-On (Voice Activity Detection)"])
        if self.config.get("activation_mode") == "toggle":
            self.mode_combo.setCurrentIndex(1)
        elif self.config.get("activation_mode") == "always_on":
            self.mode_combo.setCurrentIndex(2)
        else:
            self.mode_combo.setCurrentIndex(0)
            
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        layout.addLayout(mode_layout)
        
        shortcut_label = QLabel("Recording Shortcut:")
        layout.addWidget(shortcut_label)
        
        self.bind_btn = QPushButton(get_friendly_name(self.config.get("shortcut", [])))
        self.bind_btn.clicked.connect(self.on_bind_clicked)
        layout.addWidget(self.bind_btn)
        
        self.help_label = QLabel("")
        self.help_label.setStyleSheet("color: gray;")
        layout.addWidget(self.help_label)
        
        self.chk_boot = QCheckBox("Start Vocara on system boot")
        self.chk_boot.setChecked(self.config.get("start_on_boot", False))
        self.chk_boot.stateChanged.connect(self.on_boot_changed)
        layout.addWidget(self.chk_boot)
        
        self.chk_enter = QCheckBox("Automatically press Enter after dictation")
        self.chk_enter.setChecked(self.config.get("auto_enter", False))
        self.chk_enter.stateChanged.connect(self.on_enter_changed)
        layout.addWidget(self.chk_enter)
        
        self.chk_invis = QCheckBox("Start invisible (Ghost Mode)")
        self.chk_invis.setChecked(self.config.get("start_invisible", False))
        self.chk_invis.stateChanged.connect(self.on_invis_changed)
        layout.addWidget(self.chk_invis)
        
        self.chk_beeps = QCheckBox("Play beep sound when recording starts/stops")
        self.chk_beeps.setChecked(self.config.get("play_beeps", True))
        self.chk_beeps.stateChanged.connect(self.on_beeps_changed)
        layout.addWidget(self.chk_beeps)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        self.rebind_listener = None

    def on_mode_changed(self, index):
        if index == 1:
            self.config["activation_mode"] = "toggle"
        elif index == 2:
            self.config["activation_mode"] = "always_on"
        else:
            self.config["activation_mode"] = "hold"
        save_config(self.config)
        self.on_config_changed_cb(self.config)

    def on_boot_changed(self, state):
        self.config["start_on_boot"] = (state == 2)
        save_config(self.config)
        self.on_config_changed_cb(self.config)

    def on_enter_changed(self, state):
        self.config["auto_enter"] = (state == 2)
        save_config(self.config)
        self.on_config_changed_cb(self.config)

    def on_invis_changed(self, state):
        self.config["start_invisible"] = (state == 2)
        save_config(self.config)
        self.on_config_changed_cb(self.config)

    def on_beeps_changed(self, state):
        self.config["play_beeps"] = (state == 2)
        save_config(self.config)
        self.on_config_changed_cb(self.config)

    def on_bind_clicked(self):
        self.bind_btn.setText("Press combination now...")
        self.help_label.setText("Listening for keyboard/mouse...")
        self.bind_btn.setEnabled(False)
        
        self.rebind_listener = RebindListener(self.on_shortcut_captured)
        self.rebind_listener.start()

    def on_shortcut_captured(self, shortcut):
        self.shortcut_captured_signal.emit(shortcut)

    def _apply_shortcut(self, shortcut):
        self.config["shortcut"] = shortcut
        save_config(self.config)
        self.bind_btn.setText(get_friendly_name(shortcut))
        self.bind_btn.setEnabled(True)
        self.help_label.setText("Shortcut saved!")
        self.on_config_changed_cb(self.config)

    def closeEvent(self, event):
        if self.rebind_listener:
            self.rebind_listener.stop()
        super().closeEvent(event)
