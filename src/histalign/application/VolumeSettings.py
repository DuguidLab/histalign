# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtGui, QtWidgets


class VolumeSettings(QtWidgets.QWidget):
    title: QtWidgets.QLabel
    offset_spin_box: QtWidgets.QSpinBox
    ml_angle_spin_box: QtWidgets.QSpinBox

    settings_values: dict

    settings_values_changed: QtCore.Signal = QtCore.Signal(dict)

    def __init__(
        self,
        offset_minimum: int,
        offset_maximum: int,
        parent: typing.Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        title_font = QtGui.QFont()
        title_font.setBold(True)
        self.title = QtWidgets.QLabel(text="Volume Settings", font=title_font)

        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)

        self.offset_spin_box = QtWidgets.QSpinBox()
        self.offset_spin_box.setMinimum(offset_minimum)
        self.offset_spin_box.setMaximum(offset_maximum)
        self.offset_spin_box.valueChanged.connect(self.update_offset)

        self.ml_angle_spin_box = QtWidgets.QSpinBox()
        self.ml_angle_spin_box.setMinimum(-45)
        self.ml_angle_spin_box.setMaximum(45)
        self.ml_angle_spin_box.valueChanged.connect(self.update_ml_angle)

        layout = QtWidgets.QFormLayout()
        layout.addRow(self.title)
        layout.addRow(separator)
        layout.addRow("Offset", self.offset_spin_box)
        layout.addRow("ML Angle", self.ml_angle_spin_box)

        self.setLayout(layout)

        self.settings_values = {
            "kind": "normal",
            "origin": None,
            "ml_angle": 0,
            "axes": (0, 1),
            "offset": 0,
        }

    @QtCore.Slot()
    def update_offset(self, new_offset: int) -> None:
        self.settings_values["offset"] = new_offset
        self.settings_values_changed.emit(self.settings_values)

    @QtCore.Slot()
    def update_ml_angle(self, new_angle: int) -> None:
        self.settings_values["ml_angle"] = new_angle
        self.settings_values_changed.emit(self.settings_values)
