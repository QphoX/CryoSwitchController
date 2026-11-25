"""Launch the CryoSwitch GUI without a board connected (manual UI check, not an automated test).

Uses the fake driver from fake_cryoswitch.py, so nothing is sent to hardware.

Usage (from repo root):  python tests/gui/preview_gui.py
"""

import os
import runpy
import sys

import fake_cryoswitch  # same folder: on sys.path because this file is run as a script

# Repo root on the path so the real Updator package can be imported.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

if __name__ == "__main__":
    fake_cryoswitch.install()
    runpy.run_path(os.path.join(REPO_ROOT, "GUI", "cryoswitch_gui.py"), run_name="__main__")
