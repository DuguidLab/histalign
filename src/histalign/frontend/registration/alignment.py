# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets
import numpy as np

from histalign.backend.models import (
    AlignmentSettings,
    HistologySettings,
    VolumeSettings,
)
from histalign.backend.workspace import VolumeSlicer
from histalign.frontend.registration.helpers import get_dummy_title_bar


class AlignmentWidget(QtWidgets.QWidget):
    scene: QtWidgets.QGraphicsScene
    view: QtWidgets.QGraphicsView
    volume_pixmap: QtWidgets.QGraphicsPixmapItem
    volume_slicer: Optional[VolumeSlicer] = None
    histology_pixmap: QtWidgets.QGraphicsPixmapItem
    histology_image: QtGui.QImage

    alignment_settings: Optional[AlignmentSettings] = None
    volume_settings: Optional[VolumeSettings] = None
    histology_settings: Optional[HistologySettings] = None

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
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
        self.histology_pixmap = self.scene.addPixmap(QtGui.QPixmap())
        self.histology_image = QtGui.QImage()

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.view)
        self.setLayout(layout)

    def prepare_slicer(self) -> None:
        self.volume_slicer = VolumeSlicer(
            path=self.alignment_settings.volume_path,
            resolution=self.alignment_settings.volume_settings.resolution,
        )

    def update_histological_slice(self, array: Optional[np.ndarray]) -> None:
        if array is None:
            self.histology_image = QtGui.QImage()
        else:
            self.histology_image = QtGui.QImage(
                array.tobytes(),
                array.shape[1],
                array.shape[0],
                array.shape[1],
                QtGui.QImage.Format.Format_Grayscale8,
            )

            self.histology_image.setAlphaChannel(
                QtGui.QImage(
                    np.where(array > 5, 255, 0).astype(np.uint8).tobytes(),
                    array.shape[1],
                    array.shape[0],
                    array.shape[1],
                    QtGui.QImage.Format_Alpha8,
                )
            )

        self.histology_pixmap.setPixmap(QtGui.QPixmap.fromImage(self.histology_image))
        self.update_histology_pixmap()

    def resizeEvent(self, event) -> None:
        try:
            volume_scale_ratio = self.compute_scaling(
                self.volume_pixmap.pixmap().size(),
                event.size(),
                self.layout().contentsMargins(),
            )
            self.alignment_settings.volume_scaling = volume_scale_ratio
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

    @QtCore.Slot()
    def update_volume_pixmap(self) -> None:
        pixmap = self.convert_8_bit_numpy_to_pixmap(
            self.volume_slicer.slice(self.volume_settings)
        )
        self.volume_pixmap.setPixmap(pixmap)
        self.volume_pixmap.setOffset(
            -self.volume_pixmap.pixmap().width() / 2,
            -self.volume_pixmap.pixmap().height() / 2,
        )
        self.view.setSceneRect(self.volume_pixmap.sceneBoundingRect())

    @QtCore.Slot()
    def update_histology_pixmap(self) -> None:
        if self.histology_pixmap.pixmap().isNull():
            return

        scale_ratio = self.compute_scaling(
            self.histology_pixmap.pixmap().size(),
            self.volume_pixmap.sceneBoundingRect().size(),
            self.layout().contentsMargins(),
        )
        self.alignment_settings.histology_scaling = scale_ratio
        initial_transform = QtGui.QTransform().scale(scale_ratio, scale_ratio)
        self.histology_pixmap.setTransform(initial_transform)

        # Scaling variables
        initial_width = self.histology_pixmap.pixmap().width()
        initial_height = self.histology_pixmap.pixmap().height()
        effective_width = self.histology_settings.scale_x * initial_width
        effective_height = self.histology_settings.scale_y * initial_height

        # Shearing variables
        displacement_x = self.histology_settings.shear_x * effective_height
        displacement_y = self.histology_settings.shear_y * effective_width

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
                self.histology_settings.rotation,
            )
            .translate(  # Translation to get back to position before rotation
                -initial_width / 2,
                -initial_height / 2,
            )
            .translate(  # Regular translation
                self.histology_settings.translation_x,
                self.histology_settings.translation_y,
            )
            .translate(  # Translation to apply scaling from the center of the image
                -(effective_width - initial_width) / 2,
                -(effective_height - initial_height) / 2,
            )
            .scale(  # Regular scaling
                self.histology_settings.scale_x,
                self.histology_settings.scale_y,
            )
            .translate(  # Translation to apply shearing from the center of the image
                -displacement_x / 2,
                -displacement_y / 2,
            )
            .shear(  # Regular shearing
                self.histology_settings.shear_x,
                self.histology_settings.shear_y,
            )
        )

        self.histology_pixmap.setTransform(transform)

    @QtCore.Slot()
    def update_histology_alpha(self, alpha: int) -> None:
        if self.histology_image.isNull():
            return

        general_alpha = QtGui.QImage(
            (
                np.zeros(
                    (self.histology_image.height(), self.histology_image.width()),
                    dtype=np.uint8,
                )
                + alpha
            ).tobytes(),
            self.histology_image.width(),
            self.histology_image.height(),
            self.histology_image.width(),
            QtGui.QImage.Format_Alpha8,
        )

        alpha_image = self.histology_image.copy()
        alpha_image.setAlphaChannel(
            self.histology_image.createAlphaMask() and general_alpha
        )
        self.histology_pixmap.setPixmap(QtGui.QPixmap.fromImage(alpha_image))

    @staticmethod
    def convert_8_bit_numpy_to_pixmap(array: np.ndarray) -> QtGui.QPixmap:
        image = QtGui.QImage(
            array.tobytes(),
            array.shape[1],
            array.shape[0],
            array.shape[1],
            QtGui.QImage.Format_Grayscale8,
        )
        return QtGui.QPixmap.fromImage(image)

    @staticmethod
    def compute_scaling(
        old_size: QtCore.QSize | QtCore.QSizeF,
        new_size: QtCore.QSize | QtCore.QSizeF,
        margins: QtCore.QMargins,
    ) -> float:
        return min(
            (new_size.width() - margins.left() - margins.right()) / old_size.width(),
            (new_size.height() - margins.top() - margins.bottom()) / old_size.height(),
        )


class AlignmentButtonDockWidget(QtWidgets.QDockWidget):
    save_button: QtWidgets.QPushButton
    load_button: QtWidgets.QPushButton
    reset_volume: QtWidgets.QPushButton
    reset_histology: QtWidgets.QPushButton

    def __init__(
        self,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.setContentsMargins(10, 0, 10, 10)

        self.setTitleBarWidget(get_dummy_title_bar(self))
        self.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)

        self.save_button = QtWidgets.QPushButton("Save")
        self.load_button = QtWidgets.QPushButton("Load")

        self.reset_volume = QtWidgets.QPushButton("Reset atlas")
        self.reset_histology = QtWidgets.QPushButton("Reset histology")

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.save_button)
        layout.addWidget(self.load_button)
        layout.addWidget(self.reset_volume)
        layout.addWidget(self.reset_histology)

        container_widget = QtWidgets.QWidget()
        container_widget.setLayout(layout)

        self.setWidget(container_widget)
