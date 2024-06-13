# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import time
import typing

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.application.VolumeManager import VolumeManager
from histalign.application.VolumeSettings import VolumeSettings


class Histalign(QtWidgets.QWidget):
    volume_manager: VolumeManager

    image_viewer: QtWidgets.QLabel
    volume_settings: QtWidgets.QWidget

    def __init__(
        self,
        file_path: typing.Optional[str] = None,
        parent: typing.Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("Histalign")

        self.volume_manager = VolumeManager(file_path)

        self.image_viewer = QtWidgets.QLabel(
            scaledContents=True,
        )
        self.image_viewer.setFixedSize(
            self.volume_manager.average_volume.shape[0] * 2,
            self.volume_manager.average_volume.shape[1] * 2,
        )

        self.volume_settings = VolumeSettings(
            offset_minimum=-self.volume_manager.average_volume.shape[2] // 2,
            offset_maximum=self.volume_manager.average_volume.shape[2] // 2,
            parent=self,
        )
        self.volume_settings.settings_values_changed.connect(
            self.update_displayed_slice
        )

        self.update_displayed_slice(self.volume_settings.settings_values)

        layout = QtWidgets.QGridLayout(
            sizeConstraint=QtWidgets.QLayout.SetDefaultConstraint,
        )
        layout.addWidget(self.image_viewer, 0, 0)
        layout.addWidget(self.volume_settings, 0, 1)

        self.setLayout(layout)

    @QtCore.Slot()
    def update_displayed_slice(self, settings: dict) -> None:
        new_slice = self.volume_manager.get_slice_from_volume(**settings)
        initial_image = QtGui.QImage(
            new_slice.tobytes(),
            new_slice.shape[1],
            new_slice.shape[0],
            QtGui.QImage.Format_Grayscale8,
        )
        self.image_viewer.setPixmap(QtGui.QPixmap.fromImage(initial_image))
