import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from config import load_dictionary, save_dictionary

logger = logging.getLogger(__name__)


class DictionaryDialog(QDialog):
    def __init__(self, parent=None, on_dict_updated_cb=None):
        super().__init__(parent)
        self.on_dict_updated_cb = on_dict_updated_cb
        self.words = load_dictionary()

        self.setWindowTitle("Personal Vocabulary & Jargon")
        self.setFixedSize(480, 520)
        self.setModal(True)

        self.setStyleSheet("""
            QDialog {
                background-color: #121316;
                color: #e4e4e7;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                font-size: 13px;
            }
            QLabel {
                color: #a1a1aa;
            }
            QLabel#titleLabel {
                color: #f4f4f5;
                font-size: 15px;
                font-weight: 600;
            }
            QLabel#descLabel {
                color: #71717a;
                font-size: 12px;
                line-height: 1.4;
            }
            QLineEdit {
                background-color: #1c1d22;
                border: 1px solid #2e3038;
                border-radius: 6px;
                padding: 8px 12px;
                color: #f4f4f5;
                font-size: 13px;
                selection-background-color: #3b82f6;
            }
            QLineEdit:focus {
                border: 1px solid #6366f1;
                background-color: #22232a;
            }
            QListWidget {
                background-color: #18191e;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 6px;
                color: #f4f4f5;
                outline: none;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-radius: 6px;
                margin-bottom: 2px;
            }
            QListWidget::item:hover {
                background-color: #22232a;
            }
            QListWidget::item:selected {
                background-color: #2e303d;
                color: #818cf8;
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
            QPushButton:pressed {
                background-color: #18181b;
            }
            QPushButton#primaryBtn {
                background-color: #4f46e5;
                border: 1px solid #6366f1;
                color: #ffffff;
            }
            QPushButton#primaryBtn:hover {
                background-color: #4338ca;
            }
            QPushButton#dangerBtn {
                background-color: transparent;
                border: 1px solid #7f1d1d;
                color: #f87171;
            }
            QPushButton#dangerBtn:hover {
                background-color: #450a0a;
                border-color: #991b1b;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header_box = QVBoxLayout()
        header_box.setSpacing(4)
        title = QLabel("Personal Vocabulary & Jargon", self)
        title.setObjectName("titleLabel")
        desc = QLabel(
            "Add domain-specific jargon, acronyms, or unique names. Vocara dynamically injects these into Whisper's prompt to dramatically boost recognition accuracy.",
            self,
        )
        desc.setObjectName("descLabel")
        desc.setWordWrap(True)
        header_box.addWidget(title)
        header_box.addWidget(desc)
        layout.addLayout(header_box)

        # Add new word input bar
        add_box = QHBoxLayout()
        add_box.setSpacing(8)
        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Enter word or acronym (e.g. Wayland, PySide6, Docker)...")
        self.input_field.returnPressed.connect(self.add_word)
        add_box.addWidget(self.input_field)

        add_btn = QPushButton("Add Term", self)
        add_btn.setObjectName("primaryBtn")
        add_btn.clicked.connect(self.add_word)
        add_box.addWidget(add_btn)
        layout.addLayout(add_box)

        # Filter / Search bar
        search_box = QHBoxLayout()
        self.search_field = QLineEdit(self)
        self.search_field.setPlaceholderText("Search terms...")
        self.search_field.textChanged.connect(self.filter_terms)
        search_box.addWidget(self.search_field)
        layout.addLayout(search_box)

        # Terms list
        self.list_widget = QListWidget(self)
        layout.addWidget(self.list_widget)

        # Bottom actions
        bottom_box = QHBoxLayout()

        self.count_label = QLabel(f"{len(self.words)} terms registered", self)
        bottom_box.addWidget(self.count_label)
        bottom_box.addStretch()

        del_btn = QPushButton("Delete Selected", self)
        del_btn.clicked.connect(self.delete_selected)
        bottom_box.addWidget(del_btn)

        clear_btn = QPushButton("Clear All", self)
        clear_btn.setObjectName("dangerBtn")
        clear_btn.clicked.connect(self.clear_all)
        bottom_box.addWidget(clear_btn)

        close_btn = QPushButton("Done", self)
        close_btn.setObjectName("primaryBtn")
        close_btn.clicked.connect(self.accept)
        bottom_box.addWidget(close_btn)

        layout.addLayout(bottom_box)

        self.refresh_list()

    def refresh_list(self):
        query = self.search_field.text().strip().lower()
        self.list_widget.clear()
        count = 0
        for word in sorted(self.words, key=lambda s: s.lower()):
            if not query or query in word.lower():
                item = QListWidgetItem(f"•   {word}")
                item.setData(Qt.UserRole, word)
                self.list_widget.addItem(item)
                count += 1
        self.count_label.setText(f"{len(self.words)} terms registered")

    def filter_terms(self, text):
        self.refresh_list()

    def add_word(self):
        raw = self.input_field.text().strip()
        if not raw:
            return

        # Support comma separated additions
        new_terms = [w.strip() for w in raw.split(",") if w.strip()]
        added = False
        for term in new_terms:
            if term not in self.words:
                self.words.append(term)
                added = True

        if added:
            save_dictionary(self.words)
            self.input_field.clear()
            self.refresh_list()
            if self.on_dict_updated_cb:
                self.on_dict_updated_cb(self.words)

    def delete_selected(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            word = item.data(Qt.UserRole)
            if word in self.words:
                self.words.remove(word)
        save_dictionary(self.words)
        self.refresh_list()
        if self.on_dict_updated_cb:
            self.on_dict_updated_cb(self.words)

    def clear_all(self):
        if not self.words:
            return
        reply = QMessageBox.question(
            self,
            "Clear Vocabulary",
            "Are you sure you want to remove all vocabulary terms?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.words = []
            save_dictionary(self.words)
            self.refresh_list()
            if self.on_dict_updated_cb:
                self.on_dict_updated_cb(self.words)
