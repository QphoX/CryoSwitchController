"""Firmware update popup: pick an image file, then Update or Cancel.

Standalone on purpose: it knows nothing about the board. The caller passes ``on_update(path)``,
which does the actual work (e.g. ``Cryoswitch.update_firmware``). If it raises, the error is
shown and the dialog stays open; if it returns, the dialog closes.

Usage:
    from Updator.firmware_update_window import show_firmware_update_window
    path = show_firmware_update_window(on_update=my_function)   # None if cancelled

Embedding in an existing PyQt5 app: create ``FirmwareUpdateWindow(on_update, parent=self)``
and call ``.exec_()``.
"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class FirmwareUpdateWindow(QDialog):
    def __init__(self, on_update, start_dir=None, file_filter="Firmware image (*.bin);;All files (*)",
                 parent=None):
        super().__init__(parent)
        self.on_update = on_update
        self.start_dir = start_dir or os.getcwd()
        self.file_filter = file_filter
        self.image_path = None  # set once a file is chosen

        self.setWindowTitle("Firmware update")
        self.setMinimumWidth(500)

        self.path_edit = QLineEdit(self)
        self.path_edit.setPlaceholderText("Select a firmware image...")
        self.path_edit.textChanged.connect(self._path_changed)
        browse_button = QPushButton("Browse...", self)
        browse_button.clicked.connect(self._browse)

        self.update_button = QPushButton("Update", self)
        self.update_button.setEnabled(False)
        self.update_button.setDefault(True)
        self.update_button.clicked.connect(self._update)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)

        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse_button)
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.update_button)
        button_row.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Firmware image:", self))
        layout.addLayout(path_row)
        layout.addLayout(button_row)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select firmware image", self.start_dir, self.file_filter)
        if path:
            self.path_edit.setText(os.path.normpath(path))

    def _path_changed(self, text):
        path = text.strip()
        self.image_path = path if os.path.isfile(path) else None
        self.update_button.setEnabled(self.image_path is not None)

    def _update(self):
        self.update_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        QApplication.processEvents()
        try:
            self.on_update(self.image_path)
        except Exception as error:
            QMessageBox.critical(self, "Firmware update failed", str(error))
            self.update_button.setEnabled(True)
            self.cancel_button.setEnabled(True)
            return
        self.accept()


def show_firmware_update_window(on_update, start_dir=None, parent=None):
    """Open the popup (modal). Returns the image path if on_update succeeded, None if cancelled.
    Creates the Qt application if there is none (scripts, notebooks)."""
    app = QApplication.instance() or QApplication([])  # keep a reference while the dialog runs
    dialog = FirmwareUpdateWindow(on_update, start_dir=start_dir, parent=parent)
    if parent is None:
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint)  # otherwise it can open behind the IDE
    dialog.raise_()
    dialog.activateWindow()
    accepted = dialog.exec_() == QDialog.Accepted
    return dialog.image_path if accepted else None
