# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import time
import typing

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.application.ImageSettings import ImageSettings
from histalign.application.ImageViewer import ImageViewer
from histalign.application.VolumeManager import VolumeManager
from histalign.application.VolumeSettings import VolumeSettings


class Histalign(QtWidgets.QWidget):
    volume_manager: VolumeManager

    alpha_slider: QtWidgets.QSlider
    image_viewer: ImageViewer
    image_settings: ImageSettings
    volume_viewer: QtWidgets.QLabel
    volume_settings: VolumeSettings

    base_alpha_channel: typing.Optional[np.ndarray] = None

    def __init__(
        self,
        histology_slice_file_path: str,
        average_volume_file_path: str,
        parent: typing.Optional[QtCore.QObject] = None,
    ) -> None:
        # Initialisation
        super().__init__(parent)
        self.setWindowTitle("Histalign")

        # Set up histological slice widget
        self.image_viewer = ImageViewer(histology_slice_file_path)

        # Set up histological slice settings widget
        self.image_settings = ImageSettings()
        self.image_settings.settings_values_changed.connect(
            self.image_viewer.transform_pixmap
        )

        # Set up volume manager
        self.volume_manager = VolumeManager(average_volume_file_path)

        # Set up volume viewer widget
        self.volume_viewer = QtWidgets.QLabel(scaledContents=True)
        self.volume_viewer.setFixedSize(
            self.volume_manager.average_volume.shape[0] * 2,
            self.volume_manager.average_volume.shape[1] * 2,
        )

        # Set up volume viewer settings widget
        self.volume_settings = VolumeSettings(
            offset_minimum=-self.volume_manager.average_volume.shape[2] // 2,
            offset_maximum=self.volume_manager.average_volume.shape[2] // 2,
            parent=self,
        )
        self.volume_settings.settings_values_changed.connect(
            self.update_displayed_slice
        )

        # Set up transparency slider (between histological and volume slice)
        self.alpha_slider = QtWidgets.QSlider(minimum=0, maximum=255)
        self.alpha_slider.valueChanged.connect(lambda: self.update_displayed_slice())
        self.alpha_slider.setValue(255 // 2)

        # Organise the layout
        layout = QtWidgets.QGridLayout(sizeConstraint=QtWidgets.QLayout.SetMaximumSize)
        layout.addWidget(self.alpha_slider, 0, 0, -1, 1)
        layout.addWidget(self.image_viewer, 0, 1, -1, 1)
        layout.addWidget(self.volume_viewer, 0, 1, -1, 1)
        layout.addWidget(self.image_settings, 0, 2)
        layout.addWidget(self.volume_settings, 1, 2)
        self.setLayout(layout)

        # Retrieve default displayed volume slice
        self.update_displayed_slice()

    @QtCore.Slot()
    def update_displayed_slice(self, settings: typing.Optional[dict] = None) -> None:
        if settings is None:
            settings = self.volume_settings.settings_values

        new_slice = self.volume_manager.get_slice_from_volume(**settings)
        initial_image = QtGui.QImage(
            new_slice.tobytes(),
            new_slice.shape[1],
            new_slice.shape[0],
            QtGui.QImage.Format_Grayscale8,
        )
        if self.base_alpha_channel is None:
            self.base_alpha_channel = np.zeros(
                (new_slice.shape[0], new_slice.shape[1]), dtype=np.uint8
            )
        initial_image.setAlphaChannel(
            QtGui.QImage(
                (self.base_alpha_channel + self.alpha_slider.value()).tobytes(),
                new_slice.shape[1],
                new_slice.shape[0],
                QtGui.QImage.Format_Alpha8,
            )
        )
        self.volume_viewer.setPixmap(QtGui.QPixmap.fromImage(initial_image))
