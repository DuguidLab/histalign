# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Literal, Optional

from PySide6 import QtCore, QtGui, QtWidgets
import numpy as np

from histalign.backend.workspace import THUMBNAIL_DIMENSIONS, Workspace

COLUMN_COUNT: int = 2
SCROLL_THRESHOLD: int = 50


class ThumbnailLabel(QtWidgets.QLabel):
    index: int
    file_name: str
    thumbnail: Optional[QtGui.QPixmap]

    def __init__(
        self, index: int, file_name: str, parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)

        self.index = index
        self.file_name = file_name
        self.thumbnail = None

    def setPixmap(self, pixmap: QtGui.QPixmap) -> None:
        if self.thumbnail is None:
            self.thumbnail = pixmap
            pixmap = pixmap.scaled(pixmap.width() // 2, pixmap.height() // 2)
        super().setPixmap(pixmap)

    def heightForWidth(self, width: int) -> int:
        if self.thumbnail is None:
            return -1

        return round(width * (self.thumbnail.height() / self.thumbnail.width()))

    def resize(self, width: int) -> None:
        height = self.heightForWidth(width)
        if self.thumbnail is not None:
            self.setPixmap(self.thumbnail.scaled(width, height))

        self.setFixedSize(width, height)


class ThumbnailScrollArea(QtWidgets.QScrollArea):
    open_image: QtCore.Signal = QtCore.Signal(int)
    swapped_thumbnails: QtCore.Signal = QtCore.Signal(int, int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setWidgetResizable(True)

        self._start_drag_position = None
        self._scroll_timer = QtCore.QTimer()

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
        placeholder_thumbnail_label = ThumbnailLabel(0, "")
        placeholder_thumbnail_label.setPixmap(placeholder_pixmap)
        for i in range(COLUMN_COUNT):
            layout.addWidget(placeholder_thumbnail_label, 0, i)

        container_widget = QtWidgets.QWidget()
        container_widget.setLayout(layout)
        container_widget.setAcceptDrops(True)

        self.setWidget(container_widget)

    @QtCore.Slot()
    def update_thumbnail(
        self, index: int, file_name: str, thumbnail: np.ndarray
    ) -> None:
        thumbnail_pixmap = QtGui.QPixmap.fromImage(
            QtGui.QImage(
                thumbnail.tobytes(),
                thumbnail.shape[1],
                thumbnail.shape[0],
                QtGui.QImage.Format.Format_Grayscale8,
            )
        )
        thumbnail_label = ThumbnailLabel(index, file_name, self.widget())
        thumbnail_label.setPixmap(thumbnail_pixmap)
        thumbnail_label.resize(self.get_available_column_width())

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
        available_column_width = self.get_available_column_width()

        for thumbnail_label in self.widget().children():
            if not isinstance(thumbnail_label, ThumbnailLabel):
                continue
            thumbnail_label.resize(available_column_width)

    def get_available_column_width(self) -> int:
        return (
            self.width()
            - self.contentsMargins().left()
            - self.contentsMargins().right()
            - self.widget().layout().contentsMargins().left()
            - self.widget().layout().contentsMargins().right()
            - (self.widget().layout().spacing() * (COLUMN_COUNT - 1))
            - self.verticalScrollBar().width()
        ) // COLUMN_COUNT

    def drag_scroll(self, up_or_down: Literal["up", "down"], distance: int) -> None:
        speed = (SCROLL_THRESHOLD - distance) // 4
        if up_or_down == "up":
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - speed)
        elif up_or_down == "down":
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + speed)

    # noinspection PyTypeChecker
    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        match event.type():
            case QtCore.QEvent.Type.MouseButtonDblClick:
                widget = watched.childAt(event.position().toPoint())
                if not isinstance(widget, ThumbnailLabel):
                    return super().eventFilter(watched, event)
                self.open_image.emit(widget.index)
            case QtCore.QEvent.Type.MouseButtonPress:
                if isinstance(watched, QtWidgets.QScrollBar):
                    return super().eventFilter(watched, event)
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
                self._scroll_timer.stop()

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
            case QtCore.QEvent.Type.DragMove:
                widget = watched.parent()

                distance_to_top = event.pos().y() - (widget.y() - watched.y())
                distance_to_bottom = (
                    widget.y() + widget.height() - watched.y() - event.pos().y()
                )

                if distance_to_top < SCROLL_THRESHOLD:
                    QtCore.QObject.disconnect(self._scroll_timer, None, None, None)
                    self._scroll_timer.timeout.connect(
                        lambda: self.drag_scroll("up", distance_to_top)
                    )
                    if not self._scroll_timer.isActive():
                        self._scroll_timer.start(25)
                elif distance_to_bottom < SCROLL_THRESHOLD:
                    QtCore.QObject.disconnect(self._scroll_timer, None, None, None)
                    self._scroll_timer.timeout.connect(
                        lambda: self.drag_scroll("down", distance_to_bottom)
                    )
                    if not self._scroll_timer.isActive():
                        self._scroll_timer.start(25)
                elif self._scroll_timer.isActive():
                    self._scroll_timer.stop()
            case QtCore.QEvent.Type.DragEnter:
                event.accept()
            case _:
                return super().eventFilter(watched, event)

        return True


class ThumbnailsWidget(QtWidgets.QWidget):
    content_area: ThumbnailScrollArea
    status_bar: QtWidgets.QStatusBar

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        status_bar = QtWidgets.QStatusBar()

        self.status_bar = status_bar

        #
        content_area = ThumbnailScrollArea()

        content_area.installEventFilter(ThumbnailFileNameWatcher(status_bar, self))

        self.content_area = content_area

        #
        layout = QtWidgets.QVBoxLayout()

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(content_area)
        layout.addWidget(status_bar)

        self.setLayout(layout)

    def widget(self):
        return self._widget.findChild(ThumbnailScrollArea)

    def connect_workspace(self, workspace: Workspace) -> None:
        self.content_area.flush_thumbnails()

        workspace.thumbnail_generated.connect(self.content_area.update_thumbnail)
        self.content_area.swapped_thumbnails.connect(workspace.swap_slices)


class ThumbnailFileNameWatcher(QtCore.QObject):
    previous_position: QtCore.QPoint = QtCore.QPoint(-1, -1)
    cached_widget: Optional[QtWidgets.QWidget] = None

    status_bar: QtWidgets.QStatusBar
    watcher_timer: QtCore.QTimer

    def __init__(
        self, status_bar: QtWidgets.QStatusBar, parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)

        self.status_bar = status_bar

        watcher_timer = QtCore.QTimer()
        watcher_timer.timeout.connect(self.watch)

        self.watcher_timer = watcher_timer

    def start_watching(self, interval: int = 100) -> None:
        self.watcher_timer.start(interval)

    def stop_watching(self) -> None:
        self.watcher_timer.stop()
        self.status_bar.clearMessage()

    def eventFilter(self, watched: QtWidgets.QWidget, event: QtCore.QEvent) -> bool:
        match event.type():
            case QtCore.QEvent.Type.Enter:
                self.start_watching()
                return True
            case QtCore.QEvent.Type.Leave:
                self.stop_watching()
                return True
            case _:
                return super().eventFilter(watched, event)

    @QtCore.Slot()
    def watch(self) -> None:
        mouse_position = QtGui.QCursor.pos()

        if mouse_position == self.previous_position:
            widget = self.cached_widget
        else:
            widget = self.parent().window().childAt(mouse_position)
            self.cached_widget = widget
            self.previous_position = mouse_position

        if isinstance(widget, ThumbnailLabel):
            self.status_bar.showMessage(widget.file_name)
        else:
            self.status_bar.clearMessage()
