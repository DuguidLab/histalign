# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtGui, QtWidgets


class ImageSettings(QtWidgets.QWidget):
    title: QtWidgets.QLabel
    dv_angle_spin_box: QtWidgets.QSpinBox
    x_translation_spin_box: QtWidgets.QSpinBox
    y_translation_spin_box: QtWidgets.QSpinBox
    x_scale_spin_box: QtWidgets.QDoubleSpinBox
    y_scale_spin_box: QtWidgets.QDoubleSpinBox
    x_shear_spin_box: QtWidgets.QDoubleSpinBox
    y_shear_spin_box: QtWidgets.QDoubleSpinBox

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

        self.x_translation_spin_box = QtWidgets.QSpinBox()
        self.x_translation_spin_box.setMinimum(-100)
        self.x_translation_spin_box.setMaximum(100)
        self.x_translation_spin_box.valueChanged.connect(self.update_x_translation)

        self.y_translation_spin_box = QtWidgets.QSpinBox()
        self.y_translation_spin_box.setMinimum(-100)
        self.y_translation_spin_box.setMaximum(100)
        self.y_translation_spin_box.valueChanged.connect(self.update_y_translation)

        self.x_scale_spin_box = QtWidgets.QDoubleSpinBox()
        self.x_scale_spin_box.setMinimum(0.01)
        self.x_scale_spin_box.setMaximum(2.0)
        self.x_scale_spin_box.setValue(1.0)
        self.x_scale_spin_box.setSingleStep(0.01)
        self.x_scale_spin_box.valueChanged.connect(self.update_x_scale)

        self.y_scale_spin_box = QtWidgets.QDoubleSpinBox()
        self.y_scale_spin_box.setMinimum(0.01)
        self.y_scale_spin_box.setMaximum(2.0)
        self.y_scale_spin_box.setValue(1.0)
        self.y_scale_spin_box.setSingleStep(0.01)
        self.y_scale_spin_box.valueChanged.connect(self.update_y_scale)

        self.x_shear_spin_box = QtWidgets.QDoubleSpinBox()
        self.x_shear_spin_box.setMinimum(-1.0)
        self.x_shear_spin_box.setMaximum(1.0)
        self.x_shear_spin_box.setValue(0.0)
        self.x_shear_spin_box.setSingleStep(0.01)
        self.x_shear_spin_box.valueChanged.connect(self.update_x_shear)

        self.y_shear_spin_box = QtWidgets.QDoubleSpinBox()
        self.y_shear_spin_box.setMinimum(-1.0)
        self.y_shear_spin_box.setMaximum(1.0)
        self.y_shear_spin_box.setValue(0.0)
        self.y_shear_spin_box.setSingleStep(0.01)
        self.y_shear_spin_box.valueChanged.connect(self.update_y_shear)

        layout = QtWidgets.QFormLayout()
        layout.addRow(self.title)
        layout.addRow(separator)
        layout.addRow("DV Angle", self.dv_angle_spin_box)
        layout.addRow("X Translation", self.x_translation_spin_box)
        layout.addRow("Y Translation", self.y_translation_spin_box)
        layout.addRow("X Scale", self.x_scale_spin_box)
        layout.addRow("Y Scale", self.y_scale_spin_box)
        layout.addRow("X Shear", self.x_shear_spin_box)
        layout.addRow("Y Shear", self.y_shear_spin_box)

        self.setLayout(layout)

        self.settings_values = {
            "dv_angle": 0,
            "x_translation": 0,
            "y_translation": 0,
            "x_scale": 1.0,
            "y_scale": 1.0,
            "x_shear": 0.0,
            "y_shear": 0.0,
        }

    @QtCore.Slot()
    def update_dv_angle(self, new_angle: int) -> None:
        self.settings_values["dv_angle"] = new_angle
        self.settings_values_changed.emit(self.settings_values)

    @QtCore.Slot()
    def update_x_translation(self, new_value: int) -> None:
        self.settings_values["x_translation"] = new_value
        self.settings_values_changed.emit(self.settings_values)

    @QtCore.Slot()
    def update_y_translation(self, new_value: int) -> None:
        self.settings_values["y_translation"] = new_value
        self.settings_values_changed.emit(self.settings_values)

    @QtCore.Slot()
    def update_x_scale(self, new_value: int) -> None:
        # Make sure the value doesn't shift extremely slowly by rounding and updating
        # the underlying UI value.
        self.settings_values["x_scale"] = round(new_value, 2)

        self.x_scale_spin_box.blockSignals(True)
        self.x_scale_spin_box.setValue(self.settings_values["x_scale"])
        self.x_scale_spin_box.blockSignals(False)

        self.settings_values_changed.emit(self.settings_values)

    @QtCore.Slot()
    def update_y_scale(self, new_value: int) -> None:
        # Make sure the value doesn't shift extremely slowly by rounding and updating
        # the underlying UI value.
        self.settings_values["y_scale"] = round(new_value, 2)

        self.y_scale_spin_box.blockSignals(True)
        self.y_scale_spin_box.setValue(self.settings_values["y_scale"])
        self.y_scale_spin_box.blockSignals(False)

        self.settings_values_changed.emit(self.settings_values)

    @QtCore.Slot()
    def update_x_shear(self, new_value: int) -> None:
        # Make sure the value doesn't shift extremely slowly by rounding and updating
        # the underlying UI value.
        # Mostly nice for UI stuff, to avoid showing "-0.00"
        self.settings_values["x_shear"] = round(new_value, 2)

        self.x_shear_spin_box.blockSignals(True)
        self.x_shear_spin_box.setValue(self.settings_values["x_shear"])
        self.x_shear_spin_box.blockSignals(False)

        self.settings_values_changed.emit(self.settings_values)

    @QtCore.Slot()
    def update_y_shear(self, new_value: int) -> None:
        # Make sure the value doesn't shift extremely slowly by rounding and updating
        # the underlying UI value.
        # Mostly nice for UI stuff, to avoid showing "-0.00"
        self.settings_values["y_shear"] = round(new_value, 2)

        self.y_shear_spin_box.blockSignals(True)
        self.y_shear_spin_box.setValue(self.settings_values["y_shear"])
        self.y_shear_spin_box.blockSignals(False)

        self.settings_values_changed.emit(self.settings_values)
