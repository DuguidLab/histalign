# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.workspace.HistologySlice import THUMBNAIL_DIMENSIONS
from histalign.frontend.registration.ThumbnailLabel import ThumbnailLabel

COLUMN_COUNT: int = 2


class ThumbnailScrollArea(QtWidgets.QScrollArea):
    open_image: QtCore.Signal = QtCore.Signal(int)
    swapped_thumbnails: QtCore.Signal = QtCore.Signal(int, int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setWidgetResizable(True)

        self.installEventFilter(self)

        self._start_drag_position = None

        self._initialise_widget()

    def flush_thumbnails(self) -> None:
        self.widget().deleteLater()
        self._initialise_widget()

    def _initialise_widget(self) -> None:
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        placeholder_pixmap = QtGui.QPixmap.fromImage(
            QtGui.QImage(
                np.zeros(THUMBNAIL_DIMENSIONS[::-1], dtype=np.uint8).tobytes(),
                THUMBNAIL_DIMENSIONS[0],
                THUMBNAIL_DIMENSIONS[1],
                QtGui.QImage.Format.Format_Alpha8,
            )
        )
        placeholder_thumbnail_label = ThumbnailLabel(0)
        placeholder_thumbnail_label.setPixmap(placeholder_pixmap)
        for i in range(COLUMN_COUNT):
            layout.addWidget(placeholder_thumbnail_label, 0, i)

        container_widget = QtWidgets.QWidget()
        container_widget.setLayout(layout)
        container_widget.setAcceptDrops(True)

        self.setWidget(container_widget)

    @QtCore.Slot()
    def update_thumbnail(self, index: int, thumbnail: np.ndarray) -> None:
        thumbnail_pixmap = QtGui.QPixmap.fromImage(
            QtGui.QImage(
                thumbnail.tobytes(),
                thumbnail.shape[1],
                thumbnail.shape[0],
                QtGui.QImage.Format.Format_Grayscale8,
            )
        )
        thumbnail_label = ThumbnailLabel(index, self.widget())
        thumbnail_label.setPixmap(thumbnail_pixmap)

        self.replace_grid_cell(index, thumbnail_label)

    def replace_grid_cell(
        self, index: int, replacement_widget: QtWidgets.QWidget
    ) -> None:
        layout = self.widget().layout()
        old_widget_item = layout.itemAtPosition(
            index // COLUMN_COUNT, index % COLUMN_COUNT
        )
        if old_widget_item is not None:
            layout.takeAt(
                layout.indexOf(old_widget_item.widget())
            ).widget().deleteLater()

        layout.addWidget(
            replacement_widget, index // COLUMN_COUNT, index % COLUMN_COUNT
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        available_width = (
            event.size().width()
            - self.widget().layout().contentsMargins().left()
            - self.widget().layout().contentsMargins().right()
            - self.widget().layout().spacing()
        )

        for thumbnail_label in self.widget().children():
            if not isinstance(thumbnail_label, ThumbnailLabel):
                continue
            thumbnail_label.resize(available_width // 2)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        match event.type():
            case QtCore.QEvent.Type.MouseButtonDblClick:
                widget = watched.childAt(event.position().toPoint())
                if not isinstance(widget, ThumbnailLabel):
                    return super().eventFilter(watched, event)
                self.open_image.emit(widget.index)
            case QtCore.QEvent.Type.MouseButtonPress:
                self._start_drag_position = event.position().toPoint()
            case QtCore.QEvent.Type.MouseMove:
                if isinstance(watched, QtWidgets.QScrollBar):
                    return super().eventFilter(watched, event)
                if (
                    event.buttons() == QtCore.Qt.MouseButton.LeftButton
                    and self._start_drag_position is not None
                ):
                    drag = QtGui.QDrag(watched.childAt(self._start_drag_position))
                    drag.setMimeData(QtCore.QMimeData())
                    drag.exec(QtCore.Qt.DropAction.MoveAction)
            case QtCore.QEvent.Type.Drop:
                source = event.source()
                target = watched.childAt(event.position().toPoint())

                if isinstance(source, ThumbnailLabel) and isinstance(
                    target, ThumbnailLabel
                ):
                    layout = watched.layout()

                    index1 = source.index
                    index2 = target.index

                    widget1 = layout.itemAt(layout.indexOf(source)).widget()
                    widget2 = layout.itemAt(layout.indexOf(target)).widget()

                    widget1.index = index2
                    widget2.index = index1

                    layout.removeWidget(widget1)
                    layout.removeWidget(widget2)

                    layout.addWidget(
                        widget2, index1 // COLUMN_COUNT, index1 % COLUMN_COUNT
                    )
                    layout.addWidget(
                        widget1, index2 // COLUMN_COUNT, index2 % COLUMN_COUNT
                    )

                    self.swapped_thumbnails.emit(index1, index2)
            case QtCore.QEvent.Type.DragEnter:
                event.accept()
            case _:
                return super().eventFilter(watched, event)

        return True
