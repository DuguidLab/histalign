# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
import math
from typing import Optional

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from skimage.transform import AffineTransform, estimate_transform

from histalign.backend.maths import (
    convert_q_transform_to_sk_transform,
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

_module_logger = logging.getLogger(__name__)


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

    def compute_current_histology_transform(self) -> AffineTransform:
        scale_ratio = self.compute_scaling(
            self.histology_pixmap.pixmap().size(),
            self.volume_pixmap.sceneBoundingRect().size(),
            self.layout().contentsMargins(),
        )
        self.alignment_settings.histology_scaling = scale_ratio

        return get_sk_transform_from_parameters(
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
    def update_alignment_from_landmark_registration(
        self, transform: AffineTransform
    ) -> None:
        scale_ratio = self.compute_scaling(
            self.histology_pixmap.pixmap().size(),
            self.volume_pixmap.sceneBoundingRect().size(),
            self.layout().contentsMargins(),
        )
        current_transform = get_sk_transform_from_parameters(
            scale=(
                scale_ratio,
                scale_ratio,
            ),
            extra_translation=(
                -self.histology_pixmap.pixmap().width() / 2,
                -self.histology_pixmap.pixmap().height() / 2,
            ),
        )

        transform = AffineTransform(transform.params @ current_transform.inverse.params)

        settings = self.alignment_settings.histology_settings

        settings.scale_x, settings.scale_y = transform.scale.tolist()
        settings.rotation = math.degrees(transform.rotation)
        settings.translation_x, settings.translation_y = (
            np.round(transform.translation / self.alignment_settings.volume_scaling)
            .astype(int)
            .tolist()
        )

        # Shear requires some more computation as scikit-image returns an angle and Qt
        # expects a coordinate shift.
        # See `maths.get_sk_transform_from_parameters` for more details.
        shear_x = transform.shear
        # This formula is obtained from rearranging CAH (SOHCAHTOA) to find A which
        # corresponds to the coordinate shift derived from the shearing angle.
        shear_x = math.sqrt((1 / math.cos(shear_x)) ** 2 - 1)
        shear_x *= -1 if transform.shear > 0 else 1
        settings.shear_x, settings.shear_y = shear_x, 0

        self.update_histology_pixmap()

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

        # Construct an skimage `AffineTransform` instead of directly making a PySide
        # `QTransform` as PySide seems to have weird interactions between shearing
        # and translating, leading to shearing influencing the translation cells of
        # the transformation matrix. We therefore create an skimage transform and
        # then use its matrix to construct a `QTransform`.
        sk_transform = self.compute_current_histology_transform()
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


class CoordinateWidget(QtWidgets.QFrame):
    source_coordinates: Optional[QtCore.QPointF]
    destination_coordinates: Optional[QtCore.QPointF]

    source_label: QtWidgets.QLabel
    destination_label: QtWidgets.QLabel

    selected: QtCore.Signal = QtCore.Signal()
    deleted: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        source_coordinates: Optional[QtCore.QPointF] = None,
        destination_coordinates: Optional[QtCore.QPointF] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        #
        self.source_coordinates = source_coordinates
        self.destination_coordinates = destination_coordinates

        #
        if source_coordinates is None:
            text = "Source coordinate"
        else:
            text = f"({source_coordinates.x():.0f}, {source_coordinates.y():.0f})"
        source_label = QtWidgets.QLabel(text)

        self.source_label = source_label

        #
        if destination_coordinates is None:
            text = "Destination coordinate"
        else:
            text = f"({destination_coordinates.x():.0f}, {destination_coordinates.y():.0f})"
        destination_label = QtWidgets.QLabel(text)

        self.destination_label = destination_label

        #
        delete_button = QtWidgets.QPushButton("X")

        delete_button.setFixedWidth(delete_button.sizeHint().height())

        delete_button.clicked.connect(self.deleteLater)
        delete_button.clicked.connect(self.deleted.emit)

        self.delete_button = delete_button

        #
        layout = QtWidgets.QGridLayout()

        layout.addWidget(source_label, 0, 0)
        layout.addWidget(destination_label, 0, 1)
        layout.addWidget(delete_button, 0, 2)

        self.setLayout(layout)

        #
        self.setFrameStyle(
            QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised
        )

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent):
        match event.type():
            case QtCore.QEvent.Type.MouseButtonPress:
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self.selected.emit()
                    return True

        return super().eventFilter(watched, event)


class LandmarkCoordinatesWidget(QtWidgets.QScrollArea):
    count_changed: QtCore.Signal = QtCore.Signal(int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self.coordinates_count = 0
        self.coordinate_widgets = []

        #
        headers_widget = CoordinateWidget()

        size_policy = headers_widget.delete_button.sizePolicy()
        size_policy.setRetainSizeWhenHidden(True)
        headers_widget.delete_button.setSizePolicy(size_policy)

        headers_widget.delete_button.hide()

        #
        layout = QtWidgets.QVBoxLayout()

        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        layout.addWidget(headers_widget)

        #
        widget = QtWidgets.QWidget()

        widget.setLayout(layout)

        #
        self.setWidget(widget)

        #
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

    def add_entry(self, baseline: QtCore.QPointF, actual: QtCore.QPointF) -> None:
        coordinates_widget = CoordinateWidget(baseline, actual)
        coordinates_widget.deleted.connect(
            lambda: self.coordinate_widgets.remove(coordinates_widget)
        )
        coordinates_widget.deleted.connect(self.decrement_count)
        self.coordinate_widgets.append(coordinates_widget)

        self.widget().layout().addWidget(coordinates_widget)

        self.increment_count()

    @QtCore.Slot()
    def increment_count(self) -> None:
        self.coordinates_count += 1
        self.count_changed.emit(self.coordinates_count)

    @QtCore.Slot()
    def decrement_count(self) -> None:
        self.coordinates_count -= 1
        self.count_changed.emit(self.coordinates_count)


class LandmarkRegistrationGraphicsView(QtWidgets.QGraphicsView):
    def __init__(
        self,
        scene: QtWidgets.QGraphicsScene,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(scene, parent)

        #
        self.previous_position = None
        self.dragging = -1  # Whether user is currently dragging
        self.scale_delta = 0  # Individual scaling delta from user input
        self.x_delta = 0  # Individual X translation delta from user input
        self.y_delta = 0  # Individual Y translation delta from user input

        #
        # Receive all mouse mouse events
        self.setMouseTracking(True)
        # Allow translation
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)

        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        event.ignore()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        event.ignore()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        event.ignore()

    def wheelEvent(self, event: QtGui.QScrollEvent) -> None:
        event.ignore()


class PreviewWindow(QtWidgets.QMainWindow):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        scene = QtWidgets.QGraphicsScene()

        self.scene = scene

        #
        view = QtWidgets.QGraphicsView(scene)

        view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.view = view

        #
        self.reference_pixmap_item = scene.addPixmap(QtGui.QPixmap())
        self.histology_pixmap_item = scene.addPixmap(QtGui.QPixmap())

        #
        self.setCentralWidget(view)

    def update_reference_pixmap(
        self, pixmap: QtGui.QPixmap, transform: QtGui.QTransform
    ) -> None:
        self.reference_pixmap_item.setPixmap(pixmap)
        self.reference_pixmap_item.setTransform(transform)
        self.view.setSceneRect(self.reference_pixmap_item.sceneBoundingRect())

    def update_histology_pixmap(
        self, pixmap: QtGui.QPixmap, transform: QtGui.QTransform
    ) -> None:
        self.histology_pixmap_item.setPixmap(pixmap)
        self.histology_pixmap_item.setTransform(transform)


class LandmarkRegistrationWindow(QtWidgets.QMainWindow):
    applied: QtCore.Signal = QtCore.Signal(AffineTransform)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        reference_scene = QtWidgets.QGraphicsScene()

        self.reference_scene = reference_scene

        #
        reference_view = LandmarkRegistrationGraphicsView(reference_scene)

        reference_view.installEventFilter(self)

        reference_view.setObjectName("reference_view")

        self.reference_view = reference_view

        #
        reference_pixmap_item = reference_scene.addPixmap(QtGui.QPixmap())

        self.reference_pixmap_item = reference_pixmap_item

        #
        histology_scene = QtWidgets.QGraphicsScene()

        self.histology_scene = histology_scene

        #
        histology_view = LandmarkRegistrationGraphicsView(histology_scene)

        histology_view.setMouseTracking(True)
        histology_view.installEventFilter(self)
        histology_view.setTransformationAnchor(  # Allow dragging
            QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor
        )

        histology_view.setObjectName("histology_view")

        self.histology_view = histology_view

        #
        histology_pixmap_item = histology_scene.addPixmap(QtGui.QPixmap())

        self.histology_pixmap_item = histology_pixmap_item

        #
        landmark_coordinates_widget = LandmarkCoordinatesWidget()

        landmark_coordinates_widget.count_changed.connect(
            lambda count: self.apply_button.setEnabled(count >= 9)
        )

        self.landmark_coordinates_widget = landmark_coordinates_widget

        #
        apply_button = QtWidgets.QPushButton("Apply")

        apply_button.clicked.connect(
            lambda: self.applied.emit(
                self.estimate_histology_transform(as_sk_transform=True)
            )
        )
        apply_button.clicked.connect(self.close)

        apply_button.setEnabled(False)

        self.apply_button = apply_button

        #
        preview_button = QtWidgets.QPushButton("Preview")

        preview_button.clicked.connect(self.show_preview)

        self.preview_button = preview_button

        #
        cancel_button = QtWidgets.QPushButton("Cancel")

        cancel_button.clicked.connect(self.close)

        self.cancel_button = cancel_button

        #
        control_layout = QtWidgets.QGridLayout()

        control_layout.addWidget(landmark_coordinates_widget, 0, 0, 1, -1)
        control_layout.addWidget(apply_button, 1, 0)
        control_layout.addWidget(preview_button, 1, 1)
        control_layout.addWidget(cancel_button, 1, 2)

        #
        layout = QtWidgets.QGridLayout()

        layout.addWidget(reference_view, 0, 0)
        layout.addWidget(histology_view, 1, 0)
        layout.addLayout(control_layout, 0, 1, -1, 1)

        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 2)
        layout.setRowStretch(0, 1)
        layout.setRowStretch(1, 1)

        #
        widget = QtWidgets.QWidget()

        widget.setLayout(layout)

        self.setCentralWidget(widget)

        #
        self.setWindowTitle("Landmark Registration")

    def update_reference_pixmap(
        self, pixmap_item: QtWidgets.QGraphicsPixmapItem
    ) -> None:
        self.reference_pixmap_item.setPixmap(pixmap_item.pixmap())
        self.reference_pixmap_item.setTransform(pixmap_item.transform())
        self.reference_view.setSceneRect(self.reference_pixmap_item.sceneBoundingRect())

    def update_histology_pixmap(
        self, pixmap_item: QtWidgets.QGraphicsPixmapItem
    ) -> None:
        self.histology_pixmap_item.setPixmap(pixmap_item.pixmap())
        self.histology_pixmap_item.setTransform(pixmap_item.transform())
        self.histology_view.setSceneRect(self.histology_pixmap_item.sceneBoundingRect())

    def compute_and_apply_view_transform(self) -> None:
        self._compute_and_apply_view_transform(
            self.reference_view, self.reference_pixmap_item
        )
        self._compute_and_apply_view_transform(
            self.histology_view, self.histology_pixmap_item
        )

    def _compute_and_apply_view_transform(
        self,
        view: LandmarkRegistrationGraphicsView,
        pixmap_item: QtWidgets.QGraphicsPixmapItem,
    ) -> None:
        view_size = view.viewport().size()
        scene_rect = pixmap_item.sceneBoundingRect()
        scene_rect.moveTo(0, 0)

        view_scale = min(
            view_size.width() / scene_rect.width(),
            view_size.height() / scene_rect.height(),
        )
        view_scale += view.scale_delta

        view.setTransform(
            QtGui.QTransform()
            .translate(view.x_delta, view.y_delta)
            .scale(view_scale, view_scale)
        )

    def add_landmark_coordinates(self) -> None:
        if not hasattr(self, "_baseline") or not hasattr(self, "_actual"):
            return

        self.landmark_coordinates_widget.add_entry(self._baseline, self._actual)

        del self._baseline
        del self._actual

    def collect_transform_points(self) -> tuple[np.ndarray, np.ndarray]:
        baseline_coordinates = np.vstack(
            [
                np.array([widget.source_coordinates.x(), widget.source_coordinates.y()])
                for widget in self.landmark_coordinates_widget.coordinate_widgets
            ]
        )
        actual_coordinates = np.vstack(
            [
                np.array(
                    [
                        widget.destination_coordinates.x(),
                        widget.destination_coordinates.y(),
                    ]
                )
                for widget in self.landmark_coordinates_widget.coordinate_widgets
            ]
        )

        return baseline_coordinates, actual_coordinates

    def estimate_raw_histology_transform(
        self, as_sk_transform: bool = False
    ) -> AffineTransform | QtGui.QTransform:
        baseline, actual = self.collect_transform_points()
        sk_transform: AffineTransform = estimate_transform(
            "affine", baseline, actual
        ).inverse

        if as_sk_transform:
            return sk_transform
        else:
            return convert_sk_transform_to_q_transform(sk_transform)

    def estimate_histology_transform(
        self, as_sk_transform: bool = False
    ) -> AffineTransform | QtGui.QTransform:
        transform = AffineTransform(
            convert_q_transform_to_sk_transform(
                self.reference_pixmap_item.transform()
            ).params
            @ self.estimate_raw_histology_transform(as_sk_transform=True).params
        )

        if as_sk_transform:
            return transform
        else:
            return convert_sk_transform_to_q_transform(transform)

    def show_preview(self) -> None:
        window = PreviewWindow(self)

        window.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)

        window.update_reference_pixmap(
            self.reference_pixmap_item.pixmap(), self.reference_pixmap_item.transform()
        )
        window.update_histology_pixmap(
            self.histology_pixmap_item.pixmap(), self.estimate_histology_transform()
        )

        window.show()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        self.compute_and_apply_view_transform()

        super().showEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self.compute_and_apply_view_transform()

        super().resizeEvent(event)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if not isinstance(watched, QtWidgets.QGraphicsView):
            return super().eventFilter(watched, event)

        match event.type():
            # Handle zooming
            case QtCore.QEvent.Type.Wheel:

                if event.angleDelta().y() > 0:  # Scroll up
                    watched.scale_delta += 0.05
                elif event.angleDelta().y() < 0:  # Scroll down
                    watched.scale_delta -= 0.05
                else:  # Could be horizontal scrolling
                    return super().eventFilter(watched, event)

                self.compute_and_apply_view_transform()
                return True
            # Handle dragging
            case QtCore.QEvent.Type.MouseButtonPress:
                position = event.pos()

                watched.dragging = 0
                watched.previous_position = position

                return True
            case QtCore.QEvent.Type.MouseButtonRelease:
                if watched.dragging != 1:
                    if watched.objectName() == "reference_view":
                        view = self.reference_view
                    elif watched.objectName() == "histology_view":
                        view = self.histology_view
                    else:
                        _module_logger.warning(
                            "Watched object was not an expected view."
                        )
                        return super().eventFilter(watched, event)

                    scene_position = view.mapToScene(
                        view.mapFromGlobal(event.globalPos())
                    )

                    if watched.objectName() == "reference_view":
                        pixmap_position = self.reference_pixmap_item.mapFromScene(
                            scene_position
                        )
                        self._baseline = pixmap_position
                    elif watched.objectName() == "histology_view":
                        pixmap_position = self.histology_pixmap_item.mapFromScene(
                            scene_position
                        )
                        self._actual = pixmap_position

                    self.add_landmark_coordinates()

                watched.dragging = -1

                return True
            case QtCore.QEvent.Type.MouseMove:
                if watched.dragging == -1:
                    return super().eventFilter(watched, event)

                if watched.dragging == 0:
                    watched.dragging = 1

                new_position = event.pos()

                watched.x_delta += new_position.x() - watched.previous_position.x()
                watched.y_delta += new_position.y() - watched.previous_position.y()

                watched.previous_position = new_position

                self.compute_and_apply_view_transform()
                return True

        return super().eventFilter(watched, event)
