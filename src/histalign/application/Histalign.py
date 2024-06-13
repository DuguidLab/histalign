# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import time
import typing

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.application.ImageSettings import ImageSettings
from histalign.application.RotatingLabel import RotatingLabel
from histalign.application.VolumeManager import VolumeManager
from histalign.application.VolumeSettings import VolumeSettings


class Histalign(QtWidgets.QWidget):
    volume_manager: VolumeManager

    alpha_slider: QtWidgets.QSlider
    image_viewer: RotatingLabel
    image_settings: ImageSettings
    volume_viewer: QtWidgets.QLabel
    volume_settings: VolumeSettings

    base_alpha_channel: typing.Optional[np.ndarray] = None

    def __init__(
        self,
        file_path: typing.Optional[str] = None,
        parent: typing.Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("Histalign")

        image = QtGui.QImage()
        image.load(
            "/home/odelree/data/histalign/resources/sub-MM424_exp-38hrb23ce2_conc1x"
            "/png/A5 mcherry555 mecp488 dapi_image0000_"
            "470_New 1_maximum_downsampled.png"
        )
        self.image_viewer = RotatingLabel(
            pixmap=QtGui.QPixmap.fromImage(image),
            alignment=QtCore.Qt.AlignCenter,
        )
        self.image_viewer.image = image

        self.image_settings = ImageSettings()
        self.image_settings.settings_values_changed.connect(
            self.image_viewer.rotate_image
        )

        self.volume_manager = VolumeManager(file_path)

        self.volume_viewer = QtWidgets.QLabel(scaledContents=True)
        self.volume_viewer.setFixedSize(
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

        self.alpha_slider = QtWidgets.QSlider(minimum=0, maximum=255)
        self.alpha_slider.valueChanged.connect(lambda: self.update_displayed_slice())
        self.alpha_slider.setValue(255 // 2)

        layout = QtWidgets.QGridLayout(
            sizeConstraint=QtWidgets.QLayout.SetMaximumSize,
        )
        layout.addWidget(self.alpha_slider, 0, 0, -1, 1)
        layout.addWidget(self.image_viewer, 0, 1, -1, 1)
        layout.addWidget(self.volume_viewer, 0, 1, -1, 1)
        layout.addWidget(self.image_settings, 0, 2)
        layout.addWidget(self.volume_settings, 1, 2)

        self.setLayout(layout)

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
