# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.models.HistologySettings import HistologySettings


class HistologySettingsWidget(QtWidgets.QWidget):
    settings: HistologySettings

    rotation_angle_spin_box: QtWidgets.QSpinBox
    x_translation_spin_box: QtWidgets.QSpinBox
    y_translation_spin_box: QtWidgets.QSpinBox
    x_scale_spin_box: QtWidgets.QDoubleSpinBox
    y_scale_spin_box: QtWidgets.QDoubleSpinBox
    x_shear_spin_box: QtWidgets.QDoubleSpinBox
    y_shear_spin_box: QtWidgets.QDoubleSpinBox

    values_changed: QtCore.Signal = QtCore.Signal(HistologySettings)

    def __init__(self, parent: typing.Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)

        title_font = QtGui.QFont()
        title_font.setBold(True)
        title = QtWidgets.QLabel(text="Histological Slice Settings", font=title_font)

        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)

        self.rotation_angle_spin_box = QtWidgets.QSpinBox()
        self.rotation_angle_spin_box.setMinimum(-45)
        self.rotation_angle_spin_box.setMaximum(45)
        self.rotation_angle_spin_box.valueChanged.connect(self.update_rotation_angle)

        self.x_translation_spin_box = QtWidgets.QSpinBox()
        self.x_translation_spin_box.setMinimum(-500)
        self.x_translation_spin_box.setMaximum(500)
        self.x_translation_spin_box.valueChanged.connect(self.update_x_translation)
        self.x_translation_spin_box.installEventFilter(self)

        self.y_translation_spin_box = QtWidgets.QSpinBox()
        self.y_translation_spin_box.setMinimum(-500)
        self.y_translation_spin_box.setMaximum(500)
        self.y_translation_spin_box.valueChanged.connect(self.update_y_translation)
        self.y_translation_spin_box.installEventFilter(self)

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
        layout.addRow(title)
        layout.addRow(separator)
        layout.addRow("Rotation Angle", self.rotation_angle_spin_box)
        layout.addRow("X Translation", self.x_translation_spin_box)
        layout.addRow("Y Translation", self.y_translation_spin_box)
        layout.addRow("X Scale", self.x_scale_spin_box)
        layout.addRow("Y Scale", self.y_scale_spin_box)
        layout.addRow("X Shear", self.x_shear_spin_box)
        layout.addRow("Y Shear", self.y_shear_spin_box)

        self.setLayout(layout)

        self.settings = HistologySettings()

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if not watched.isEnabled():
            return super().eventFilter(watched, event)

        match event.type():
            case QtCore.QEvent.Type.Wheel:
                if event.angleDelta().y() > 0:  # Scroll up
                    watched.setValue(watched.value() + 5 * watched.singleStep())
                elif event.angleDelta().y() < 0:  # Scroll down
                    watched.setValue(watched.value() - 5 * watched.singleStep())
                else:  # Could be horizontal scrolling
                    return super().eventFilter(watched, event)

                # Reproduce selection behaviour as it is with up/down buttons
                watched.lineEdit().setSelection(
                    len(watched.lineEdit().text()), -watched.lineEdit().maxLength()
                )
            case _:
                return super().eventFilter(watched, event)

        return True

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

    @QtCore.Slot()
    def reset_to_defaults(self) -> None:
        self.rotation_angle_spin_box.setValue(0)
        self.x_translation_spin_box.setValue(0)
        self.y_translation_spin_box.setValue(0)
        self.x_scale_spin_box.setValue(1.0)
        self.y_scale_spin_box.setValue(1.0)
        self.x_shear_spin_box.setValue(0.0)
        self.y_shear_spin_box.setValue(0.0)

        self.values_changed.emit(self.settings)
