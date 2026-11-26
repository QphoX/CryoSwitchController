"""Hardware-free stand-in for ``CryoSwitchController.Cryoswitch``.

For GUI development and tests only: switch actions return a synthetic current
trace and nothing here reflects real hardware behaviour.

    import fake_cryoswitch
    fake_cryoswitch.install()   # before cryoswitch_gui is imported/run
"""

import math
import sys
import types


class _Trace(list):
    """List that supports ``/ number`` like the numpy array the real driver returns."""

    def __truediv__(self, k):
        return _Trace(v / k for v in self)


class _FakeLabphox:
    """Minimal stand-in for the Labphox driver object (``Cryoswitch.labphox``)."""

    USB_or_ETH = 2  # pretend Ethernet

    @staticmethod
    def require_FW(feature):
        pass


class FakeCryoswitch:
    ports_enabled = 4
    sampling_freq = 28000  # placeholder value, not taken from the real driver

    def __init__(self, *args, **kwargs):
        self.converter_voltage = None
        self.pulse_duration_ms = None
        self.labphox = _FakeLabphox()
        print("[fake] FakeCryoswitch created (no hardware)")

    def start(self):
        print("[fake] start()")

    def _pulse(self, action, port, contact):
        print(f"[fake] {action}(port={port}, contact={contact})")
        # Synthetic decaying pulse in mA, for plotting only.
        return _Trace(50 * math.exp(-i / 40) for i in range(200))

    def connect(self, port, contact):
        return self._pulse("connect", port, contact)

    def disconnect(self, port, contact):
        return self._pulse("disconnect", port, contact)

    def set_output_voltage(self, v):
        self.converter_voltage = v

    def set_pulse_duration_ms(self, ms):
        self.pulse_duration_ms = ms

    def update_firmware(self, image_path=None, *, progress=None, start_dir=None):
        # Defined explicitly so __getattr__ cannot turn it into a silent "success".
        raise RuntimeError("Fake board: no board connected, nothing was sent.")

    def __getattr__(self, name):
        # Any other driver method (set_OCP_mA, enable_chopping, ...) becomes a no-op.
        def _noop(*args, **kwargs):
            print(f"[fake] {name}{args or ''}{kwargs or ''}")

        return _noop


def install():
    """Register the fake as the ``CryoSwitchController`` module."""
    module = types.ModuleType("CryoSwitchController")
    module.Cryoswitch = FakeCryoswitch
    sys.modules["CryoSwitchController"] = module
