# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.models.VolumeSettings import VolumeSettings


class VolumeSettingsWidget(QtWidgets.QWidget):
    settings: VolumeSettings

    offset_spin_box: QtWidgets.QSpinBox
    leaning_angle_spin_box: QtWidgets.QSpinBox

    values_changed: QtCore.Signal = QtCore.Signal(VolumeSettings)

    def __init__(
        self,
        parent: typing.Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        title_font = QtGui.QFont()
        title_font.setBold(True)
        title = QtWidgets.QLabel(text="Atlas Volume Settings", font=title_font)

        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)

        self.offset_spin_box = QtWidgets.QSpinBox()
        self.offset_spin_box.setMinimum(0)
        self.offset_spin_box.setMaximum(0)
        self.offset_spin_box.valueChanged.connect(self.update_offset)

        self.leaning_angle_spin_box = QtWidgets.QSpinBox()
        self.leaning_angle_spin_box.setMinimum(-45)
        self.leaning_angle_spin_box.setMaximum(45)
        self.leaning_angle_spin_box.valueChanged.connect(self.update_leaning_angle)

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow(title)
        layout.addRow(separator)
        layout.addRow("Offset", self.offset_spin_box)
        layout.addRow("Leaning Angle", self.leaning_angle_spin_box)

        self.setLayout(layout)

        self.settings = VolumeSettings()

    def set_offset_spin_box_limits(self, minimum: int, maximum: int) -> None:
        self.offset_spin_box.setMinimum(minimum)
        self.offset_spin_box.setMaximum(maximum)

    def update_from_settings(self, settings: VolumeSettings) -> None:
        self.offset_spin_box.setValue(settings.offset)
        self.update_offset(settings.offset)
        self.leaning_angle_spin_box.setValue(settings.leaning_angle)
        self.update_leaning_angle(settings.leaning_angle)

    @QtCore.Slot()
    def update_offset(self, new_offset: int) -> None:
        self.settings.offset = new_offset
        self.values_changed.emit(self.settings)

    @QtCore.Slot()
    def update_leaning_angle(self, new_angle: int) -> None:
        self.settings.leaning_angle = new_angle
        self.values_changed.emit(self.settings)

    @QtCore.Slot()
    def reset_to_defaults(self) -> None:
        self.offset_spin_box.setValue(0)
        self.leaning_angle_spin_box.setValue(0)

        self.values_changed.emit(self.settings)
