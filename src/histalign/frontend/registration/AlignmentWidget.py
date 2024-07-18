# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.models.HistologySettings import HistologySettings
from histalign.backend.workspace.VolumeManager import VolumeManager
from histalign.backend.models.VolumeSettings import VolumeSettings


class AlignmentWidget(QtWidgets.QWidget):
    scene: QtWidgets.QGraphicsScene
    view: QtWidgets.QGraphicsView
    volume_pixmap: QtWidgets.QGraphicsPixmapItem
    volume_manager: VolumeManager
    histology_pixmap: QtWidgets.QGraphicsPixmapItem
    histology_image: QtGui.QImage

    volume_scale_ratio_changed = QtCore.Signal(float)
    histology_scale_ratio_changed = QtCore.Signal(float)

    def __init__(self, parent: typing.Optional[QtCore.QObject]) -> None:
        super().__init__(parent)

        self.scene = QtWidgets.QGraphicsScene(self)

        self.view = QtWidgets.QGraphicsView(self.scene)
        self.view.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 255)))
        self.view.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.view.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.volume_pixmap = self.scene.addPixmap(QtGui.QPixmap())
        self._volume_settings = None
        self.histology_pixmap = self.scene.addPixmap(QtGui.QPixmap())
        self._histology_settings = None

        self.volume_manager = VolumeManager()

        self.histology_image = QtGui.QImage()

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.view)
        self.setLayout(layout)

    def load_volume(self, file_path: str) -> None:
        self.volume_manager.load_volume(file_path)
        self.update_volume_pixmap()

    def load_histological_slice(self, file_path: str) -> None:
        self.histology_image = QtGui.QImage()
        self.histology_image.load(file_path)

        self.histology_pixmap.setPixmap(QtGui.QPixmap.fromImage(self.histology_image))
        self.update_histology_pixmap()

    def update_histological_slice(self, array: np.ndarray) -> None:
        self.histology_image = QtGui.QImage(
            array.tobytes(),
            array.shape[1],
            array.shape[0],
            QtGui.QImage.Format.Format_Grayscale8,
        )

        self.histology_pixmap.setPixmap(QtGui.QPixmap.fromImage(self.histology_image))
        self.update_histology_pixmap()

    def update_volume_pixmap(
        self, settings: typing.Optional[VolumeSettings] = None
    ) -> None:
        if settings is None:
            settings = self._volume_settings
        self._volume_settings = settings

        pixmap = self.convert_8_bit_numpy_to_pixmap(
            self.volume_manager.slice_volume(settings)
        )
        self.volume_pixmap.setPixmap(pixmap)
        self.volume_pixmap.setOffset(
            -self.volume_pixmap.pixmap().width() / 2,
            -self.volume_pixmap.pixmap().height() / 2,
        )
        self.view.setSceneRect(self.volume_pixmap.sceneBoundingRect())

    @QtCore.Slot()
    def reslice_volume(self, settings: VolumeSettings) -> None:
        self.update_volume_pixmap(settings)

    @QtCore.Slot()
    def update_histology_pixmap(
        self, settings: typing.Optional[HistologySettings] = None
    ) -> None:
        if self.histology_pixmap.pixmap().isNull():
            return

        if settings is None:
            if self._histology_settings is None:
                settings = HistologySettings()
            else:
                settings = self._histology_settings
        self._histology_settings = settings

        scale_ratio = self.calculate_scale_ratio(
            self.histology_pixmap.pixmap().size(),
            self.volume_pixmap.sceneBoundingRect().size(),
            self.layout().contentsMargins(),
        )
        self.histology_scale_ratio_changed.emit(scale_ratio)
        initial_transform = QtGui.QTransform().scale(scale_ratio, scale_ratio)
        self.histology_pixmap.setTransform(initial_transform)

        # Scaling variables
        initial_width = self.histology_pixmap.pixmap().width()
        initial_height = self.histology_pixmap.pixmap().height()
        effective_width = settings.x_scale * initial_width
        effective_height = settings.y_scale * initial_height

        # Shearing variables
        x_displacement = settings.x_shear * effective_height
        y_displacement = settings.y_shear * effective_width

        transform = (
            initial_transform.translate(  # Translation to center on (0, 0)
                -initial_width / 2,
                -initial_height / 2,
            )
            .translate(  # Translation to apply rotation around the center of the image
                initial_width / 2,
                initial_height / 2,
            )
            .rotate(  # Regular rotation
                settings.rotation_angle,
            )
            .translate(  # Translation to get back to position before rotation
                -initial_width / 2,
                -initial_height / 2,
            )
            .translate(  # Regular translation
                settings.x_translation,
                settings.y_translation,
            )
            .translate(  # Translation to apply scaling from the center of the image
                -(effective_width - initial_width) / 2,
                -(effective_height - initial_height) / 2,
            )
            .scale(  # Regular scaling
                settings.x_scale,
                settings.y_scale,
            )
            .translate(  # Translation to apply shearing from the center of the image
                -x_displacement / 2,
                -y_displacement / 2,
            )
            .shear(  # Regular shearing
                settings.x_shear,
                settings.y_shear,
            )
        )

        self.histology_pixmap.setTransform(transform)

    @QtCore.Slot()
    def update_histology_alpha(self, alpha: int) -> None:
        if self.histology_image.isNull():
            return

        alpha_image = self.histology_image.copy()
        alpha_image.setAlphaChannel(
            QtGui.QImage(
                (
                    np.zeros(
                        (alpha_image.height(), alpha_image.width()),
                        dtype=np.uint8,
                    )
                    + alpha
                ).tobytes(),
                alpha_image.width(),
                alpha_image.height(),
                QtGui.QImage.Format_Alpha8,
            )
        )
        self.histology_pixmap.setPixmap(QtGui.QPixmap.fromImage(alpha_image))

    def resizeEvent(self, event) -> None:
        try:
            volume_scale_ratio = self.calculate_scale_ratio(
                self.volume_pixmap.pixmap().size(),
                event.size(),
                self.layout().contentsMargins(),
            )
            self.volume_scale_ratio_changed.emit(volume_scale_ratio)
            self.volume_pixmap.setTransform(
                QtGui.QTransform().scale(volume_scale_ratio, volume_scale_ratio)
            )
            self.volume_pixmap.setOffset(
                -self.volume_pixmap.pixmap().width() / 2,
                -self.volume_pixmap.pixmap().height() / 2,
            )
            self.view.setSceneRect(self.volume_pixmap.sceneBoundingRect())
        except ZeroDivisionError:
            return

        self.update_histology_pixmap()

    @staticmethod
    def convert_8_bit_numpy_to_pixmap(array: np.ndarray) -> QtGui.QPixmap:
        image = QtGui.QImage(
            array.tobytes(),
            array.shape[1],
            array.shape[0],
            QtGui.QImage.Format_Grayscale8,
        )
        return QtGui.QPixmap.fromImage(image)

    @staticmethod
    def calculate_scale_ratio(
        old_size: QtCore.QSize | QtCore.QSizeF,
        new_size: QtCore.QSize | QtCore.QSizeF,
        margins: QtCore.QMargins,
    ) -> float:
        return min(
            (new_size.width() - margins.left() - margins.right()) / old_size.width(),
            (new_size.height() - margins.top() - margins.bottom()) / old_size.height(),
        )
