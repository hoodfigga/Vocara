import sys
import os
import platform
import subprocess
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QProgressBar
from PySide6.QtCore import QThread, Signal, Qt

class PipStream:
    def __init__(self, signal):
        self.signal = signal

    def write(self, text):
        if text.strip():
            self.signal.emit(text.strip())
            
    def flush(self):
        pass

class DownloadThread(QThread):
    progress_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, engine_dir):
        super().__init__()
        self.engine_dir = engine_dir

    def run(self):
        try:
            from pip._internal.cli.main import main as pip_main
            
            index_url = None
            if platform.system() == "Windows":
                index_url = "https://download.pytorch.org/whl/cu118"
            elif platform.system() == "Linux":
                try:
                    lspci = subprocess.check_output("lspci", shell=True).decode().lower()
                    if "amd" in lspci and "vga" in lspci:
                        index_url = "https://download.pytorch.org/whl/rocm5.6"
                    else:
                        index_url = "https://download.pytorch.org/whl/cu118"
                except:
                    pass
            
            pip_args = [
                'install',
                '--target', self.engine_dir,
                '--upgrade',
                '--no-color',
                '--progress-bar', 'off',
                'torch', 'torchvision', 'torchaudio',
                'openai-whisper', 'numpy<2.0.0'
            ]
            
            if index_url:
                pip_args.extend(['--extra-index-url', index_url])
            else:
                pip_args.extend(['--extra-index-url', 'https://download.pytorch.org/whl/cpu'])

            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = PipStream(self.progress_signal)
            sys.stderr = PipStream(self.progress_signal)

            self.progress_signal.emit(f"Downloading ML Engine to {self.engine_dir}...")
            exit_code = pip_main(pip_args)
            
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
            self.finished_signal.emit(exit_code == 0)
        except Exception as e:
            self.progress_signal.emit(f"Error: {str(e)}")
            self.finished_signal.emit(False)

class DownloaderDialog(QDialog):
    def __init__(self, engine_dir, parent=None):
        super().__init__(parent)
        self.engine_dir = engine_dir
        self.setWindowTitle("Downloading AI Engine")
        self.setFixedSize(600, 300)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)
        
        layout = QVBoxLayout(self)
        
        self.info_label = QLabel("Downloading dependencies...")
        self.info_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.info_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(10)
        layout.addWidget(self.progress_bar)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: black; color: #00ff00; font-family: monospace; font-size: 11px;")
        layout.addWidget(self.log_view)
        
        self.thread = DownloadThread(self.engine_dir)
        self.thread.progress_signal.connect(self.update_log)
        self.thread.finished_signal.connect(self.on_finished)
        
    def start_download(self):
        self.thread.start()
        
    def update_log(self, text):
        self.log_view.append(text)
        
        lower_text = text.lower()
        if "collecting torch" in lower_text or "downloading torch" in lower_text:
            self.progress_bar.setValue(10)
        elif "collecting triton" in lower_text or "downloading triton" in lower_text:
            self.progress_bar.setValue(40)
        elif "collecting openai-whisper" in lower_text:
            self.progress_bar.setValue(60)
        elif "installing collected packages:" in lower_text:
            self.progress_bar.setValue(85)
        elif "successfully installed" in lower_text:
            self.progress_bar.setValue(100)
            
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def on_finished(self, success):
        if success:
            self.accept()
        else:
            self.info_label.setText("Download failed! Please check your internet connection.")
            self.info_label.setStyleSheet("color: red;")
