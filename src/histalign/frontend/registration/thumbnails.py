# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations, annotations, annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.workspace import Workspace
from histalign.frontend.common_widgets import ThumbnailsContainerWidget, ThumbnailWidget
from histalign.frontend.pyside_helpers import find_parent

SCROLL_THRESHOLD: int = 50


class ThumbnailsWidget(QtWidgets.QScrollArea):
    thumbnail_activated: QtCore.Signal = QtCore.Signal(int)
    thumbnails_swapped: QtCore.Signal = QtCore.Signal(int, int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self._active_thumbnail = None
        self._complete_indices = []

        self._start_drag_position = None
        self._scroll_distance = 0
        self._scroll_timer = QtCore.QTimer()
        self._scroll_timer.timeout.connect(self.drag_scroll)

        #
        self.setAcceptDrops(True)
        self.setWidgetResizable(True)

        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setViewportMargins(5, 5, 5, 5)

        #
        self._initialise_container_widget()

    def connect_workspace(self, workspace: Workspace) -> None:
        self.flush_thumbnails()

        workspace.thumbnail_generated.connect(self.update_thumbnail)
        self.thumbnails_swapped.connect(workspace.swap_images)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        event.accept()

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        position = event.position().toPoint()

        if (
            distance := min(-1, -(position.y() - self.viewport().rect().y()))
        ) > -SCROLL_THRESHOLD or (
            distance := max(1, self.viewport().height() - position.y())
        ) < SCROLL_THRESHOLD:
            self._scroll_distance = distance
            if not self._scroll_timer.isActive():
                self._scroll_timer.start(25)
        else:
            self._scroll_timer.stop()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        self._scroll_timer.stop()

        # According to the docs, the source is a QWidget, not just a QObject
        source = event.source()
        if not isinstance(source, ThumbnailWidget):
            if not isinstance(source, QtWidgets.QWidget):
                return
            source = find_parent(source, ThumbnailWidget)
        target = self.childAt(event.position().toPoint())
        if target is not None and not isinstance(target, ThumbnailWidget):
            target = find_parent(target, ThumbnailWidget)

        # Only allow drag & drop from thumbnail A to thumbnail B
        if source is None or target is None or source is target:
            super().dropEvent(event)
            return

        target.index, source.index = source.index, target.index

        self.widget().layout().swapItems(source.index, target.index)

        self.thumbnails_swapped.emit(target.index, source.index)

        # Force a hover event on the source to highlight it.
        # Required to process events to "eat up" an enter event that otherwise gets
        # processed after our custom leave event.
        QtWidgets.QApplication.instance().processEvents()
        target.leaveEvent(QtCore.QEvent(QtCore.QEvent.Type.Leave))
        source.enterEvent(
            event=QtGui.QEnterEvent(
                event.position(),
                self.mapToGlobal(event.position()),
                self.mapToGlobal(event.position()),
            )
        )
        source.clearFocus()

    def flush_thumbnails(self) -> None:
        self.widget().deleteLater()
        self._active_thumbnail = None
        self._initialise_container_widget()
        self._complete_indices = []

    def focus_thumbnail(self, index: int) -> None:
        item = self.widget().layout().itemAt(index)
        if item is not None:
            widget = item.widget()
            if not isinstance(widget, ThumbnailWidget):
                raise Exception(
                    "Received a widget from PixmapFlowLayout that was not a "
                    "ThumbnailWidget."
                )

            widget.setFocus()
            self.make_thumbnail_active(widget)

    def make_thumbnail_active(self, widget: ThumbnailWidget) -> None:
        if self._active_thumbnail is not None:
            self._active_thumbnail.set_active(False)
        widget.set_active(True)
        self._active_thumbnail = widget

    def make_thumbnail_at_active(self, index: int) -> None:
        item = self.widget().layout().itemAt(index)
        if item is None:
            return
        widget = item.widget()

        if self._active_thumbnail is not None:
            self._active_thumbnail.set_active(False)
        widget.set_active(True)
        self._active_thumbnail = widget

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        widget = self.childAt(event.position().toPoint())
        if widget is not None:
            widget = find_parent(widget, ThumbnailWidget)

        if isinstance(widget, ThumbnailWidget):
            self.make_thumbnail_active(widget)

            self.thumbnail_activated.emit(widget.index)
            return

        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.buttons() == QtCore.Qt.MouseButton.LeftButton
            and self._start_drag_position is not None
        ):
            child = self.childAt(self._start_drag_position)
            if not isinstance(child, QtWidgets.QWidget):
                return super().mouseMoveEvent(event)

            dragged_widget = find_parent(child, ThumbnailWidget)
            if dragged_widget is None:
                return super().mouseMoveEvent(event)

            dragged_widget.set_highlighted(False, False)

            drag = QtGui.QDrag(dragged_widget)
            drag.setPixmap(dragged_widget.grab())
            drag.setMimeData(QtCore.QMimeData())
            drag.exec(QtCore.Qt.DropAction.MoveAction)
            return

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._start_drag_position = event.position().toPoint()
            return

        super().mousePressEvent(event)

    def replace_thumbnail(self, index: int, thumbnail: ThumbnailWidget) -> None:
        self.widget().layout().replaceAt(index, thumbnail)

    def set_thumbnail_completed(self, index: int, completed: bool) -> None:
        if not 0 < index < self.widget().layout().count():
            return

        if index in self._complete_indices and not completed:
            self._complete_indices.remove(index)
        elif index not in self._complete_indices and completed:
            self._complete_indices.append(index)

        thumbnail_item = self.widget().layout().itemAt(index)
        if thumbnail_item is not None:
            thumbnail_item.widget().set_completed(completed)

    def setWidget(self, widget: ThumbnailsContainerWidget) -> None:
        if not isinstance(widget, ThumbnailsContainerWidget):
            raise ValueError(
                "ThumbnailsWidget only accepts _ThumbnailsContainerWidget as a widget."
            )

        self._widget = widget
        super().setWidget(widget)

    def widget(self) -> ThumbnailsContainerWidget:
        return self._widget

    def _initialise_container_widget(self) -> None:
        widget = ThumbnailsContainerWidget()

        self.setMinimumSize(
            widget.layout().minimumSize()
            + QtCore.QSize(20, 20)
            + QtCore.QSize(
                self.verticalScrollBar().sizeHint().width(),
                0,
            )
        )

        self.setWidget(widget)

    @QtCore.Slot()
    def drag_scroll(self) -> None:
        distance = self._scroll_distance
        speed = round(((SCROLL_THRESHOLD - abs(distance)) // 4)) * (
            distance // abs(distance)
        )
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + speed)

    @QtCore.Slot()
    def update_thumbnail(self, index: int, file_path: Path, file_name: str) -> None:
        thumbnail_widget = ThumbnailWidget(
            file_path, file_name, index, parent=self.widget()
        )
        if index in self._complete_indices:
            thumbnail_widget.set_completed(True)

        self.replace_thumbnail(index, thumbnail_widget)
