# SPDX-FileCopyrightText: 2025-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from contextlib import suppress
import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.io import load_alignment_settings
from histalign.backend.registration import ContourGeneratorThread
from histalign.backend.workspace import HistologySlice
from histalign.frontend.common_widgets import ZoomAndPanView
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
        file.load_image(str(alignment_path.parent), 16)

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
    def add_contours(self, structure: str, contours: np.ndarray) -> None:
        if self._histology_item is None:
            return

        pixmap = QtGui.QPixmap(self._histology_item.pixmap().size())

        painter = QtGui.QPainter(pixmap)

        painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.white, 10))

        painter.drawPointsNp(contours[..., 0], contours[..., 1])

        painter.end()

        self._contours[structure] = self.scene.addPixmap(pixmap)

    @QtCore.Slot()
    def remove_contours(self, structure: str) -> None:
        with suppress(KeyError):
            self._contours_threads[structure].should_emit = False

        item = self._contours.pop(structure, None)
        if item is not None:
            self.scene.removeItem(item)
