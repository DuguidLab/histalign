# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtGui, QtWidgets


class ImageSettings(QtWidgets.QWidget):
    title: QtWidgets.QLabel
    dv_angle_spin_box: QtWidgets.QSpinBox

    settings_values: dict

    settings_values_changed: QtCore.Signal = QtCore.Signal(dict)

    def __init__(self, parent: typing.Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)

        title_font = QtGui.QFont()
        title_font.setBold(True)
        self.title = QtWidgets.QLabel(text="Image Settings", font=title_font)

        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)

        self.dv_angle_spin_box = QtWidgets.QSpinBox()
        self.dv_angle_spin_box.setMinimum(-45)
        self.dv_angle_spin_box.setMaximum(45)
        self.dv_angle_spin_box.valueChanged.connect(self.update_dv_angle)

        layout = QtWidgets.QFormLayout()
        layout.addRow(self.title)
        layout.addRow(separator)
        layout.addRow("DV Angle", self.dv_angle_spin_box)

        self.setLayout(layout)

        self.settings_values = {
            "dv_angle": 0,
        }

    @QtCore.Slot()
    def update_dv_angle(self, new_angle: int) -> None:
        self.settings_values["dv_angle"] = new_angle
        self.settings_values_changed.emit(self.settings_values)
