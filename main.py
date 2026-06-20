import sys
import os

# --- PyInstaller Hidden Stdlib Imports ---
import argparse, ast, asyncio, base64, bisect, bz2, calendar, collections, concurrent
import contextlib, contextvars, copy, copyreg, csv, ctypes, dataclasses, datetime
import difflib, dis, email, enum, fnmatch, gettext, glob, gzip, hashlib, heapq, hmac
import html, http, importlib, inspect, ipaddress, json, linecache, locale, logging
import lzma, mmap, multiprocessing, ntpath, numbers, opcode, pathlib, pickle
import pickletools, pkgutil, platform, pprint, queue, quopri, random, re, runpy
import secrets, selectors, shutil, signal, socket, ssl, string, struct, subprocess
import tarfile, tempfile, textwrap, timeit, token, tokenize, traceback, typing
import unittest, urllib, uuid, warnings, weakref, zipfile
# ------------------------------------------
os.environ["HSA_OVERRIDE_GFX_VERSION"] = "10.3.0"

import logging
import threading
import time
from pynput import keyboard

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSystemTrayIcon, QMenu, QDialog, QTextEdit, QMessageBox, QLineEdit,
    QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QPoint, QMetaObject, Slot
from PySide6.QtGui import QIcon, QAction, QColor, QPainter, QPixmap
from PySide6.QtNetwork import QLocalSocket, QLocalServer

import sys
import os
import time
import uuid
import json
import urllib.request
import urllib.error
import hashlib
import numpy as np
import platform

def is_fullscreen():
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
        except:
            return False
    elif platform.system() == "Linux":
        try:
            import subprocess
            active_win_id = subprocess.check_output(["xprop", "-root", "_NET_ACTIVE_WINDOW"], stderr=subprocess.DEVNULL).decode().split("#")[1].strip()
            if active_win_id == "0x0": return False
            
            win_props = subprocess.check_output(["xprop", "-id", active_win_id, "_NET_WM_STATE"], stderr=subprocess.DEVNULL).decode()
            return "_NET_WM_STATE_FULLSCREEN" in win_props
        except:
            return False
    return False

class ProcessingThread(QThread):
    finished = Signal(str)
    
    def __init__(self, transcriber, audio_array):
        super().__init__()
        self.transcriber = transcriber
        self.audio_array = audio_array
        
    def run(self):
        text = self.transcriber.transcribe(self.audio_array)
        self.finished.emit(text)

class ModelLoaderThread(QThread):
    loaded = Signal(object)
    
    def run(self):
        transcriber = WhisperTranscriber(model_size="base")
        self.loaded.emit(transcriber)

class VocaraWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setFixedSize(320, 180)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        
        self.container = QWidget()
        self.container.setObjectName("mainContainer")
        
        current_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        self.icon_path = lambda name: os.path.join(current_dir, "assets", f"{name}.png").replace("\\", "/")
        self.container.setStyleSheet("""
            QWidget#mainContainer {
                background-color: rgba(25, 25, 30, 200);
                border-radius: 20px;
                border: 1px solid #87CEEB;
            }
            QLabel { color: #87CEEB; font-weight: bold; }
            QPushButton {
                background-color: rgba(59, 59, 59, 150);
                color: #87CEEB;
                border-radius: 6px;
                padding: 6px;
                border: 1px solid rgba(135, 206, 235, 0.5);
                icon-size: 24px;
            }
            QPushButton:hover { background-color: rgba(75, 75, 75, 200); }
            QPushButton:disabled { color: gray; border: 1px solid #555; }
        """)
        
        container_layout = QVBoxLayout(self.container)
        container_layout.setSpacing(10)
        
        self.status_label = QLabel("Loading AI Model...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        container_layout.addWidget(self.status_label)
        
        self.toggle_btn = QPushButton("Wait...")
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.setFocusPolicy(Qt.NoFocus)
        self.toggle_btn.clicked.connect(self.on_toggle_clicked)
        self.toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        container_layout.addWidget(self.toggle_btn)
        
        control_box = QHBoxLayout()
        control_box.setAlignment(Qt.AlignCenter)
        
        self.pause_btn = QPushButton("")
        self.pause_btn.setIcon(QIcon(self.icon_path("btn_pause")))
        self.pause_btn.setToolTip("Pause App")
        self.pause_btn.setFocusPolicy(Qt.NoFocus)
        self.pause_btn.clicked.connect(self.on_pause_clicked)
        control_box.addWidget(self.pause_btn)
        
        self.settings_btn = QPushButton("")
        self.settings_btn.setIcon(QIcon(self.icon_path("btn_settings")))
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setFocusPolicy(Qt.NoFocus)
        self.settings_btn.clicked.connect(self.on_settings_clicked)
        control_box.addWidget(self.settings_btn)
        
        self.dict_btn = QPushButton("")
        self.dict_btn.setIcon(QIcon(self.icon_path("btn_dict")))
        self.dict_btn.setToolTip("Edit Personal Dictionary")
        self.dict_btn.setFocusPolicy(Qt.NoFocus)
        self.dict_btn.clicked.connect(self.on_dict_clicked)
        control_box.addWidget(self.dict_btn)
        
        self.hide_btn = QPushButton("")
        self.hide_btn.setIcon(QIcon(self.icon_path("btn_hide")))
        self.hide_btn.setToolTip("Hide Interface (Ghost Mode)")
        self.hide_btn.setFocusPolicy(Qt.NoFocus)
        self.hide_btn.clicked.connect(self.hide)
        control_box.addWidget(self.hide_btn)
        
        container_layout.addLayout(control_box)
        
        self.shortcut_label = QLabel()
        self.shortcut_label.setAlignment(Qt.AlignCenter)
        self.shortcut_label.setStyleSheet("color: #aaaaaa;")
        self.shortcut_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._update_shortcut_label()
        container_layout.addWidget(self.shortcut_label)
        
        self.layout.addWidget(self.container)
        
        self.recorder = AudioRecorder()
        self.vad_thread = None
        self.transcriber = None
        self.simulator = TypeSimulator()
        self.nlp_engine = NLPProcessor(self.simulator)
        
        self.vad_queue = []
        self.is_processing_vad = False
        self.is_recording = False
        self.is_suspended = False
        self.is_manually_paused = False
        self.was_visible_before_suspend = False
        
        self.fullscreen_timer = QTimer(self)
        self.fullscreen_timer.timeout.connect(self._check_fullscreen_status)
        self.fullscreen_timer.start(2000)
        
        self.loader_thread = ModelLoaderThread()
        self.loader_thread.loaded.connect(self.on_model_loaded)
        self.loader_thread.start()
        
        self.shortcut_manager = ShortcutManager(
            self.config.get("shortcut", []), 
            self._handle_ptt,
            is_toggle_mode=(self.config.get("activation_mode") == "toggle")
        )
        self.shortcut_manager.start()
        
        self.ghost_listener = keyboard.GlobalHotKeys({
            '<ctrl>+<alt>+v': self.toggle_visibility
        })
        self.ghost_listener.start()
        
        self.old_pos = None
        
        self.setup_tray()
        
    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(create_mic_icon())
        
        tray_menu = QMenu()
        toggle_action = QAction("Toggle Vocara Window", self)
        toggle_action.triggered.connect(self.toggle_visibility)
        tray_menu.addAction(toggle_action)
        
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

    def on_model_loaded(self, transcriber):
        self.transcriber = transcriber
        self.status_label.setText('<span style="color: #87CEEB; font-size: 20px; font-weight: 800; letter-spacing: 2px;">Vocara</span>')
        self._manage_vad_thread()
        self._update_shortcut_label()
        
        action = "Toggle" if self.config.get("activation_mode") == "toggle" else "Hold"
        if self.config.get("activation_mode") == "always_on":
            self.toggle_btn.setText("Always-On Active")
            self.toggle_btn.setEnabled(False)
        else:
            self.toggle_btn.setText(f"{action} to Record")
            self.toggle_btn.setEnabled(True)

    @Slot()
    def on_pause_clicked(self):
        self.is_manually_paused = not self.is_manually_paused
        if self.is_manually_paused:
            self.pause_btn.setIcon(QIcon(self.icon_path("btn_play")))
            self.pause_btn.setToolTip("Resume App")
            self.toggle_btn.setEnabled(False)
        else:
            self.pause_btn.setIcon(QIcon(self.icon_path("btn_pause")))
            self.pause_btn.setToolTip("Pause App")
            if self.config.get("activation_mode") != "always_on":
                self.toggle_btn.setEnabled(True)
        self._manage_vad_thread()
        self._update_shortcut_label()

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
                self.vad_thread = VADThread()
                self.vad_thread.phrase_detected.connect(self.on_vad_phrase)
                self.vad_thread.start()
                if getattr(self, 'shortcut_manager', None):
                    self.shortcut_manager.stop() # Disable hotkeys
        else:
            if self.vad_thread and self.vad_thread.isRunning():
                self.vad_thread.stop()
                self.vad_thread = None
            if getattr(self, 'shortcut_manager', None):
                self.shortcut_manager.start() # Re-enable hotkeys

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
            else:
                self.was_visible_before_suspend = False
            self._manage_vad_thread()
            self._update_shortcut_label()
        elif not is_fs and self.is_suspended:
            self.is_suspended = False
            if self.transcriber:
                self._manage_vad_thread()
                self._update_shortcut_label()
            if getattr(self, 'was_visible_before_suspend', False):
                self.show()
                self.was_visible_before_suspend = False

    @Slot(np.ndarray)
    def on_vad_phrase(self, audio_array):
        if not self.transcriber or self.nlp_engine.is_paused:
            return
            
        self.vad_queue.append(audio_array)
        self._process_next_vad()

    def _process_next_vad(self):
        if self.is_processing_vad or not self.vad_queue:
            return
            
        self.is_processing_vad = True
        audio_array = self.vad_queue.pop(0)
        self.shortcut_label.setText(f'VAD Mode: <img src="{self.icon_path("status_processing")}" width="24" height="24" align="middle"> Processing...')
        
        if not hasattr(self, 'old_threads'):
            self.old_threads = []
        if getattr(self, 'processing_thread', None) is not None:
            self.old_threads.append(self.processing_thread)
            
        self.old_threads = [t for t in self.old_threads if t.isRunning()]
        
        self.processing_thread = ProcessingThread(self.transcriber, audio_array)
        self.processing_thread.finished.connect(self._on_processing_complete)
        self.processing_thread.start()

    def _update_shortcut_label(self):
        if getattr(self, 'is_manually_paused', False):
            self.shortcut_label.setText(f'VAD Mode: <img src="{self.icon_path("status_idle")}" width="24" height="24" align="middle"> App Paused')
            return
            
        if self.config.get("activation_mode") == "always_on":
            if getattr(self, 'is_suspended', False):
                self.shortcut_label.setText(f'VAD Mode: <img src="{self.icon_path("status_idle")}" width="24" height="24" align="middle"> Suspended')
            elif getattr(self, 'nlp_engine', None) and getattr(self.nlp_engine, 'is_paused', False):
                self.shortcut_label.setText(f'VAD Mode: <img src="{self.icon_path("status_idle")}" width="24" height="24" align="middle"> Paused')
            else:
                self.shortcut_label.setText(f'VAD Mode: <img src="{self.icon_path("status_listening")}" width="24" height="24" align="middle"> Listening...')
        else:
            action = "Press" if self.config.get("activation_mode") == "toggle" else "Hold"
            key_name = get_friendly_name(self.config.get("shortcut", []))
            self.shortcut_label.setText(f"{action} {key_name} to Record")

    def on_settings_clicked(self):
        dialog = SettingsDialog(self, self.config, self.on_config_changed)
        dialog.exec()

    def on_config_changed(self, new_config):
        self.config = new_config
        self.shortcut_manager.update_config(
            self.config.get("shortcut", []),
            (self.config.get("activation_mode") == "toggle")
        )
        self._update_shortcut_label()
        update_autostart(self.config.get("start_on_boot", False))
        if self.transcriber:
            self._manage_vad_thread()
            
            if self.config.get("activation_mode") == "always_on":
                self.toggle_btn.setText("Always-On Active")
                self.toggle_btn.setEnabled(False)
            else:
                action = "Toggle" if self.config.get("activation_mode") == "toggle" else "Hold"
                self.toggle_btn.setText(f"{action} to Record")
                self.toggle_btn.setEnabled(True)

    def on_dict_clicked(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Personal Dictionary")
        dialog.setFixedSize(300, 200)
        
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Add custom jargon, comma separated:"))
        
        text_edit = QTextEdit()
        words = load_dictionary()
        text_edit.setText(", ".join(words))
        layout.addWidget(text_edit)
        
        btn_box = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(lambda: self.save_dict(dialog, text_edit.toPlainText()))
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(save_btn)
        layout.addLayout(btn_box)
        
        dialog.exec()

    def save_dict(self, dialog, text):
        words = [w.strip() for w in text.split(",") if w.strip()]
        save_dictionary(words)
        dialog.accept()

    def _handle_ptt(self, is_active):
        if getattr(self, 'is_manually_paused', False):
            return
            
        if is_active:
            QMetaObject.invokeMethod(self, "start_dictation", Qt.QueuedConnection)
        else:
            QMetaObject.invokeMethod(self, "stop_dictation", Qt.QueuedConnection)

    @Slot()
    def on_toggle_clicked(self):
        if getattr(self, 'is_manually_paused', False):
            return
            
        if not self.is_recording:
            self.start_dictation()
        else:
            self.stop_dictation()

    @Slot()
    def start_dictation(self):
        if self.is_recording or not self.transcriber: return
        self.is_recording = True
        self.recorder.start_recording()
        self.shortcut_label.setText(f'VAD Mode: <img src="{self.icon_path("status_listening")}" width="24" height="24" align="middle"> Recording...')
        self.toggle_btn.setText("Stop to Type")
        self.toggle_btn.setStyleSheet("background-color: #aa3333; color: white;")
        
        if self.config.get("play_beeps", True):
            self.recorder.play_cue("start")
        self.recorder.start_recording()

    @Slot()
    def stop_dictation(self):
        if not self.is_recording: return
        self.shortcut_label.setText(f'VAD Mode: <img src="{self.icon_path("status_processing")}" width="24" height="24" align="middle"> Processing...')
        self.toggle_btn.setText("Wait...")
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.setStyleSheet("")
        
        if self.config.get("play_beeps", True):
            self.recorder.play_cue("stop")
        self.is_recording = False
        audio_array = self.recorder.stop_recording()
        
        from pynput.mouse import Controller as MouseController, Button as MouseButton
        mouse_ctrl = MouseController()
        mouse_ctrl.click(MouseButton.left, 1)
        
        if not hasattr(self, 'old_threads'):
            self.old_threads = []
        if getattr(self, 'processing_thread', None) is not None:
            self.old_threads.append(self.processing_thread)
            
        self.old_threads = [t for t in self.old_threads if t.isRunning()]
        
        self.processing_thread = ProcessingThread(self.transcriber, audio_array)
        self.processing_thread.finished.connect(self._on_processing_complete)
        self.processing_thread.start()

    def _on_processing_complete(self, text):
        if text:
            def type_and_enter():
                self.nlp_engine.process(text)
                if self.config.get("auto_enter", False) and not self.nlp_engine.is_paused:
                    time.sleep(0.05)
                    from pynput.keyboard import Key
                    self.simulator.keyboard.press(Key.enter)
                    self.simulator.keyboard.release(Key.enter)
                    self.nlp_engine.is_first_word = True # Reset spacing after enter
                    
                if self.config.get("activation_mode") == "always_on":
                    self._update_shortcut_label()
                    
            QTimer.singleShot(100, type_and_enter)
            
        self._update_shortcut_label()
        
        if self.config.get("activation_mode") != "always_on":
            action = "Toggle" if self.config.get("activation_mode") == "toggle" else "Hold"
            self.toggle_btn.setText(f"{action} to Record")
            self.toggle_btn.setEnabled(True)
        else:
            self.is_processing_vad = False
            self._process_next_vad()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    socket = QLocalSocket()
    socket.connectToServer("VocaraSingleInstance")
    if socket.waitForConnected(500):
        sys.exit(0)
    
    server = QLocalServer()
    server.listen("VocaraSingleInstance")
    
    app.setQuitOnLastWindowClosed(False) # Prevents closing when invisible
    
    # --- ML Engine Downloader Logic ---
    if platform.system() == "Windows":
        engine_dir = os.path.join(os.getenv('LOCALAPPDATA', os.path.expanduser('~')), 'Vocara', 'Engine')
    else:
        engine_dir = os.path.join(os.path.expanduser('~'), '.local', 'share', 'Vocara', 'Engine')
        
    engine_ready_file = os.path.join(engine_dir, 'engine_ready.txt')
    
    if not os.path.exists(engine_ready_file):
        import shutil
        if os.path.exists(engine_dir):
            shutil.rmtree(engine_dir, ignore_errors=True)
        os.makedirs(engine_dir, exist_ok=True)
        
        from downloader import DownloaderDialog
        dl_dialog = DownloaderDialog(engine_dir)
        dl_dialog.start_download()
        if dl_dialog.exec() != QDialog.Accepted:
            sys.exit(0)
            
        with open(engine_ready_file, 'w') as f:
            f.write("ready")
            
    sys.path.insert(0, engine_dir)
    # ----------------------------------
    
    
    window = VocaraWindow()
    update_autostart(window.config.get("start_on_boot", False))
    
    if window.config.get("start_invisible", False):
        window.hide()
    else:
        window.show()
    
    sys.exit(app.exec())
