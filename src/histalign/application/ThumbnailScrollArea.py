# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierDelrée@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.application.ThumbnailLabel import ThumbnailLabel
from histalign.application.Workspace import Workspace


COLUMN_COUNT: int = 2


class ThumbnailScrollArea(QtWidgets.QScrollArea):
    thumbnail_labels: list[ThumbnailLabel]

    open_image: QtCore.Signal = QtCore.Signal(int)
    swapped_thumbnails: QtCore.Signal = QtCore.Signal(int, int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)

        self.installEventFilter(self)

        self.thumbnail_labels = []
        self._start_drag_position = None

    def populate_thumbnails(self, workspace: Workspace) -> None:
        self.thumbnail_labels.clear()

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        for index, thumbnail in enumerate(workspace.iterate_thumbnails()):
            thumbnail_pixmap = QtGui.QPixmap().fromImage(
                QtGui.QImage(
                    thumbnail.tobytes(),
                    thumbnail.shape[1],
                    thumbnail.shape[0],
                    QtGui.QImage.Format.Format_Grayscale8,
                )
            )
            thumbnail_label = ThumbnailLabel(index)
            thumbnail_label.setPixmap(thumbnail_pixmap)

            layout.addWidget(
                thumbnail_label, index // COLUMN_COUNT, index % COLUMN_COUNT
            )

            self.thumbnail_labels.append(thumbnail_label)

        container_widget = QtWidgets.QWidget()
        container_widget.setLayout(layout)
        container_widget.setAcceptDrops(True)

        self.setWidget(container_widget)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        available_width = (
            event.size().width()
            - self.widget().layout().contentsMargins().left()
            - self.widget().layout().contentsMargins().right()
            - self.widget().layout().spacing()
        )

        for thumbnail_label in self.thumbnail_labels:
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
