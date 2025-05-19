# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
import math
from typing import Optional

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
import shiboken6
from skimage.transform import AffineTransform, estimate_transform

from histalign.backend.maths import (
    convert_q_transform_to_sk_transform,
    convert_sk_transform_to_q_transform,
    decompose_sk_transform,
    get_sk_transform_from_parameters,
    normalise_array,
    simulate_auto_contrast_passes,
)
from histalign.backend.models import (
    AlignmentSettings,
    HistologySettings,
    Orientation,
    VolumeSettings,
)
from histalign.backend.workspace import VolumeSlicer
from histalign.frontend.common_widgets import PointGraphicsItem, ZoomAndPanView
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

        if self.previous_position is None:
            return
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
            return super().wheelEvent(event)

        # TODO: Avoid hard-coding 5x for modifier here and in `settings.py`
        if modified:
            direction_multiplier *= 5

        if modifiers & QtCore.Qt.KeyboardModifier.AltModifier:
            if (
                modifiers
                & ~QtCore.Qt.KeyboardModifier.AltModifier
                & ~QtCore.Qt.KeyboardModifier.ShiftModifier
            ):
                # Don't rotate if another modifier than ALT(+SHIFT) is pressed
                return
            self.rotate(direction_multiplier)
        else:
            self.zoom(direction_multiplier)


class AlignmentWidget(QtWidgets.QWidget):
    background_threshold: int = 0
    global_alpha: int = 255
    lut: str = str
    auto_contrast_passes: int = 0

    scene: QtWidgets.QGraphicsScene
    view: ZoomAndPanView
    volume_pixmap: QtWidgets.QGraphicsPixmapItem
    volume_slicer: Optional[VolumeSlicer] = None
    histology_pixmap: QtWidgets.QGraphicsPixmapItem
    histology_image: QtGui.QImage
    histology_array: Optional[np.ndarray] = None

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
        self.scene = QtWidgets.QGraphicsScene(
            QtCore.QRectF(-100_000, -100_000, 200_000, 200_000),  # Make "infinite"
            self,
        )

        self.view = ZoomAndPanView(self.scene)
        self.view.setBackgroundBrush(
            QtGui.QBrush(QtWidgets.QApplication.instance().palette().base())
        )
        self.view.set_drag_button(QtCore.Qt.MouseButton.MiddleButton)
        self.view.set_zoom_modifier(QtCore.Qt.KeyboardModifier.ControlModifier)

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
        if self.auto_contrast_passes > 0:
            self.auto_contrast_passes -= 1
            self.apply_auto_contrast(force=True)
        else:
            self.update_histology_image(array)

    def update_histology_image(self, array: Optional[np.ndarray]) -> None:
        if array is None:
            self.histology_image = QtGui.QImage()
        else:
            # Ensure images are 8-bit as that's the only way to have an indexed format
            # and the indexed format allows LUTs.
            if array.dtype != np.uint8:
                array = normalise_array(array, np.uint8)

            self.histology_image = QtGui.QImage(
                array.tobytes(),
                array.shape[1],
                array.shape[0],
                array.shape[1],
                QtGui.QImage.Format.Format_Indexed8,
            )
            self.histology_image.setColorTable(
                get_colour_table(
                    self.lut, self.global_alpha, self.background_threshold
                ).tolist()
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

        self.update_histology_pixmap()

    def apply_auto_contrast(self, force: bool = False) -> None:
        """Applies ImageJ's auto-threshold algorithm on the current image.

        Args:
            force (bool, optional):
                Whether to force the image to be thresholded when the passes count is
                too high for a successful thresholding. In that case, the smallest
                successful passes count will be used. This can mean no thresholding is
                applied if no passes count greater than 0 is successful.
        """
        if self.histology_array is None:
            return

        self.auto_contrast_passes += 1

        new_array, successful = simulate_auto_contrast_passes(
            self.histology_array, self.auto_contrast_passes
        )

        if not successful:
            if force and self.auto_contrast_passes > 1:
                self.auto_contrast_passes -= 2
                self.apply_auto_contrast(force)
                return
            self.auto_contrast_passes = 0
            new_array = self.histology_array

        self.update_histology_image(new_array)

    def compute_current_histology_transform(self) -> AffineTransform:
        scale_ratio = self.compute_scaling(
            self.histology_pixmap.pixmap().size(),
            self.volume_pixmap.sceneBoundingRect().size(),
            self.layout().contentsMargins(),
        )

        match self.volume_settings.orientation:
            case Orientation.CORONAL:
                factor = 2
            case Orientation.HORIZONTAL:
                factor = 1.5
            case Orientation.SAGITTAL:
                factor = 1.7
        scale_ratio /= factor

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

    def reset_auto_contrast(self) -> None:
        self.auto_contrast_passes = 0

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
        match self.volume_settings.orientation:
            case Orientation.CORONAL:
                factor = 2
            case Orientation.HORIZONTAL:
                factor = 1.5
            case Orientation.SAGITTAL:
                factor = 1.7
        scale_ratio /= factor
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

        components = decompose_sk_transform(transform)
        settings.scale_x, settings.scale_y = components[:2]
        settings.shear_x, settings.shear_y = components[2:4]
        settings.rotation = components[4]
        settings.translation_x, settings.translation_y = (
            np.round(np.array(components[5:]) / self.alignment_settings.volume_scaling)
            .astype(int)
            .tolist()
        )

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
    def update_volume_pixmap(self, rescale: bool = False) -> None:
        pixmap = self.convert_8_bit_numpy_to_pixmap(
            self.volume_slicer.slice(self.volume_settings)
        )

        self.volume_pixmap.setPixmap(pixmap)
        if rescale:
            self.handle_volume_scaling_change()
            match self.volume_settings.orientation:
                case Orientation.CORONAL:
                    self.view.general_zoom = 2.0
                case Orientation.HORIZONTAL:
                    self.view.general_zoom = 1.5
                case Orientation.SAGITTAL:
                    self.view.general_zoom = 1.7

        self.view.set_focus_rect(
            self.volume_pixmap.sceneBoundingRect(), reset_general_zoom=False
        )

        if rescale:
            self.view.centre_on_focus()

        self.view.update_focus_zoom()

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


class CoordinatesWidget(QtWidgets.QFrame):
    """Widget displaying reference and histology coordinates.

    Attributes:
        reference_coordinates (Optional[QtCore.QPoint]):
            Coordinates of the reference point.
        histology_coordinates (Optional[QtCore.QPoint]):
            Coordinates of the histology point.
        reference_label (QtWidgets.QLabel): Label displaying the reference coordinates.
        histology_label (QtWidgets.QLabel): Label displaying the histology coordinates.
    """

    reference_coordinates: Optional[QtCore.QPoint]
    histology_coordinates: Optional[QtCore.QPoint]

    reference_label: QtWidgets.QLabel
    histology_label: QtWidgets.QLabel

    selected: QtCore.Signal = QtCore.Signal()
    removed: QtCore.Signal = QtCore.Signal()
    deleted: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        source_coordinates: Optional[QtCore.QPoint] = None,
        destination_coordinates: Optional[QtCore.QPoint] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        #
        self.reference_coordinates = source_coordinates
        self.histology_coordinates = destination_coordinates

        #
        self.installEventFilter(self)

        #
        source_label = QtWidgets.QLabel()

        self.reference_label = source_label
        self.update_reference_coordinates(source_coordinates)

        #
        destination_label = QtWidgets.QLabel()

        self.histology_label = destination_label
        self.update_histology_coordinates(destination_coordinates)

        #
        delete_button = QtWidgets.QPushButton("X")

        delete_button.setFixedWidth(delete_button.sizeHint().height())

        delete_button.clicked.connect(self.removed.emit)

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

    def update_reference_coordinates(
        self, coordinates: Optional[QtCore.QPoint]
    ) -> None:
        """Updates reference coordinates with new coordinates.

        Args:
            coordinates (QtCore.QPoint): New coordinates.
        """
        if coordinates is None:
            text = "Reference coordinates"
        else:
            text = f"({coordinates.x()}, {coordinates.y()})"
        self.reference_label.setText(text)
        self.reference_coordinates = coordinates

    def update_histology_coordinates(
        self, coordinates: Optional[QtCore.QPoint]
    ) -> None:
        """Updates histology coordinates with new coordinates.

        Args:
            coordinates (QtCore.QPoint): New coordinates.
        """
        if coordinates is None:
            text = "Histology coordinates"
        else:
            text = f"({coordinates.x()}, {coordinates.y()})"
        self.histology_label.setText(text)
        self.histology_coordinates = coordinates

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Handles events received by the watched widget.

        Args:
            watched (QtCore.QObject): Watched widget.
            event (QtCore.QEvent): Event received by the watched widget.

        Returns:
            bool: Whether the event wa handled or should be propagated.
        """
        match event.type():
            case QtCore.QEvent.Type.MouseButtonPress:
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self.selected.emit()
                    return True

        return super().eventFilter(watched, event)

    def deleteLater(self) -> None:
        """Schedules the widget for deletion."""
        super().deleteLater()
        self.deleted.emit()


class LandmarkCoordinatesWidget(QtWidgets.QScrollArea):
    """Scroll area displaying the current coordinates widgets.

    Attributes:
        widgets_count (int): Number of coordinates widget.
        coordinates_widgets (dict[str, CoordinatesWidget]):
            Mapping associating a coordinates widget's ID to itself.
    """

    count_changed: QtCore.Signal = QtCore.Signal(int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self.widgets_count = 0
        self.coordinate_widgets: dict[str, CoordinatesWidget] = {}

        #
        headers_widget = CoordinatesWidget()

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

    def add_entry(
        self, reference_coordinates: QtCore.QPoint, histology_coordinates: QtCore.QPoint
    ) -> CoordinatesWidget:
        """Adds a coordinates widget from the reference and histology coordinates.

        Args:
            reference_coordinates (QtCore.QPoint): Coordinates of the reference point.
            histology_coordinates (QtCore.QPoint): Coordinates of the histology point.

        Returns:
            CoordinatesWidget: The newly-created widget.
        """
        coordinates_widget = CoordinatesWidget(
            reference_coordinates, histology_coordinates
        )

        widget_id = hex(id(coordinates_widget))

        coordinates_widget.deleted.connect(
            lambda: self.coordinate_widgets.pop(widget_id)
        )
        coordinates_widget.deleted.connect(self.decrement_count)

        self.coordinate_widgets[widget_id] = coordinates_widget

        self.widget().layout().addWidget(coordinates_widget)

        self.increment_count()

        return coordinates_widget

    @QtCore.Slot()
    def increment_count(self) -> None:
        """Increments the widgets count."""
        self.widgets_count += 1
        self.count_changed.emit(self.widgets_count)

    @QtCore.Slot()
    def decrement_count(self) -> None:
        """Decrements the widgets count."""
        self.widgets_count -= 1
        self.count_changed.emit(self.widgets_count)


class PreviewWindow(QtWidgets.QMainWindow):
    """Landmark registration preview GUI window.

    This provides a way to display the current effect of the landmark registration
    without applying them to the main registration window directly.

    Attributes:
        scene (QtWidgets.QGraphicsScene): Scene to put the pixmaps into.
        view (ZoomAndPanView): View on the scene.
        reference_pixmap_item (QtWidgets.QGraphicsPixmapItem):
            Pixmap item of the reference (typically the atlas) slice.
        histology_pixmap_item (QtWidgets.QGraphicsPixmapItem):
            Pixmap item of the histology image.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        scene = QtWidgets.QGraphicsScene(
            QtCore.QRectF(-100_000, -100_000, 200_000, 200_000)  # Make "infinite"
        )

        self.scene = scene

        #
        view = ZoomAndPanView(scene)

        self.view = view

        #
        self.reference_pixmap_item = scene.addPixmap(QtGui.QPixmap())
        self.histology_pixmap_item = scene.addPixmap(QtGui.QPixmap())

        #
        self.setCentralWidget(view)

    def update_reference_pixmap(
        self, pixmap: QtGui.QPixmap, transform: QtGui.QTransform
    ) -> None:
        """Updates the reference pixmap with the given pixmap and transform.

        Args:
            pixmap (QtGui.QPixmap): Pixmap to display.
            transform (QtGui.QTransform): Transform to apply to the pixmap item.
        """

        self.reference_pixmap_item.setPixmap(pixmap)
        self.reference_pixmap_item.setTransform(transform)

        self.view.set_focus_rect(self.reference_pixmap_item.sceneBoundingRect())
        self.view.centerOn(self.reference_pixmap_item.sceneBoundingRect().center())

    def update_histology_pixmap(
        self, pixmap: QtGui.QPixmap, transform: QtGui.QTransform
    ) -> None:
        """Updates the histology pixmap with the given pixmap and transform.

        Args:
            pixmap (QtGui.QPixmap): Pixmap to display.
            transform (QtGui.QTransform): Transform to apply to the pixmap item.
        """
        self.histology_pixmap_item.setPixmap(pixmap)
        self.histology_pixmap_item.setTransform(transform)


class LandmarkRegistrationWindow(QtWidgets.QMainWindow):
    """Landmark registration main GUI window.

    The window consists of two views stacked on top of each other on the left and a
    landmark tracker on the right.

    The user can interact (zoom and pan) the views and click on them to place a marker.
    Once markers exist in both views, they are paired and added to the list of
    landmarks. The user can repeat this as many times as they want or move the already-
    present points.

    To check their progress, the user can use the "Preview" button to get an idea of
    what the currently estimated transform looks like. If they are happy with the
    result, they can "Apply" which applies the transform on the original alignment
    window and closes the landmark registration. If not, the user can cancel.

    Attributes:
        reference_scene (QtWidgets.QGraphicsScene):
            Scene for the reference (typically atlas) workspace.
        reference_view (ZoomAndPanView):
            View for the reference (typically atlas) workspace.
        reference_pixmap_item (QtWidgets.QGraphicsPixmapItem):
            Pixmap item of the reference (typically atlas) slice.
        histology_scene (QtWidgets.QGraphicsScene):
            Scene for the histology workspace.
        histology_view (ZoomAndPanView):
            View for the histology workspace.
        histology_pixmap_item (QtWidgets.QGraphicsPixmapItem):
            Pixmap item of the histology image to align.
    """

    applied: QtCore.Signal = QtCore.Signal(AffineTransform)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self._reference_point: Optional[PointGraphicsItem] = None
        self._histology_point: Optional[PointGraphicsItem] = None
        self._ignore_next_click: bool = False

        self._point_to_widget_map: dict[tuple[str, str], CoordinatesWidget] = {}
        self._widget_to_point_map: dict[
            str, tuple[PointGraphicsItem, PointGraphicsItem]
        ] = {}

        #
        reference_scene = QtWidgets.QGraphicsScene(
            QtCore.QRectF(-100_000, -100_000, 200_000, 200_000)  # Make "infinite"
        )

        self.reference_scene = reference_scene

        #
        reference_view = ZoomAndPanView(reference_scene)

        reference_view.clicked.connect(self.process_click)

        self.reference_view = reference_view

        #
        self.reference_pixmap_item = reference_scene.addPixmap(QtGui.QPixmap())

        #
        histology_scene = QtWidgets.QGraphicsScene(
            QtCore.QRectF(-100_000, -100_000, 200_000, 200_000)
        )  # Make "infinite"

        self.histology_scene = histology_scene

        #
        histology_view = ZoomAndPanView(histology_scene)

        histology_view.clicked.connect(self.process_click)

        self.histology_view = histology_view

        #
        self.histology_pixmap_item = histology_scene.addPixmap(QtGui.QPixmap())

        #
        apply_button = QtWidgets.QPushButton("Apply")

        apply_button.clicked.connect(
            lambda: self.applied.emit(
                self.estimate_histology_transform(as_sk_transform=True)
            )
        )
        apply_button.clicked.connect(self.close)

        apply_button.setEnabled(False)

        #
        preview_button = QtWidgets.QPushButton("Preview")

        preview_button.clicked.connect(self.show_preview)

        preview_button.setEnabled(False)

        #
        landmark_coordinates_widget = LandmarkCoordinatesWidget()

        landmark_coordinates_widget.count_changed.connect(
            lambda count: apply_button.setEnabled(count >= 9)
        )
        landmark_coordinates_widget.count_changed.connect(
            lambda count: preview_button.setEnabled(count >= 9)
        )

        self.landmark_coordinates_widget = landmark_coordinates_widget

        #
        cancel_button = QtWidgets.QPushButton("Cancel")

        cancel_button.clicked.connect(self.close)

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
        self,
        pixmap_item: QtWidgets.QGraphicsPixmapItem,
        general_zoom: float = 1.0,
    ) -> None:
        """Updates the pixmap item shown in the reference (top) view.

        The pixmap item is taken as-is, maintaining the transform.

        Args:
            pixmap_item (QtWidgets.QGraphicsPixmapItem): Pixmap item to update with.
            general_zoom (float, optional): Initial general zoom of the view.
        """
        self.reference_pixmap_item.setPixmap(pixmap_item.pixmap())
        self.reference_pixmap_item.setTransform(pixmap_item.transform())

        self.reference_view.general_zoom = general_zoom
        self.reference_view.set_focus_rect(
            self.reference_pixmap_item.sceneBoundingRect(), reset_general_zoom=False
        )

    def update_histology_pixmap(
        self, pixmap_item: QtWidgets.QGraphicsPixmapItem
    ) -> None:
        """Updates the pixmap item shown in the histology (bottom) view.

        The pixmap item is taken as-is, maintaining the transform.

        Args:
            pixmap_item (QtWidgets.QGraphicsPixmapItem): Pixmap item to update with.
        """
        self.histology_pixmap_item.setPixmap(pixmap_item.pixmap())
        self.histology_pixmap_item.setTransform(pixmap_item.transform())

        self.histology_view.set_focus_rect(
            self.histology_pixmap_item.sceneBoundingRect()
        )

    def process_click(self, position: QtCore.QPointF) -> None:
        """Processes a click coming from either of the views.

        The view is identified through `QtCore.QObject.sender()`.

        Args:
            position (QtCore.QPointF): Scene position of the click.
        """
        # Determine which view the click was on
        sender = self.sender()

        if sender is self.reference_view:
            name = "reference"
        elif sender is self.histology_view:
            name = "histology"
        else:
            _module_logger.error(
                "Cannot process click emanating from neither the reference nor "
                "the histology view."
            )
            return

        # Ignore click when user removes selection by clicking away from items
        if self._ignore_next_click:
            self._ignore_next_click = False
            return

        # Extract relevant members
        scene1: QtWidgets.QGraphicsScene = getattr(self, f"{name}_scene")
        pixmap_item1: QtWidgets.QGraphicsPixmapItem = getattr(
            self, f"{name}_pixmap_item"
        )
        graphics_item1: PointGraphicsItem = getattr(self, f"_{name}_point")

        # Don't add a new item if clicking on an existing one
        if isinstance(scene1.itemAt(position, QtGui.QTransform()), PointGraphicsItem):
            return

        if graphics_item1 is not None and shiboken6.isValid(graphics_item1):
            # Move currently unpaired graphics item if clicking on same view again
            graphics_item1.setPos(position)
        else:
            # Otherwise, create new graphics item
            graphics_item1 = PointGraphicsItem(
                position,
                round(min(*pixmap_item1.sceneBoundingRect().size().toTuple()) / 50),
            )
            graphics_item1.clicked.connect(
                lambda x: self.handle_graphics_item_click(x, graphics_item1)
            )
            graphics_item1.deselected.connect(self.ignore_next_click)

            # Add item to the scene
            scene1.addItem(graphics_item1)
            setattr(self, f"_{name}_point", graphics_item1)

        # Check if a matching point exists in the other scene
        other_name = "reference" if name == "histology" else "histology"

        graphics_item2: PointGraphicsItem = getattr(self, f"_{other_name}_point")

        # Early return if no matching point yet
        if graphics_item2 is None:
            return

        # Otherwise, link the points
        graphics_item1.selected.connect(graphics_item2.select)
        graphics_item1.deselected.connect(graphics_item2.deselect)
        graphics_item1.deleted.connect(graphics_item2.deleteLater)

        graphics_item2.selected.connect(graphics_item1.select)
        graphics_item2.deselected.connect(graphics_item1.deselect)
        graphics_item2.deleted.connect(graphics_item1.deleteLater)

        # Create a coordinates widget
        self.create_coordinates_widget()

        # Reset caches
        self._reference_point = None
        self._histology_point = None

    def ignore_next_click(self) -> None:
        """Sets a flag to ignore the next click processing."""
        # If neither has focus, the user clicked outside of both and the next click
        # should not be ignored since no point will be selected at that point.
        if self.reference_view.hasFocus() or self.histology_view.hasFocus():
            self._ignore_next_click = True

    def handle_graphics_item_click(
        self, button: QtCore.Qt.MouseButton, graphics_item: PointGraphicsItem
    ) -> None:
        """Handles clicks other than left clicks on points.

        Currently, this only provides a way to delete points and points pairs by right-
        clicking them.

        Args:
            button (QtCore.Qt.MouseButton): Button that was clicked.
            graphics_item (PointGraphicsItem): Item that emitted the click.
        """
        if button == QtCore.Qt.MouseButton.RightButton:
            self.handle_item_deletion(graphics_item)

    def handle_item_deletion(self, graphics_item: PointGraphicsItem) -> None:
        """Handles deleting points and coordinate widgets.

        If the point has a pair, that pair is also deleted and the corresponding
        coordinates widget is also removed.

        Args:
            graphics_item (PointGraphicsItem): Item to delete.
        """
        graphics_item.delete()

        item_id = hex(id(graphics_item))
        full_key = None
        for key, value in self._point_to_widget_map.items():
            if item_id in key:
                full_key = key

                self._widget_to_point_map.pop(hex(id(value)))
                value.deleteLater()
        # Defer deletion until after iterating
        if full_key is not None:
            self._point_to_widget_map.pop(full_key)

    # noinspection PyTypeChecker
    def create_coordinates_widget(self) -> None:
        """Creates a coordinate widget with the cached points."""
        if self._reference_point is None or self._histology_point is None:
            _module_logger.error(
                "Attempted to create a coordinates widget without valid points."
            )
            return

        # Pixels are drawn from index to index + 1, hence float portion is irrelevant
        reference_pos = self.convert_position_to_coordinates(
            self.reference_pixmap_item.mapFromScene(self._reference_point.pos())
        )
        histology_pos = self.convert_position_to_coordinates(
            self.histology_pixmap_item.mapFromScene(self._histology_point.pos())
        )

        # Create the widget
        widget = self.landmark_coordinates_widget.add_entry(
            reference_pos, histology_pos
        )

        widget.removed.connect(
            lambda x=self._reference_point: self.handle_item_deletion(x)
        )
        widget.selected.connect(lambda x=self._reference_point: self.select_items(x))

        # Update widget when graphics items are moved
        self._reference_point.moved.connect(
            lambda x: widget.update_reference_coordinates(
                self.convert_position_to_coordinates(
                    self.reference_pixmap_item.mapFromScene(x)  # type: ignore[arg-type]
                )
            )
        )
        self._histology_point.moved.connect(
            lambda x: widget.update_histology_coordinates(
                self.convert_position_to_coordinates(
                    self.histology_pixmap_item.mapFromScene(x)  # type: ignore[arg-type]
                )
            )
        )

        # Add to the maps
        self._point_to_widget_map[
            (hex(id(self._reference_point)), (hex(id(self._histology_point))))
        ] = widget
        self._widget_to_point_map[hex(id(widget))] = (
            self._reference_point,
            self._histology_point,
        )

    # noinspection PyTypeChecker
    def select_items(self, item: PointGraphicsItem) -> None:
        """Selects an item and its pair if it has one.

        Note that this clear the current selection.

        Args:
            item (PointGraphicsItem): Item to select.
        """
        self.reference_scene.setFocusItem(None)  # type: ignore[arg-type]
        self.reference_scene.clearSelection()

        self.histology_scene.setFocusItem(None)  # type: ignore[arg-type]
        self.histology_scene.clearSelection()

        item.setSelected(True)

    def collect_transform_points(self) -> tuple[np.ndarray, np.ndarray]:
        """Collects the current transformation points pairs."""
        reference_points = []
        histology_points = []

        for widget in self.landmark_coordinates_widget.coordinate_widgets.values():
            reference_points.append(np.array([*widget.reference_coordinates.toTuple()]))
            histology_points.append(np.array([*widget.histology_coordinates.toTuple()]))

        reference_points = np.vstack(reference_points)
        histology_points = np.vstack(histology_points)

        return reference_points, histology_points

    def estimate_raw_histology_transform(
        self, as_sk_transform: bool = False
    ) -> AffineTransform | QtGui.QTransform:
        """Estimates the histology transform from the current transform points.

        Args:
            as_sk_transform (bool):
                Whether to return the transform as a `scikit-image` transform.

        Returns:
            AffineTransform | QtGui.QTransform: The raw histology transform.
        """
        reference_points, histology_points = self.collect_transform_points()
        sk_transform: AffineTransform = estimate_transform(
            "affine", reference_points, histology_points
        ).inverse

        if as_sk_transform:
            return sk_transform
        else:
            return convert_sk_transform_to_q_transform(sk_transform)

    def estimate_histology_transform(
        self, as_sk_transform: bool = False
    ) -> AffineTransform | QtGui.QTransform:
        """Estimates the histology transform relative to the transformed reference.

        Args:
            as_sk_transform (bool):
                Whether to return the transform as a `scikit-image` transform.

        Returns:
            AffineTransform | QtGui.QTransform: The histology transform.
        """
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
        """Shows the preview GUI given the current transform points."""
        window = PreviewWindow(self)
        window.resize(self.size() * 0.95)

        window.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)

        window.update_reference_pixmap(
            self.reference_pixmap_item.pixmap(), self.reference_pixmap_item.transform()
        )
        window.update_histology_pixmap(
            self.histology_pixmap_item.pixmap(), self.estimate_histology_transform()  # type: ignore[arg-type]
        )

        window.show()

    @staticmethod
    def convert_position_to_coordinates(position: QtCore.QPointF) -> QtCore.QPoint:
        """Converts a scene position into grid coordinates.

        This is especially useful to convert float scene positions into pixmap item
        coordinates.

        Args:
            position (QtCore.QPointF):

        Returns:
            QtCore.QPoint: The grid coordinates.
        """
        position = position.__copy__()

        position.setX(math.floor(position.x()))
        position.setY(math.floor(position.y()))

        return position.toPoint()
