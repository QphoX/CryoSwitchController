"""Labphox firmware update over UDP: self-contained package, copy the folder as-is to reuse it.

Modules are imported explicitly (nothing here) so that non-GUI parts do not require PyQt5:
    from Updator.firmware_update_window import show_firmware_update_window, FirmwareUpdateWindow
"""
