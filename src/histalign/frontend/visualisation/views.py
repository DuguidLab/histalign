# SPDX-FileCopyrightText: 2025-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from contextlib import suppress
import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.ccf import get_atlas_path
from histalign.backend.maths import normalise_array
from histalign.backend.registration import ContourGeneratorThread
from histalign.frontend.common_widgets import BinaryAlphaPixmap, ZoomAndPanView
from histalign.frontend.pyside_helpers import (
    np_to_qpixmap,
    try_show_permanent_status_message,
)
from histalign.io import (
    load_alignment_settings,
    load_volume,
    open_file,
)
from histalign.resources import ICONS_ROOT

_module_logger = logging.getLogger(__name__)


class SliceViewer(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self._alignment_settings = None
        self._histology_item = None

        self._contours = {}
        self._contours_threads = {}

        self._processing_count = 0
        self._status_bar_label = None

        #
        scene = QtWidgets.QGraphicsScene(-100_000, -100_000, 200_000, 200_000, self)

        self.scene = scene

        #
        view = ZoomAndPanView(scene)

        view.setBackgroundBrush(QtCore.Qt.GlobalColor.black)
        view.setContentsMargins(0, 0, 0, 0)

        self.view = view

        #
        layout = QtWidgets.QVBoxLayout()

        layout.addWidget(view)

        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

    def clear_contours(self) -> None:
        for structure in list(self._contours.keys()):
            self.remove_contours(structure)

    def reset(self) -> None:
        self.clear_contours()
        self.set_pixmap(QtGui.QPixmap())

    def set_pixmap(self, pixmap: QtGui.QPixmap) -> None:
        if self._histology_item is not None:
            self.scene.removeItem(self._histology_item)

        pixmap_item = self.scene.addPixmap(pixmap)
        pixmap_item.setZValue(-1)

        self.view.set_focus_rect(pixmap_item.sceneBoundingRect())
        self._histology_item = pixmap_item

    def update_status_bar(self) -> None:
        if self._status_bar_label is not None:
            self._status_bar_label.deleteLater()

        if self._processing_count <= 0:
            self._status_bar_label = None
            return

        self._status_bar_label = try_show_permanent_status_message(
            self.window(),
            f"Processing {self._processing_count} "
            f"contour{'' if self._processing_count == 1 else 's'}...",
        )

    @QtCore.Slot()
    def open_image(self, alignment_path: Path) -> None:
        alignment_settings = load_alignment_settings(alignment_path)
        histology_path = alignment_settings.histology_path

        handle = open_file(histology_path)
        pixmap = np_to_qpixmap(
            normalise_array(handle.read_image(handle.index), np.uint8)
        )

        self.set_pixmap(pixmap)
        self._alignment_settings = alignment_settings

        self.clear_contours()

    @QtCore.Slot()
    def contour_structure(self, structure: str) -> None:
        if self._alignment_settings is None:
            return

        thread = ContourGeneratorThread(structure, self._alignment_settings)

        thread.started.connect(self.increment_processing_count)
        thread.contours_ready.connect(lambda x: self.add_contours(structure, x))
        thread.finished.connect(self.decrement_processing_count)
        thread.finished.connect(thread.deleteLater)

        thread.start()

        self._contours_threads[structure] = thread

    @QtCore.Slot()
    def add_contours(self, structure: str, contours: list[np.ndarray]) -> None:
        if self._histology_item is None:
            return

        image = QtGui.QImage(
            self._histology_item.pixmap().size(),
            QtGui.QImage.Format.Format_ARGB32,
        )
        image.fill(0)

        pixmap = QtGui.QPixmap(image)

        painter = QtGui.QPainter(pixmap)

        width = 1
        width *= 100 / self._alignment_settings.volume_settings.resolution.value
        painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.white, width))

        for contour in contours:
            for i in range(contour.shape[0]):
                p1 = QtCore.QPoint(*contour[i, 0].tolist())
                j = i + 1
                if i == contour.shape[0] - 1:
                    j = 0
                p2 = QtCore.QPoint(*contour[j, 0].tolist())

                painter.drawLine(p1, p2)

        painter.end()

        self._contours[structure] = self.scene.addPixmap(pixmap)

    @QtCore.Slot()
    def remove_contours(self, structure: str) -> None:
        with suppress(KeyError):
            self._contours_threads[structure].should_emit = False

        item = self._contours.pop(structure, None)
        if item is not None:
            self.scene.removeItem(item)

    @QtCore.Slot()
    def increment_processing_count(self) -> None:
        self._processing_count += 1
        self.update_status_bar()

    @QtCore.Slot()
    def decrement_processing_count(self) -> None:
        self._processing_count -= 1
        self.update_status_bar()


class VolumeViewer(QtWidgets.QWidget):
    reference_volume: Optional[np.ndarray]
    overlay_volume: Optional[np.ndarray]

    view_updated: QtCore.Signal = QtCore.Signal(ZoomAndPanView)

    def __init__(
        self,
        reference_volume: Optional[np.ndarray] = None,
        resolution: Optional[Resolution] = None,
        overlay_volume: Optional[np.ndarray] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        #
        self.reference_volume = None

        self._primary_view = None
        self._coronal_pixmap_item = None
        self._horizontal_pixmap_item = None
        self._sagittal_pixmap_item = None

        self._slicing_indices = np.array([0, 0, 0])

        #
        self.setContentsMargins(0, 0, 0, 0)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.MinimumExpanding,
            QtWidgets.QSizePolicy.Policy.MinimumExpanding,
        )

        #
        master_scene = QtWidgets.QGraphicsScene(
            QtCore.QRectF(-100_000, -100_000, 200_000, 200_000), self
        )

        self.master_scene = master_scene

        #
        primary_view = ZoomAndPanView(master_scene, self)

        primary_view.setContentsMargins(0, 0, 0, 0)
        primary_view.setBackgroundBrush(QtCore.Qt.GlobalColor.black)

        self.primary_view = primary_view

        #
        coronal_view = FMRIPreview(master_scene, self)

        coronal_view.make_primary_requested.connect(
            lambda: self.make_primary(coronal_view)
        )
        coronal_view.up_scrolled.connect(lambda: self.increment_slicing_index(0))
        coronal_view.down_scrolled.connect(lambda: self.decrement_slicing_index(0))

        self.coronal_view = coronal_view

        #
        horizontal_view = FMRIPreview(master_scene, self)

        horizontal_view.make_primary_requested.connect(
            lambda: self.make_primary(horizontal_view)
        )
        horizontal_view.up_scrolled.connect(lambda: self.increment_slicing_index(1))
        horizontal_view.down_scrolled.connect(lambda: self.decrement_slicing_index(1))

        self.horizontal_view = horizontal_view

        #
        sagittal_view = FMRIPreview(master_scene, self)

        sagittal_view.make_primary_requested.connect(
            lambda: self.make_primary(sagittal_view)
        )
        sagittal_view.up_scrolled.connect(lambda: self.increment_slicing_index(2))
        sagittal_view.down_scrolled.connect(lambda: self.decrement_slicing_index(2))

        self.sagittal_view = sagittal_view

        #
        if reference_volume is None:
            if resolution is None:
                raise ValueError(
                    "Cannot instantiate a VolumeViewer without either a volume "
                    "or a resolution."
                )

            path = get_atlas_path(resolution, ensure_downloaded=True)
            reference_volume = load_volume(
                path, normalise_dtype=np.uint16, as_array=True
            )

        self.overlay_volume = overlay_volume
        self.set_reference_volume(reference_volume)
        self.update_views()

    def minimumSize(self) -> QtCore.QSize:
        return QtCore.QSize(200, 150)

    def set_reference_volume(self, volume: np.ndarray) -> None:
        self.reference_volume = volume
        self._slicing_indices = (np.array(volume.shape) - 1) // 2
        if volume is not None:
            self.update_views()

    def set_overlay_volume(self, volume: np.ndarray) -> None:
        self.overlay_volume = volume
        if volume is not None:
            self.update_views()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        self._do_layout()

    def increment_slicing_index(self, view_index: int) -> None:
        if self.reference_volume is None:
            return

        new_index = self._slicing_indices[view_index] + 1
        if new_index >= self.reference_volume.shape[view_index]:
            new_index -= 1

        self._slicing_indices[view_index] = new_index

        if view_index == 0:
            view = self.coronal_view
        elif view_index == 1:
            view = self.horizontal_view
        elif view_index == 2:
            view = self.sagittal_view
        else:
            return

        self._update_view(view)

    def decrement_slicing_index(self, view_index: int) -> None:
        if self.reference_volume is None:
            return

        new_index = self._slicing_indices[view_index] - 1
        if new_index < 0:
            new_index += 1

        self._slicing_indices[view_index] = new_index

        if view_index == 0:
            view = self.coronal_view
        elif view_index == 1:
            view = self.horizontal_view
        elif view_index == 2:
            view = self.sagittal_view
        else:
            return

        self._update_view(view)

    def update_views(self) -> None:
        if self.reference_volume is None:
            return

        self._update_view(self.coronal_view)
        self._update_view(self.horizontal_view)
        self._update_view(self.sagittal_view)

    def _update_view(self, view: FMRIPreview) -> None:
        if self.reference_volume is None:
            return

        if view == self.coronal_view:
            index = 0
            slicing = self._slicing_indices[index]
        elif view == self.horizontal_view:
            index = 1
            slicing = (slice(None), self._slicing_indices[index])
        elif view == self.sagittal_view:
            index = 2
            slicing = (slice(None), slice(None), self._slicing_indices[index])
        else:
            return

        array = self.reference_volume[slicing]
        if self.overlay_volume is not None:
            overlay = self.overlay_volume[slicing]
            array = np.where(overlay, overlay, array)

            if view == self.sagittal_view:
                array = array.T
        pixmap = np_to_qpixmap(array)

        if view == self.coronal_view:
            self.set_coronal_pixmap(pixmap)
        elif view == self.horizontal_view:
            self.set_horizontal_pixmap(pixmap)
        elif view == self.sagittal_view:
            self.set_sagittal_pixmap(pixmap)

    def set_coronal_pixmap(self, pixmap: QtGui.QPixmap) -> None:
        self._coronal_pixmap_item = self._replace_pixmap_item(
            pixmap, self._coronal_pixmap_item
        )

        self._coronal_pixmap_item.setTransform(QtGui.QTransform().translate(0, -10_000))

        self.coronal_view.set_focus_rect(self._coronal_pixmap_item.sceneBoundingRect())
        self.coronal_view.centre_on_focus()

        if self._primary_view == self.coronal_view or self._primary_view is None:
            self.make_primary(self.coronal_view)

    def set_horizontal_pixmap(self, pixmap: QtGui.QPixmap) -> None:
        self._horizontal_pixmap_item = self._replace_pixmap_item(
            pixmap, self._horizontal_pixmap_item
        )

        self.horizontal_view.set_focus_rect(
            self._horizontal_pixmap_item.sceneBoundingRect()
        )
        self.horizontal_view.centre_on_focus()

        if self._primary_view == self.horizontal_view or self._primary_view is None:
            self.make_primary(self.horizontal_view)

    def set_sagittal_pixmap(self, pixmap: QtGui.QPixmap) -> None:
        self._sagittal_pixmap_item = self._replace_pixmap_item(
            pixmap, self._sagittal_pixmap_item
        )

        self._sagittal_pixmap_item.setTransform(QtGui.QTransform().translate(0, 10_000))

        self.sagittal_view.set_focus_rect(
            self._sagittal_pixmap_item.sceneBoundingRect()
        )
        self.sagittal_view.centre_on_focus()

        if self._primary_view == self.sagittal_view or self._primary_view is None:
            self.make_primary(self.sagittal_view)

    @QtCore.Slot()
    def make_primary(self, view: ZoomAndPanView) -> None:
        self.primary_view.set_focus_rect(
            view.focus_rect, centre_on=True, reset_general_zoom=True
        )
        # self.primary_view.centre_on_focus()
        # self.primary_view.general_zoom = 1
        # self.primary_view.update_focus_zoom()

        self._primary_view = view

    def _do_layout(self) -> None:
        width = self.contentsRect().width()
        height = self.contentsRect().height()
        side_dimension = height // 3

        self.primary_view.setGeometry(
            0, 0, max(width - side_dimension, 10), max(height, 10)
        )

        self.coronal_view.setGeometry(
            width - side_dimension,
            self.contentsRect().top(),
            side_dimension,
            side_dimension,
        )

        self.horizontal_view.setGeometry(
            width - side_dimension,
            self.rect().top() + side_dimension,
            side_dimension,
            side_dimension,
        )

        self.sagittal_view.setGeometry(
            width - side_dimension,
            self.rect().top() + 2 * side_dimension,
            side_dimension,
            side_dimension,
        )

    def _replace_pixmap_item(
        self,
        pixmap: QtGui.QPixmap,
        pixmap_item: QtWidgets.QGraphicsPixmapItem | None = None,
    ) -> QtWidgets.QGraphicsPixmapItem:
        if pixmap_item is not None:
            self.master_scene.removeItem(pixmap_item)

        pixmap_item = self.master_scene.addPixmap(pixmap)

        return pixmap_item


class FMRIPreview(ZoomAndPanView):
    make_primary_requested: QtCore.Signal = QtCore.Signal()
    up_scrolled: QtCore.Signal = QtCore.Signal()
    down_scrolled: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        scene: QtWidgets.QGraphicsScene,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(scene, parent)

        #
        self.setContentsMargins(0, 0, 0, 0)
        self.setBackgroundBrush(QtCore.Qt.GlobalColor.black)

        self.set_drag_button(QtCore.Qt.MouseButton.MiddleButton)
        self.set_zoom_modifier(QtCore.Qt.KeyboardModifier.ControlModifier)

        #
        make_primary_button = QtWidgets.QPushButton(self)

        make_primary_button.setIcon(
            BinaryAlphaPixmap(ICONS_ROOT / "search-line-icon.png")
        )
        make_primary_button.setIconSize(QtCore.QSize(12, 12))

        make_primary_button.clicked.connect(self.make_primary_requested.emit)

        self.make_primary_button = make_primary_button

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        self.make_primary_button.setGeometry(self.width() - 25, 5, 20, 20)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        super().wheelEvent(event)

        delta = event.angleDelta()
        if delta.y() > 0:
            self.up_scrolled.emit()
        elif delta.y() < 0:
            self.down_scrolled.emit()
