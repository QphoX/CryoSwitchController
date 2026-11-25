"""Firmware update popup: pick an image, then Update or Cancel. Knows nothing about the board.

on_update(path, progress) does the work in a background thread and may call progress(percent, message).
If it raises, the error is shown and the window stays open; otherwise the window closes.

    path = show_firmware_update_window(on_update)          # None if cancelled
    FirmwareUpdateWindow(on_update, parent=self).exec_()   # embedded in a PyQt5 app
"""
import os

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


class _UpdateWorker(QThread):
    """Runs on_update off the UI thread; signals arrive on the UI thread."""
    progress = pyqtSignal(int, str)
    failed = pyqtSignal(str)
    succeeded = pyqtSignal()

    def __init__(self, on_update, path, parent=None):
        super().__init__(parent)
        self.on_update = on_update
        self.path = path

    def run(self):
        try:
            self.on_update(self.path, self.progress.emit)
        except Exception as error:
            self.failed.emit(str(error) or type(error).__name__)
            return
        self.succeeded.emit()


class FirmwareUpdateWindow(QDialog):
    def __init__(self, on_update, start_dir=None, file_filter="Firmware image (*.bin);;All files (*)",
                 parent=None):
        super().__init__(parent)
        self.on_update = on_update
        self.start_dir = start_dir or os.getcwd()
        self.file_filter = file_filter
        self.image_path = None  # set once a file is chosen
        self._worker = None

        self.setWindowTitle("Firmware update")
        self.setMinimumWidth(500)

        self.path_edit = QLineEdit(self)
        self.path_edit.setPlaceholderText("Select a firmware image...")
        self.path_edit.textChanged.connect(self._path_changed)
        self.browse_button = QPushButton("Browse...", self)
        self.browse_button.clicked.connect(self._browse)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()
        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)

        self.update_button = QPushButton("Update", self)
        self.update_button.setEnabled(False)
        self.update_button.setDefault(True)
        self.update_button.clicked.connect(self._update)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)

        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit)
        path_row.addWidget(self.browse_button)
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.update_button)
        button_row.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Firmware image:", self))
        layout.addLayout(path_row)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addLayout(button_row)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select firmware image", self.start_dir, self.file_filter)
        if path:
            self.path_edit.setText(os.path.normpath(path))

    def _path_changed(self, text):
        path = text.strip()
        self.image_path = path if os.path.isfile(path) else None
        self.update_button.setEnabled(self.image_path is not None)

    def _busy(self):
        return self._worker is not None

    def _set_controls_enabled(self, enabled):
        for widget in (self.path_edit, self.browse_button, self.update_button, self.cancel_button):
            widget.setEnabled(enabled)

    def _update(self):
        self._set_controls_enabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_label.setText("Starting...")
        self._worker = _UpdateWorker(self.on_update, self.image_path, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.failed.connect(self._on_failed)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.start()

    def _on_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    def _finish_worker(self):
        self._worker.wait()
        self._worker = None

    def _on_failed(self, message):
        self._finish_worker()
        self.status_label.setText("Update failed.")
        QMessageBox.critical(self, "Firmware update failed", message)
        self._set_controls_enabled(True)

    def _on_succeeded(self):
        self._finish_worker()
        QMessageBox.information(self, "Firmware update", self.status_label.text() or "Update finished.")
        self.accept()

    def reject(self):  # Cancel button, Esc and the window's close button all end up here
        if not self._busy():
            super().reject()

    def closeEvent(self, event):
        if self._busy():
            event.ignore()
        else:
            super().closeEvent(event)


def show_firmware_update_window(on_update, start_dir=None, parent=None):
    """Modal popup; creates the Qt application if needed (scripts, notebooks)."""
    app = QApplication.instance() or QApplication([])  # keep a reference while the dialog runs
    dialog = FirmwareUpdateWindow(on_update, start_dir=start_dir, parent=parent)
    if parent is None:
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint)  # otherwise it can open behind the IDE
    dialog.raise_()
    dialog.activateWindow()
    accepted = dialog.exec_() == QDialog.Accepted
    return dialog.image_path if accepted else None
