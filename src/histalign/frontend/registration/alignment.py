# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.maths import (
    convert_sk_transform_to_q_transform,
    get_sk_transform_from_parameters,
)
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

    def move(self, old_position: QtCore.QPointF, new_position: QtCore.QPointF) -> None:
        raise NotImplementedError("Function was not patched.")

    def rotate(self, steps: int) -> None:
        raise NotImplementedError("Function was not patched.")

    def zoom(self, steps: int) -> None:
        raise NotImplementedError("Function was not patched.")

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        self.previous_position = event.scenePos()

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        new_position = event.scenePos()

        self.move(self.previous_position, new_position)

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
        self.reset_volume()
        self.reset_histology()

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

        pixmap = QtGui.QPixmap.fromImage(self.histology_image)

        self.histology_pixmap.setPixmap(pixmap)
        self.update_histology_pixmap()

    def handle_volume_scaling_change(self, size: Optional[QtCore.QSize] = None) -> None:
        size = size or self.size()

        try:
            volume_scale_ratio = self.compute_scaling(
                self.volume_pixmap.pixmap().size(),
                size,
                self.layout().contentsMargins(),
            )
        except ZeroDivisionError:
            return

        self.alignment_settings.volume_scaling = volume_scale_ratio

        sk_transform = get_sk_transform_from_parameters(
            scale=(volume_scale_ratio, volume_scale_ratio),
            # Move coordinate system origin to centre of image
            extra_translation=(
                -self.volume_pixmap.pixmap().width() / 2,
                -self.volume_pixmap.pixmap().height() / 2,
            ),
        )
        q_transform = convert_sk_transform_to_q_transform(sk_transform)
        self.volume_pixmap.setTransform(q_transform)

        self.view.setSceneRect(self.volume_pixmap.sceneBoundingRect())

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

    def reset_volume(self) -> None:
        if hasattr(self, "volume_pixmap"):
            self.volume_pixmap.setPixmap(QtGui.QPixmap())
        else:
            self.volume_pixmap = self.scene.addPixmap(QtGui.QPixmap())
        self.volume_slicer = None

    def reset_histology(self) -> None:
        if hasattr(self, "histology_pixmap"):
            self.histology_pixmap.setPixmap(QtGui.QPixmap())
        else:
            self.histology_pixmap = MovableAndZoomableGraphicsPixmapItem(
                self.scene.addPixmap(QtGui.QPixmap())
            )
            self.histology_pixmap.move = self.handle_mouse_translation
            self.histology_pixmap.rotate = self.rotation_changed.emit
            self.histology_pixmap.zoom = self.zoom_changed.emit

        self.histology_image = QtGui.QImage()
        self.histology_array = np.array([])

    @QtCore.Slot()
    def handle_mouse_translation(
        self, old_position: QtCore.QPointF, new_position: QtCore.QPointF
    ) -> None:
        """Scales a translation from scene coordinates to volume pixmap coordinates.

        Args:
            old_position (QtCore.QPoint): Previous position in scene coordinates.
            new_position (QtCore.QPoint): Current position in scene coordinates.
        """
        old_volume_coordinates = self.volume_pixmap.mapFromScene(old_position)
        new_volume_coordinates = self.volume_pixmap.mapFromScene(new_position)

        self.translation_changed.emit(
            QtCore.QPoint(
                round(new_volume_coordinates.x()) - round(old_volume_coordinates.x()),
                round(new_volume_coordinates.y()) - round(old_volume_coordinates.y()),
            )
        )

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

        # Construct an skimage `AffineTransform` instead of directly making a PySide
        # `QTransform` as PySide seems to have weird interactions between shearing
        # and translating, leading to shearing influencing the translation cells of
        # the transformation matrix. We therefore create an skimage transform and
        # then use its matrix to construct a `QTransform`.
        sk_transform = get_sk_transform_from_parameters(
            scale=(
                scale_ratio * self.histology_settings.scale_x,
                scale_ratio * self.histology_settings.scale_y,
            ),
            shear=(
                self.histology_settings.shear_x,
                self.histology_settings.shear_y,
            ),
            rotation=self.histology_settings.rotation,
            # Adjust by the volume scaling so that translation is relative and remains
            # relatively the same with resizing.
            translation=(
                self.histology_settings.translation_x
                * self.alignment_settings.volume_scaling,
                self.histology_settings.translation_y
                * self.alignment_settings.volume_scaling,
            ),
            # Move coordinate system origin to centre of image
            extra_translation=(
                -self.histology_pixmap.pixmap().width() / 2,
                -self.histology_pixmap.pixmap().height() / 2,
            ),
        )
        q_transform = convert_sk_transform_to_q_transform(sk_transform)

        self.histology_pixmap.setTransform(q_transform)

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
        width_margin = margins.left() + margins.right()
        height_margin = margins.top() + margins.bottom()

        return min(
            (new_size.width() - width_margin) / (old_size.width() - width_margin),
            (new_size.height() - height_margin) / (old_size.height() - height_margin),
        )
