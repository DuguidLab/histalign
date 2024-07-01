# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.application.HistologySettings import HistologySettings


class HistologySettingsWidget(QtWidgets.QWidget):
    settings: HistologySettings

    values_changed: QtCore.Signal = QtCore.Signal(HistologySettings)

    def __init__(self, parent: typing.Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)

        title_font = QtGui.QFont()
        title_font.setBold(True)
        title = QtWidgets.QLabel(text="Histological Slice Settings", font=title_font)

        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)

        rotation_angle_spin_box = QtWidgets.QSpinBox()
        rotation_angle_spin_box.setMinimum(-45)
        rotation_angle_spin_box.setMaximum(45)
        rotation_angle_spin_box.valueChanged.connect(self.update_rotation_angle)

        x_translation_spin_box = QtWidgets.QSpinBox()
        x_translation_spin_box.setMinimum(-100)
        x_translation_spin_box.setMaximum(100)
        x_translation_spin_box.valueChanged.connect(self.update_x_translation)

        y_translation_spin_box = QtWidgets.QSpinBox()
        y_translation_spin_box.setMinimum(-100)
        y_translation_spin_box.setMaximum(100)
        y_translation_spin_box.valueChanged.connect(self.update_y_translation)

        x_scale_spin_box = QtWidgets.QDoubleSpinBox()
        x_scale_spin_box.setMinimum(0.01)
        x_scale_spin_box.setMaximum(2.0)
        x_scale_spin_box.setValue(1.0)
        x_scale_spin_box.setSingleStep(0.01)
        x_scale_spin_box.valueChanged.connect(self.update_x_scale)

        y_scale_spin_box = QtWidgets.QDoubleSpinBox()
        y_scale_spin_box.setMinimum(0.01)
        y_scale_spin_box.setMaximum(2.0)
        y_scale_spin_box.setValue(1.0)
        y_scale_spin_box.setSingleStep(0.01)
        y_scale_spin_box.valueChanged.connect(self.update_y_scale)

        x_shear_spin_box = QtWidgets.QDoubleSpinBox()
        x_shear_spin_box.setMinimum(-1.0)
        x_shear_spin_box.setMaximum(1.0)
        x_shear_spin_box.setValue(0.0)
        x_shear_spin_box.setSingleStep(0.01)
        x_shear_spin_box.valueChanged.connect(self.update_x_shear)

        y_shear_spin_box = QtWidgets.QDoubleSpinBox()
        y_shear_spin_box.setMinimum(-1.0)
        y_shear_spin_box.setMaximum(1.0)
        y_shear_spin_box.setValue(0.0)
        y_shear_spin_box.setSingleStep(0.01)
        y_shear_spin_box.valueChanged.connect(self.update_y_shear)

        layout = QtWidgets.QFormLayout()
        layout.addRow(title)
        layout.addRow(separator)
        layout.addRow("Rotation Angle", rotation_angle_spin_box)
        layout.addRow("X Translation", x_translation_spin_box)
        layout.addRow("Y Translation", y_translation_spin_box)
        layout.addRow("X Scale", x_scale_spin_box)
        layout.addRow("Y Scale", y_scale_spin_box)
        layout.addRow("X Shear", x_shear_spin_box)
        layout.addRow("Y Shear", y_shear_spin_box)

        self.setLayout(layout)

        self.settings = HistologySettings()

    @QtCore.Slot()
    def update_rotation_angle(self, new_angle: int) -> None:
        self.settings.rotation_angle = new_angle
        self.values_changed.emit(self.settings)

    @QtCore.Slot()
    def update_x_translation(self, new_value: int) -> None:
        self.settings.x_translation = new_value
        self.values_changed.emit(self.settings)

    @QtCore.Slot()
    def update_y_translation(self, new_value: int) -> None:
        self.settings.y_translation = new_value
        self.values_changed.emit(self.settings)

    @QtCore.Slot()
    def update_x_scale(self, new_value: int) -> None:
        self.settings.x_scale = round(new_value, 2)
        self.values_changed.emit(self.settings)

    @QtCore.Slot()
    def update_y_scale(self, new_value: int) -> None:
        self.settings.y_scale = round(new_value, 2)
        self.values_changed.emit(self.settings)

    @QtCore.Slot()
    def update_x_shear(self, new_value: int) -> None:
        self.settings.x_shear = round(new_value, 2)
        self.values_changed.emit(self.settings)

    @QtCore.Slot()
    def update_y_shear(self, new_value: int) -> None:
        self.settings.y_shear = round(new_value, 2)
        self.values_changed.emit(self.settings)
