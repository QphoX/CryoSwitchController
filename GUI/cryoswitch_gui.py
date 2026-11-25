_VERSION = "v1.2"  # nopep8

# Changelog
# 1.1: Removed numpy dependency
# 1.2.0: Added Update over the wire (UDP). Added Button and download GUI
import hashlib
import json
import os
import sys

import __main__
import pyqtgraph as pg
from CryoSwitchController import Cryoswitch
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QShortcut,
    QWidget,
)
from pyqtgraph import PlotWidget


# TODO: pulses >100ms will be silently set to 100ms - better way? change line edit when used
# TODO: Connect ALL useful?
class AboutDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(AboutDialog, self).__init__(parent)

        self.setWindowTitle("About")

        layout = QtWidgets.QVBoxLayout(self)

        self.nameLabel = QtWidgets.QLabel("Application Name: CryoSwitch Control Panel")
        self.versionLabel = QtWidgets.QLabel(f"Version: {_VERSION}")
        self.authorLabel = QtWidgets.QLabel("Authors: Cristobal Ferrer, Lars Freisem")
        self.descriptionLabel = QtWidgets.QLabel(
            "Description: GUI for the CryoSwitchController API"
        )
        self.creditsLabel = QtWidgets.QLabel("© 2023 QphoX")

        layout.addWidget(self.nameLabel)
        layout.addWidget(self.versionLabel)
        layout.addWidget(self.authorLabel)
        layout.addWidget(self.descriptionLabel)
        layout.addWidget(self.creditsLabel)

        self.setLayout(layout)


def generate_checksum(string):
    md5_hash = hashlib.md5()
    md5_hash.update(string.encode("utf-8"))
    checksum = md5_hash.hexdigest()[:6]
    return checksum


def python_arange(start, stop, step):
    num = start
    result = []
    while num < stop:
        result.append(num)
        num += step
    return result


def python_ones(length):
    return [1.0] * length


script_filename = os.path.abspath(sys.executable)
__main__.__dict__["last_meas_ID"] = ""
# Define the default settings and their types
default_settings = {
    "column A": "A",
    "column B": "B",
    "column C": "C",
    "column D": "D",
    "row 1": "1",
    "row 2": "2",
    "row 3": "3",
    "row 4": "4",
    "row 5": "5",
    "row 6": "6",
    "default_pulse_voltage_V": 5,
    "default_pulse_current_limit_mA": 80,
    "default_pulse_duration_ms": 15,
    "default_pulse_current_chopping": True,
    "IP": "192.168.1.101",
}
default_types = {
    "column A": str,
    "column B": str,
    "column C": str,
    "column D": str,
    "row 1": str,
    "row 2": str,
    "row 3": str,
    "row 4": str,
    "row 5": str,
    "row 6": str,
    "default_pulse_voltage_V": (int, float),
    "default_pulse_current_limit_mA": (int, float),
    "default_pulse_duration_ms": (int, float),
    "default_pulse_current_chopping": bool,
    "IP": str,
}

# Get the path to the AppData\Roaming directory
try:
    appdata_path = os.environ["APPDATA"]
    settings_file = os.path.join(
        appdata_path, f"cryoswitch_settings_{generate_checksum(script_filename)}.json"
    )
    _config_path = "%appdata%"
except KeyError:
    appdata_path = os.environ["HOME"]
    settings_file = os.path.join(
        appdata_path,
        ".config",
        f"cryoswitch_settings_{generate_checksum(script_filename)}.json",
    )
    _config_path = "~/.config"


def load_settings():
    """
    by chatgpt, v2.2
    """
    try:
        if os.path.exists(settings_file):
            with open(settings_file, "r") as f:
                settings = json.load(f)

            # Check each setting for type correctness and correct key
            for setting, value in list(settings.items()):
                if setting not in default_types:
                    print(
                        f"Misspelled or unknown parameter {setting}, marking as invalid"
                    )
                    if "_INVALID_PARAMETER" not in setting:
                        settings[setting + "_INVALID_PARAMETER"] = settings.pop(setting)
                else:
                    allowed_types = default_types[setting]

                    # If the allowed type is not a tuple, make it a tuple
                    if not isinstance(allowed_types, tuple):
                        allowed_types = (allowed_types,)

                    if not any(isinstance(value, t) for t in allowed_types):
                        print(
                            f"Invalid type for {setting}, marking as invalid, resetting to default"
                        )
                        settings[setting + "_INVALID_PARAMETER"] = settings.pop(setting)
                        settings[setting] = default_settings[setting]

            # Check if any default setting is missing in the loaded settings
            for setting, default_value in default_settings.items():
                if setting not in settings:
                    print(f"Missing {setting}, adding to settings")
                    settings[setting] = default_value

            # Write back the settings after checking the types and missing values
            with open(settings_file, "w") as f:
                json.dump(settings, f, indent=4)
        else:
            print("Settings file not found, creating a new one with default settings")
            with open(settings_file, "w") as f:
                json.dump(default_settings, f, indent=4)

            settings = default_settings.copy()
    except json.decoder.JSONDecodeError:
        settings = default_settings.copy()
    return settings


settings = load_settings()


class GridButton(QPushButton):
    def __init__(
        self,
        parent=None,
        colorscheme={},
        functionality_IDs={},
        buttonfriends=[],
        buttonallies=[],
    ):
        super(GridButton, self).__init__(parent)
        self.colorscheme = colorscheme
        self.functionality_IDs = functionality_IDs
        self.buttonfriends = buttonfriends
        self.buttonallies = buttonallies
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.right_click)
        self.clicked.connect(self.left_click)
        self.cs = functionality_IDs["CS"]
        self.measurement_ID = f"{self.functionality_IDs['port']}/{self.functionality_IDs['contact']}/{self.functionality_IDs['button']}"

    def left_click(self):
        # lighten other buttons
        for btn in self.buttonfriends:
            btn.lighten()
        for btn in self.buttonallies:
            btn.darken()
        self.darken()
        # Process information

        if self.functionality_IDs["contact"] == "ALL":
            for btn in self.buttonallies:
                btn.left_click()
        else:
            self.update_parameters()

            if self.functionality_IDs["button"] == "conn":
                self.cs.internal_measured_A[self.measurement_ID] = (
                    self.cs.connect(
                        port=self.functionality_IDs["port"],
                        contact=self.functionality_IDs["contact"],
                    )
                    / 1000
                )  # turn into smart connect and then also change button logic? - no, but see if it was disconnected before
            elif self.functionality_IDs["button"] == "disc":
                self.cs.internal_measured_A[self.measurement_ID] = (
                    self.cs.disconnect(
                        port=self.functionality_IDs["port"],
                        contact=self.functionality_IDs["contact"],
                    )
                    / 1000
                )
            self.cs.internal_inferred_t[self.measurement_ID] = python_arange(
                0,
                0
                + (
                    len(self.cs.internal_measured_A[self.measurement_ID])
                    * 1
                    / self.cs.sampling_freq
                ),
                1 / self.cs.sampling_freq,
            )
            self.cs.internal_limit_of_mA[self.measurement_ID] = (
                python_ones(len(self.cs.internal_measured_A[self.measurement_ID]))
                * self.cs.internal_OCP_mA_tracked
                / 1000
            )
            self.right_click()

    def update_parameters(self):
        self.data_validation()
        voltage_V = float(self.functionality_IDs["voltage"].text().replace(",", "."))
        duration_ms = float(self.functionality_IDs["duration"].text().replace(",", "."))
        current_mA = float(self.functionality_IDs["OCP"].text().replace(",", "."))
        chopping_enabled = self.functionality_IDs["chopping"].isChecked()

        if self.cs.converter_voltage != voltage_V:
            self.cs.set_output_voltage(voltage_V)
        if self.cs.pulse_duration_ms != duration_ms:
            self.cs.set_pulse_duration_ms(duration_ms)
        if self.cs.internal_OCP_mA_tracked != current_mA:
            self.cs.set_OCP_mA(current_mA)
            self.cs.internal_OCP_mA_tracked = current_mA
        if self.cs.internal_chopping_tracked != chopping_enabled:
            if chopping_enabled:
                self.cs.enable_chopping()
            else:
                self.cs.disable_chopping()
            self.cs.internal_chopping_tracked = chopping_enabled

    def data_validation(self):
        self.limit_checker("voltage", 5, 30)
        self.limit_checker("duration", 1, 100)
        self.limit_checker("OCP", 1, 500)

    # def enter_pressed(self, event):
    #     if event.key() in (QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return):
    #         self.update_parameters()
    #     super().keyPressEvent(event)

    def limit_checker(self, dic_key, lower_bound, upper_bound):
        OCP_value = float(self.functionality_IDs[dic_key].text().replace(",", "."))
        if OCP_value < lower_bound:
            self.functionality_IDs[dic_key].setText(str(lower_bound))
            self.functionality_IDs[dic_key].setStyleSheet("background-color: salmon")
        elif OCP_value > upper_bound:
            self.functionality_IDs[dic_key].setText(str(upper_bound))
            self.functionality_IDs[dic_key].setStyleSheet("background-color: salmon")
        else:
            self.functionality_IDs[dic_key].setStyleSheet("background-color: White")

    def lighten(self):
        self.setStyleSheet(f"background-color: {self.colorscheme['neutral']}")

    def darken(self):
        self.setStyleSheet(f"background-color: {self.colorscheme['dark']}")

    def right_click(self):
        if (
            self.functionality_IDs["contact"] != "ALL"
        ):  # TODO: multiplot could be cool but isn't implemented
            if self.functionality_IDs["button"] == "conn":
                operation = "connection"
            elif self.functionality_IDs["button"] == "disc":
                operation = "disconnection"
            self.functionality_IDs["plot"].setText(
                f"Current draw during last {operation} of port {self.functionality_IDs['port']} contact {self.functionality_IDs['contact']}"
            )
            __main__.__dict__["last_meas_ID"] = self.measurement_ID
            self.right_click_helper()

    def right_click_helper(self):
        pass


class CSCApp(QWidget):
    def __init__(self):
        super().__init__()
        try:
            try:
                self.cs = Cryoswitch(
                    IP=settings["IP"], override_abspath=os.path.dirname(script_filename)
                )  # Only works with exe now
            except FileNotFoundError:
                self.cs = Cryoswitch(IP=settings["IP"])  # Only works with exe now
        except TimeoutError:
            IP = input(
                "The initialization failed because of a network timeout. Please provide the correct IP address: "
            )
            with open(settings_file, "w") as f:
                settings["IP"] = IP
                json.dump(settings, f, indent=4)
            self.cs = Cryoswitch(
                IP=IP, override_abspath=os.path.dirname(script_filename)
            )

        # General layout options
        self.N_ports = self.cs.ports_enabled
        self.N_contacts = 6
        self.labphoxch_translator = {1: "A", 2: "B", 3: "C", 4: "D"}

        # Color options
        self.background_color = (240, 240, 240)
        self.plot_background_color = (230, 230, 230)

        self.current_line_color = (0, 119, 187)
        self.OCP_line_color = (235, 28, 28)
        self.line_widths = 2
        self.plot_font_size = 18

        # Inits
        self.initUI()
        self.initHW()

    def initHW(self):
        self.cs.start()
        self.cs.plot = False
        self.cs.log_wav = False
        self.cs.plot_polarization = False
        self.cs.internal_OCP_mA_tracked = None
        self.cs.internal_chopping_tracked = None
        self.cs.internal_measured_A = {}
        self.cs.internal_inferred_t = {}
        self.cs.internal_limit_of_mA = {}

    def initUI(self):
        self.shortcut1 = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.shortcut1.activated.connect(QApplication.instance().quit)
        self.shortcut2 = QShortcut(QKeySequence("Ctrl+W"), self)
        self.shortcut2.activated.connect(QApplication.instance().quit)

        grid = QGridLayout()
        self.setLayout(grid)

        duration_label = QLabel("Pulse duration [ms]: ", self)
        duration_lineedit = QLineEdit(str(settings["default_pulse_duration_ms"]), self)
        duration_lineedit.setStyleSheet("background-color: White")

        voltage_label = QLabel("Pulse voltage [V]:", self)
        voltage_lineedit = QLineEdit(str(settings["default_pulse_voltage_V"]), self)
        voltage_lineedit.setStyleSheet("background-color: White")

        chopping_checkbox = QCheckBox("Chopping", self)
        chopping_checkbox.setChecked(settings["default_pulse_current_chopping"])
        chopping_checkbox.setToolTip(
            "🗹: The drive current will be chopped to match the current limit for the full duration of the pulse.\n☐: The drive current immediately stops and falls to zero after reaching the limit."
        )  # switch to ☒ ?

        OCP_label = QLabel("Limit current [mA]: ", self)
        OCP_lineedit = QLineEdit(str(settings["default_pulse_current_limit_mA"]), self)
        OCP_lineedit.setStyleSheet("background-color: White")
        # OCP_lineedit.setFixedWidth(300)

        plot_label = QLabel("Plot", self)
        plot_label.setMinimumWidth(600)
        plot_label.setAlignment(Qt.AlignCenter)

        grid.addWidget(duration_label, 0, 0, 1, 2)
        grid.addWidget(duration_lineedit, 0, 2, 1, 2)
        grid.addWidget(voltage_label, 1, 0, 1, 2)
        grid.addWidget(voltage_lineedit, 1, 2, 1, 2)

        colors = [
            "mistyrose",
            "mistyrose",
            "lightgoldenrodyellow",
            "lightgoldenrodyellow",
            "honeydew",
            "honeydew",
            "lavender",
            "lavender",
        ]
        colors_dark = [
            "tomato",
            "tomato",
            "goldenrod",
            "goldenrod",
            "lightgreen",
            "lightgreen",
            "deepskyblue",
            "deepskyblue",
        ]

        buttonfriends = (
            {}
        )  # these other buttons are "unmarked" visually when the clicked button is activated (no action)
        buttonallies = (
            {}
        )  # these other buttons switch on together with the clicked button (including all click-actions)
        for phxch in range(self.N_ports):
            buttonfriends.update({f"{phxch + 1}/ALL/conn": []})
            buttonfriends.update({f"{phxch + 1}/ALL/disc": []})
            buttonallies.update({f"{phxch + 1}/ALL/conn": []})
            buttonallies.update({f"{phxch + 1}/ALL/disc": []})
            for i in range(self.N_contacts):
                buttonallies.update({f"{phxch + 1}/{i + 1}/conn": []})
                buttonallies.update({f"{phxch + 1}/{i + 1}/disc": []})
                buttonfriends.update({f"{phxch + 1}/{i + 1}/conn": []})
                buttonfriends.update({f"{phxch + 1}/{i + 1}/disc": []})

        for i in range(3, 10):
            for j in range(self.N_ports * 2):
                labphoxch_startsfrom1 = j // 2 + 1
                if labphoxch_startsfrom1 <= self.N_ports:
                    channel = i - 2  # replace add sf1
                    if i == 9:
                        if j % 2 == 0:
                            label = QLabel(
                                [
                                    settings[ii]
                                    for ii in [
                                        "column A",
                                        "column B",
                                        "column C",
                                        "column D",
                                    ]
                                ][labphoxch_startsfrom1 - 1],
                                self,
                            )
                            label.setStyleSheet(f"background-color: {colors[j]}")
                            # label.setMinimumSize(330, 30)
                            label.setAlignment(Qt.AlignCenter)
                            grid.addWidget(label, 2, j, 1, 2)

                    if i >= 9:
                        channel = "ALL"
                    if j % 2 == 0:
                        buttonfn = "disc"
                        buttonfn_opposite = "conn"
                        buttontext = f"Disc. "
                    else:
                        buttonfn = "conn"
                        buttonfn_opposite = "disc"
                        buttontext = f"Conn. "
                    if isinstance(channel, int):
                        buttontext += settings[f"row {channel}"]
                    else:
                        buttontext += "ALL"

                    if channel != "ALL" or buttonfn != "conn":
                        labphoxch_startsfrom1_formatted = self.labphoxch_translator[
                            labphoxch_startsfrom1
                        ]
                        button = GridButton(
                            parent=self,
                            colorscheme={"dark": colors_dark[j], "neutral": colors[j]},
                            # 0 is cs, 1 is V QE, 2 is ms QE, 3 is mA QE, 4 is port, 5 is contact, 6 is conn disc, 7 is chopping chb, 8 is plot label
                            functionality_IDs={
                                "CS": self.cs,
                                "voltage": voltage_lineedit,
                                "duration": duration_lineedit,
                                "OCP": OCP_lineedit,
                                "port": labphoxch_startsfrom1_formatted,
                                "contact": channel,
                                "button": buttonfn,
                                "chopping": chopping_checkbox,
                                "plot": plot_label,
                            },
                            # functionality_IDs=[
                            #     self.cs,
                            #     voltage_lineedit,
                            #     duration_lineedit,
                            #     OCP_lineedit,
                            #     labphoxch_startsfrom1_formatted,
                            #     channel,
                            #     buttonfn,
                            #     chopping_checkbox,
                            #     plot_label,
                            # ],
                            buttonfriends=buttonfriends[
                                f"{labphoxch_startsfrom1}/{channel}/{buttonfn}"
                            ],
                            buttonallies=buttonallies[
                                f"{labphoxch_startsfrom1}/{channel}/{buttonfn}"
                            ],
                        )

                        if channel != "ALL":
                            buttonfriends[
                                f"{labphoxch_startsfrom1}/ALL/{buttonfn_opposite}"
                            ].append(button)
                            buttonallies[
                                f"{labphoxch_startsfrom1}/ALL/{buttonfn}"
                            ].append(button)
                            button.right_click_helper = self.update_plot_data
                            grid.addWidget(button, i, j)

                        else:
                            for k in range(1, 7):
                                buttonfriends[
                                    f"{labphoxch_startsfrom1}/{k}/{buttonfn_opposite}"
                                ].append(button)

                            grid.addWidget(button, i, j, 1, 2)

                        buttonfriends[
                            f"{labphoxch_startsfrom1}/{channel}/{buttonfn_opposite}"
                        ].append(button)
                        button.setStyleSheet(f"background-color: {colors[j]}")
                        button.setText(buttontext)

        grid.addWidget(chopping_checkbox, 1, 6, 1, 2)
        grid.addWidget(OCP_label, 0, 4, 1, 2)
        grid.addWidget(OCP_lineedit, 0, 6, 1, 2)

        current_plot_widget = PlotWidget(self, background=self.background_color)
        current_plot_item = current_plot_widget.getPlotItem()
        current_plot_item.getViewBox().setBackgroundColor(self.plot_background_color)

        current_plot_widget.setLabel(
            "left", "Current", units="A"
        )  # , **{'font-size': '14pt'}
        current_plot_widget.setLabel("bottom", "Time", units="s")
        # current_plot_widget.showGrid(x=True, y=True)

        MeasCurrent_pen = pg.mkPen(
            color=self.current_line_color, width=self.line_widths
        )
        OCP_pen = pg.mkPen(
            color=self.OCP_line_color, width=self.line_widths, style=QtCore.Qt.DotLine
        )

        self.measured_line = current_plot_widget.plot(
            [0, 1], [0, 1], pen=MeasCurrent_pen, name="Measured current"
        )
        self.OCP_line = current_plot_widget.plot(
            [0, 1], [1, 0], pen=OCP_pen, name="Current limit"
        )

        legend = pg.LegendItem(offset=(70, 30))
        legend.setParentItem(current_plot_widget.graphicsItem())
        legend.setAutoFillBackground(False)
        legend.addItem(self.measured_line, "Measured current")
        legend.addItem(self.OCP_line, "Current limit")

        grid.addWidget(current_plot_widget, 1, 8, 10, 1)
        grid.addWidget(plot_label, 0, 8, 1, 1)

        help_info_label = QLabel(
            f"Leftclick: Actuate switch // Rightclick: Show last measured current.\nOptionally, change labels and default settings in {_config_path}/cryoswitch_settings_{generate_checksum(script_filename)}.json",
            self,
        )
        help_info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # help_info_label.setAlignment(Qt.AlignCenter)
        help_info_label.setStyleSheet("color: gray;")
        grid.addWidget(help_info_label, 10, 0, 1, 7)
        about_button = QPushButton("About")
        about_button.clicked.connect(self.show_about_dialog)
        grid.addWidget(about_button, 10, 7, 1, 1)
        # self.setGeometry(300, 300, 800, 600)
        self.setWindowTitle(f"CryoSwitch Control Panel {_VERSION}")
        self.show()

    def show_about_dialog(self):
        dialog = AboutDialog()
        dialog.exec_()

    def update_plot_data(self):
        try:
            self.measured_line.setData(
                self.cs.internal_inferred_t[__main__.__dict__["last_meas_ID"]],
                self.cs.internal_measured_A[__main__.__dict__["last_meas_ID"]],
            )
            self.OCP_line.setData(
                self.cs.internal_inferred_t[__main__.__dict__["last_meas_ID"]],
                self.cs.internal_limit_of_mA[__main__.__dict__["last_meas_ID"]],
            )
            # self.data_line3.setData(self.x, self.y3)
        except KeyError:
            print("No saved data in this slot.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = CSCApp()
    sys.exit(app.exec_())
