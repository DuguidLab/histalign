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
from histalign.backend.preprocessing import simulate_auto_contrast_passes
from histalign.backend.workspace import VolumeSlicer
from histalign.frontend.pyside_helpers import get_colour_table


class MovableAndZoomableGraphicsPixmapItem(QtWidgets.QGraphicsPixmapItem):
    """A movable and zoomable class for QGraphicsPixmapItem.

    This is not suitable for `common_widgets.py` because of a bit of spaghetti code.
    Since QGraphicsItems are not QObjects, they cannot have signals. The workaround is
    to have them call a function which is patched through by the parent to emit a
    signal.
    """

    previous_position: Optional[QtCore.QPointF] = None

    def move(self, translation: QtCore.QPoint) -> None:
        raise NotImplementedError("Function was not patched.")

    def rotate(self, steps: int) -> None:
        raise NotImplementedError("Function was not patched.")

    def zoom(self, steps: int) -> None:
        raise NotImplementedError("Function was not patched.")

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        self.previous_position = event.scenePos()

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        new_position = event.scenePos()

        movement = new_position - self.previous_position
        self.move(QtCore.QPoint(round(movement.x()), round(movement.y())))

        self.previous_position = new_position

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        self.previous_position = None

    def wheelEvent(self, event: QtWidgets.QGraphicsSceneWheelEvent):
        modifiers = event.modifiers()
        modified = modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier
        if event.delta() > 0:
            direction_multiplier = 1
        elif event.delta() < 0:
            direction_multiplier = -1
        else:  # Horizontal scrolling
            return super().eventFilter(watched, event)

        # TODO: Avoid hard-coding 5x for modifier here and in `settings.py`
        if modified:
            direction_multiplier *= 5

        if modifiers & QtCore.Qt.KeyboardModifier.AltModifier:
            self.rotate(direction_multiplier)
        else:
            self.zoom(direction_multiplier)


class AlignmentWidget(QtWidgets.QWidget):
    background_threshold: int = 0
    global_alpha: int = 255
    lut: str = str
    auto_contrast_passes: int = 0

    scene: QtWidgets.QGraphicsScene
    view: QtWidgets.QGraphicsView
    volume_pixmap: QtWidgets.QGraphicsPixmapItem
    volume_slicer: Optional[VolumeSlicer] = None
    histology_pixmap: QtWidgets.QGraphicsPixmapItem
    histology_image: QtGui.QImage

    alignment_settings: Optional[AlignmentSettings] = None
    volume_settings: Optional[VolumeSettings] = None
    histology_settings: Optional[HistologySettings] = None

    translation_changed: QtCore.Signal = QtCore.Signal(QtCore.QPoint)
    rotation_changed: QtCore.Signal = QtCore.Signal(int)
    zoom_changed: QtCore.Signal = QtCore.Signal(int)

    def __init__(
        self, lut: str = "grey", parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)

        #
        self.lut = lut

        #
        self.scene = QtWidgets.QGraphicsScene(self)

        self.view = QtWidgets.QGraphicsView(self.scene)
        self.view.setBackgroundBrush(
            QtGui.QBrush(QtWidgets.QApplication.instance().palette().base())
        )
        self.view.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.view.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        #
        self.volume_pixmap = self.scene.addPixmap(QtGui.QPixmap())

        self.histology_pixmap = MovableAndZoomableGraphicsPixmapItem(
            self.scene.addPixmap(QtGui.QPixmap())
        )
        # Step through a lambda to scale the translation properly. Without this, the
        # translation is still correct but is smaller than the mouse movement which
        # is unintuitive from a UX POV.
        self.histology_pixmap.move = lambda x: self.translation_changed.emit(
            QtCore.QPoint(
                x.x() / self.alignment_settings.histology_scaling,
                x.y() / self.alignment_settings.histology_scaling,
            )
        )
        self.histology_pixmap.rotate = self.rotation_changed.emit
        self.histology_pixmap.zoom = self.zoom_changed.emit

        self.histology_image = QtGui.QImage()
        self.histology_array = np.array([])

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.setLayout(layout)

    def prepare_slicer(self) -> None:
        self.volume_slicer = VolumeSlicer(
            path=self.alignment_settings.volume_path,
            resolution=self.alignment_settings.volume_settings.resolution,
        )

    def update_histological_slice(self, array: Optional[np.ndarray]) -> None:
        self.histology_array = array
        self.auto_contrast_passes = 0

        self.update_histology_image(array)

    def update_histology_image(self, array: np.ndarray) -> None:
        if array is None:
            self.histology_image = QtGui.QImage()
        else:
            self.histology_image = QtGui.QImage(
                array.tobytes(),
                array.shape[1],
                array.shape[0],
                array.shape[1],
                QtGui.QImage.Format.Format_Indexed8,
            )
            self.histology_image.setColorTable(
                get_colour_table(self.lut, self.global_alpha, self.background_threshold)
            )

        self.histology_pixmap.setPixmap(QtGui.QPixmap.fromImage(self.histology_image))
        self.update_histology_pixmap()

    def handle_volume_scaling_change(self, size: Optional[QtCore.QSize] = None) -> None:
        size = size or self.size()

        try:
            volume_scale_ratio = self.compute_scaling(
                self.volume_pixmap.pixmap().size(),
                size,
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

    def apply_auto_contrast(self) -> None:
        self.auto_contrast_passes += 1

        new_array, successful = simulate_auto_contrast_passes(
            self.histology_array, self.auto_contrast_passes
        )

        if not successful:
            self.auto_contrast_passes = 0
            new_array = self.histology_array

        self.update_histology_image(new_array)

    def resizeEvent(self, event) -> None:
        self.handle_volume_scaling_change(event.size())

    @QtCore.Slot()
    def update_volume_pixmap(self) -> None:
        pixmap = self.convert_8_bit_numpy_to_pixmap(
            self.volume_slicer.slice(self.volume_settings)
        )
        self.volume_pixmap.setPixmap(pixmap)
        self.handle_volume_scaling_change()

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
            .translate(  # Regular translation
                self.histology_settings.translation_x,
                self.histology_settings.translation_y,
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
    def update_lut(self, new_lut: str) -> None:
        self.lut = new_lut
        self.recompute_colour_map()

    @QtCore.Slot()
    def recompute_colour_map(self) -> None:
        if self.histology_image.isNull():
            return

        self.histology_image.setColorTable(
            get_colour_table(self.lut, self.global_alpha, self.background_threshold)
        )
        self.histology_pixmap.setPixmap(QtGui.QPixmap.fromImage(self.histology_image))

    @QtCore.Slot()
    def update_background_alpha(self, threshold: int) -> None:
        self.background_threshold = threshold
        self.recompute_colour_map()

    @QtCore.Slot()
    def update_global_alpha(self, alpha: int) -> None:
        self.global_alpha = alpha
        self.recompute_colour_map()

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
