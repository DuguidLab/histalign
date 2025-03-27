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

from histalign.backend.ccf.paths import get_atlas_path
from histalign.backend.io import (
    load_alignment_settings,
    load_volume,
    RESOURCES_ROOT,
)
from histalign.backend.registration import ContourGeneratorThread
from histalign.backend.workspace import HistologySlice
from histalign.frontend.common_widgets import BinaryAlphaPixmap, ZoomAndPanView
from histalign.frontend.pyside_helpers import np_to_qpixmap

_module_logger = logging.getLogger(__name__)


class SliceViewer(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self._alignment_settings = None
        self._histology_item = None

        self._contours = {}
        self._contours_threads = {}
        self._contours_item = None

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
        for structure in self._contours.keys():
            self.remove_contours(structure)

    def set_pixmap(self, pixmap: QtGui.QPixmap) -> None:
        if self._histology_item is not None:
            self.scene.removeItem(self._histology_item)

        pixmap_item = self.scene.addPixmap(pixmap)
        pixmap_item.setZValue(-1)

        self.view.set_focus_rect(pixmap_item.sceneBoundingRect())
        self._histology_item = pixmap_item

    @QtCore.Slot()
    def open_image(self, alignment_path: Path) -> None:
        alignment_settings = load_alignment_settings(alignment_path)
        histology_path = alignment_settings.histology_path

        file = HistologySlice(str(histology_path))
        file.load_image(str(alignment_path.parent), downsampling_factor=1)

        pixmap = np_to_qpixmap(file.image_array)

        self.set_pixmap(pixmap)
        self._alignment_settings = alignment_settings

        self.clear_contours()

    @QtCore.Slot()
    def contour_structure(self, structure: str) -> None:
        if self._alignment_settings is None:
            return

        thread = ContourGeneratorThread(structure, self._alignment_settings)

        thread.contours_ready.connect(lambda x: self.add_contours(structure, x))
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

        pixmap = QtGui.QPixmap(image)

        painter = QtGui.QPainter(pixmap)

        painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.white, 10))

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

        self.coronal_view = coronal_view

        #
        horizontal_view = FMRIPreview(master_scene, self)

        horizontal_view.make_primary_requested.connect(
            lambda: self.make_primary(horizontal_view)
        )

        self.horizontal_view = horizontal_view

        #
        sagittal_view = FMRIPreview(master_scene, self)

        sagittal_view.make_primary_requested.connect(
            lambda: self.make_primary(sagittal_view)
        )

        self.sagittal_view = sagittal_view

        #
        if reference_volume is None:
            if resolution is None:
                raise ValueError(
                    "Cannot instantiate a VolumeViewer without either a volume "
                    "or a resolution."
                )

            path = get_atlas_path(resolution)
            reference_volume = load_volume(
                path, normalise_dtype=np.uint16, return_raw_array=True
            )

        self.reference_volume = reference_volume
        self.overlay_volume = overlay_volume
        self.update_views()

    def minimumSize(self) -> QtCore.QSize:
        return QtCore.QSize(200, 150)

    def set_reference_volume(self, volume: np.ndarray) -> None:
        self.reference_volume = volume
        if volume is not None:
            self.update_views()

    def set_overlay_volume(self, volume: np.ndarray) -> None:
        self.overlay_volume = volume
        if volume is not None:
            self.update_views()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        self._do_layout()

    def update_views(self) -> None:
        if self.reference_volume is None:
            return

        # Coronal
        array = self.reference_volume[(self.reference_volume.shape[0] - 1) // 2]
        if self.overlay_volume is not None:
            overlay = self.overlay_volume[(self.overlay_volume.shape[0] - 1) // 2]
            array = np.where(overlay, overlay, array)
        pixmap = np_to_qpixmap(array)
        self.set_coronal_pixmap(pixmap)

        # Horizontal
        array = self.reference_volume[:, (self.reference_volume.shape[1] - 1) // 2]
        if self.overlay_volume is not None:
            overlay = self.overlay_volume[:, (self.overlay_volume.shape[1] - 1) // 2]
            array = np.where(overlay, overlay, array)
        pixmap = np_to_qpixmap(array)
        self.set_horizontal_pixmap(pixmap)

        # Sagittal
        array = self.reference_volume[..., (self.reference_volume.shape[2] - 1) // 2].T
        if self.overlay_volume is not None:
            overlay = self.overlay_volume[
                ..., (self.overlay_volume.shape[2] - 1) // 2
            ].T
            array = np.where(overlay, overlay, array)
        pixmap = np_to_qpixmap(array)
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

    def __init__(
        self,
        scene: QtWidgets.QGraphicsScene,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(scene, parent)

        #
        self.setContentsMargins(0, 0, 0, 0)
        self.setBackgroundBrush(QtCore.Qt.GlobalColor.black)

        self.set_zoom_modifier(QtCore.Qt.KeyboardModifier.ControlModifier)

        #
        make_primary_button = QtWidgets.QPushButton(self)

        make_primary_button.setIcon(
            BinaryAlphaPixmap(RESOURCES_ROOT / "icons" / "search-line-icon.png")
        )
        make_primary_button.setIconSize(QtCore.QSize(12, 12))

        make_primary_button.clicked.connect(self.make_primary_requested.emit)

        self.make_primary_button = make_primary_button

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        self.make_primary_button.setGeometry(self.width() - 25, 5, 20, 20)
