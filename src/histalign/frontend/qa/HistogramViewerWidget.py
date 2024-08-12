# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
import matplotlib.pyplot as plt
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.frontend.qa.QAViewerWidget import QAViewerWidget


class Canvas(FigureCanvasQTAgg):
    def __init__(self, structure_name: str, values: np.ndarray) -> None:
        figure, axes = plt.subplots(figsize=(16, 9), constrained_layout=True)
        axes.set_title(structure_name)
        axes.set_xlabel("Pixel intensities")
        axes.hist(values, bins=100)
        axes.set_xlim(0, np.iinfo(values.dtype).max)

        super().__init__(figure)

        self.installEventFilter(self)
        self.setMinimumSize(1, 1)  # Avoid Matplotlib errors from 0-size

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        width = event.size().width()
        height = round(width * (9 / 16))

        event = QtGui.QResizeEvent(
            QtCore.QSize(width, height),
            event.oldSize(),
        )
        self.setFixedHeight(height)
        super().resizeEvent(event)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.Wheel:
            watched.parent().wheelEvent(event)
            return True
        else:
            return super().eventFilter(watched, event)


class HistogramViewerWidget(QtWidgets.QScrollArea):
    viewer: QAViewerWidget
    canvases: dict[str, QtWidgets.QWidget]
    canvases_layout: QtWidgets.QVBoxLayout

    def __init__(
        self, viewer: QAViewerWidget, parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)

        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self.setWidgetResizable(True)

        self.viewer = viewer
        self.canvases = {}

        container_widget = QtWidgets.QWidget()

        self.canvases_layout = QtWidgets.QVBoxLayout()
        self.canvases_layout.setAlignment(QtCore.Qt.AlignTop)
        container_widget.setLayout(self.canvases_layout)

        self.setWidget(container_widget)

    @QtCore.Slot()
    def add_histogram(self, structure_name: str, mask: np.ndarray) -> None:
        values = self.viewer.histology_array[np.where(mask != 0)]
        canvas = Canvas(structure_name, values)

        self.canvases[structure_name] = canvas

        self.canvases_layout.addWidget(canvas)

    @QtCore.Slot()
    def remove_histogram(self, structure_name: str) -> None:
        canvas = self.canvases.pop(structure_name, None)
        if canvas is not None:
            # Prevent Matplotlib from trying to use canvas._draw_idle() on deleted canvas
            canvas.hide()
            canvas.deleteLater()
