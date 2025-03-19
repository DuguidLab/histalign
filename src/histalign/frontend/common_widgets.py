# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from abc import abstractmethod
from contextlib import suppress
import itertools
import json
import logging
import math
from pathlib import Path
import re
import sys
from typing import Any, Callable, Literal, Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
import matplotlib.pyplot as plt
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend import UserRole
from histalign.backend.ccf.model_view import (
    ABAStructureTreeModel,
    iterate_tree_model_dfs,
)
from histalign.backend.io import RESOURCES_ROOT
from histalign.backend.workspace import HistologySlice
from histalign.frontend.dialogs import OpenProjectDialog
from histalign.frontend.pyside_helpers import (
    connect_single_shot_slot,
    FakeQtABC,
    lua_aware_shift,
)
from histalign.frontend.themes import is_light_colour

QWIDGETSIZE_MAX = 16777215  # Qt constant

HASHED_DIRECTORY_NAME_PATTERN = re.compile(r"[0-9a-f]{10}")

_module_logger = logging.getLogger(__name__)


class ProjectDirectoriesComboBox(QtWidgets.QComboBox):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

    def parse_project(self, project_directory: Path) -> None:
        self.clear()

        for path in project_directory.iterdir():
            if (
                path.is_file()
                or re.fullmatch(HASHED_DIRECTORY_NAME_PATTERN, str(path.name)) is None
            ):
                continue

            metadata_path = path / "metadata.json"
            if not metadata_path.exists():
                continue

            with open(metadata_path) as handle:
                self.addItem(json.load(handle)["directory_path"])


class NoFocusRectProxyStyle(QtWidgets.QProxyStyle):
    """A proxy style removing the focus rect present in tree views in some styles.

    Taken from the following StackOverflow answer:
    https://stackoverflow.com/questions/17280056/how-to-remove-qpushbutton-focus-rectangle-using-stylesheets/17294081#17294081
    """

    def drawPrimitive(
        self,
        element: QtWidgets.QStyle.PrimitiveElement,
        option: QtWidgets.QStyleOption,
        painter: QtGui.QPainter,
        widget: QtWidgets.QWidget | None = None,
    ) -> None:
        if element == QtWidgets.QStyle.PrimitiveElement.PE_FrameFocusRect:
            return

        super().drawPrimitive(element, option, painter, widget)


class StructureTreeView(QtWidgets.QTreeView):
    """A tree view used to display the CCF structure hierarchy."""

    item_checked: QtCore.Signal = QtCore.Signal(QtCore.QModelIndex)
    item_unchecked: QtCore.Signal = QtCore.Signal(QtCore.QModelIndex)

    selection_hidden: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        #
        self.setModel(ABAStructureTreeModel())

        #
        self.setStyle(NoFocusRectProxyStyle())
        self.setHeaderHidden(True)

        self.collapsed.connect(self.collapse_all_children)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        self.auto_resize_columns()

    @QtCore.Slot()
    def auto_resize_columns(self, _=...) -> None:
        """Resizes the columns to ensure acronyms are visible in the first column."""
        options = QtWidgets.QStyleOptionFrame()
        self.initStyleOption(options)

        width = (
            self.style()
            .subElementRect(
                QtWidgets.QStyle.SubElement.SE_CheckBoxClickRect, options, self
            )
            .width()
        ) + 10

        self.setColumnWidth(0, self.viewport().width() - width - 2)
        self.setColumnWidth(1, width - 2)

    @QtCore.Slot()
    def collapse_all_children(
        self, index: QtCore.QModelIndex | QtCore.QPersistentModelIndex
    ) -> None:
        """Collapses all the children of a node.

        This also removes the selection if it has been collapsed.

        Args:
            index (QtCore.QModelIndex | QtCore.QPersistentModelIndex):
                Root node to collapse the children of.
        """
        child_count = self.model().rowCount(index)
        self._collapse_all_children(index, child_count)

        selection = self.selectionModel().selectedIndexes()
        if selection:
            # Take [0] as selectedIndexes() returns one per column
            if not self.visualRect(selection[0]).isValid():
                self.selection_hidden.emit()

    def _collapse_all_children(
        self,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        child_count: int,
    ) -> None:
        for i in range(child_count):
            child_index = self.model().index(i, 0, index)

            sub_child_count = self.model().rowCount(child_index)
            if sub_child_count > 0:
                self._collapse_all_children(child_index, sub_child_count)

            self.collapse(child_index)


class StructureTableView(QtWidgets.QTableView):
    """A table view used to display the CCF structure hierarchy."""

    def __init__(
        self,
        model: Optional[ABAStructureListModel] = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        #
        self.setModel(model or ABAStructureListModel())

        #
        self.setWordWrap(False)
        self.setStyle(NoFocusRectProxyStyle())

        self.horizontalHeader().hide()
        self.verticalHeader().hide()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        self.auto_resize_columns()

    @QtCore.Slot()
    def auto_resize_columns(self, _=...) -> None:
        """Resizes the columns to ensure acronyms are visible in the first column."""
        options = QtWidgets.QStyleOptionFrame()
        self.initStyleOption(options)

        width = (
            self.style()
            .subElementRect(
                QtWidgets.QStyle.SubElement.SE_CheckBoxClickRect, options, self
            )
            .width()
        ) + 10

        self.setColumnWidth(0, self.viewport().width() - width - 2)
        self.setColumnWidth(1, width - 2)


class StructureFinderDialog(QtWidgets.QDialog):
    """A pop-up dialog showing a structure finder widget.

    Attributes:
        finder_widget (StructureFinderWidget): Finder widget for this dialog.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        finder_widget = StructureFinderWidget()

        finder_widget.layout().setContentsMargins(0, 0, 0, 0)

        self.finder_widget = finder_widget

        #
        close_button = QtWidgets.QPushButton("Close")

        close_button.clicked.connect(self.close)

        #
        layout = QtWidgets.QGridLayout()

        layout.addWidget(finder_widget, 0, 0, 1, 2)
        layout.addWidget(close_button, 1, 1, 1, 1)

        self.setLayout(layout)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Handles key press events.

        Args:
            event (QtGui.QKeyEvent): Event to handle.
        """
        # Ignore enter and return key inputs to avoid closing the dialog instead of
        # searching with the finder widget.
        if (
            event.key() == QtCore.Qt.Key.Key_Return
            or event.key() == QtCore.Qt.Key.Key_Enter
        ):
            return

        super().keyPressEvent(event)


class StructureFinderWidget(QtWidgets.QWidget):
    """A structure finder widget consisting of a search bar and a structure tree view.

    The search bar allows searching for acronyms or structure names in the view. If they
    are found, the view highlights them and scrolls to them if they're not in view.
    The user can search forward (with Enter/Return) or backwards (Shift+Enter/Return).

    Attributes:
        tree_view (StructureTreeView): Tree view with which to show the hierarchy.
    """

    def __init__(
        self, use_proxy: bool = True, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)

        #
        self._previous_search = None
        self._previous_index = -1

        #
        line_edit = QtWidgets.QLineEdit()

        line_edit.returnPressed.connect(
            lambda: self.find_and_focus_structure_node(line_edit.text())
        )

        #
        tree_view = StructureTreeView()

        tree_view.selection_hidden.connect(self.clear_search_and_selection)

        if use_proxy:
            proxy = CustomDisplayRoleProxy()

            proxy.setSourceModel(tree_view.model())

            proxy.override_display_role(UserRole.SHORTENED_NAME)

            tree_view.setModel(proxy)

        self.tree_view = tree_view

        #
        layout = QtWidgets.QVBoxLayout()

        layout.addWidget(line_edit)
        layout.addWidget(tree_view)

        self.setLayout(layout)

    def clear_search_and_selection(self) -> None:
        """Clears the search cache and the current selection."""
        self._previous_search = None
        self._previous_index = -1

        self.tree_view.selectionModel().clearCurrentIndex()
        self.tree_view.selectionModel().clearSelection()

    def find_and_focus_structure_node(self, text: str) -> None:
        """Searches for and selects a structure node in the view if it exists.

        Args:
            text (str):
                Search query. This can be the acronym or the name of the structure.
        """
        text = text.lower()

        if len(text) < 3:
            return

        repeat = text == self._previous_search  # Is this a repeat search
        reverse = (
            QtWidgets.QApplication.queryKeyboardModifiers()
            == QtCore.Qt.KeyboardModifier.ShiftModifier
        )  # Is this a reverse search

        first_match = None
        last_match = None
        match_index = -1
        self._previous_search = text

        # Search in the full name
        model = self.tree_view.model()
        for index in iterate_tree_model_dfs(model):
            try:
                found = (
                    text.lower()
                    in model.data(
                        index, QtCore.Qt.ItemDataRole.DisplayRole, skip_override=True
                    ).lower()
                )
            except TypeError:
                found = (
                    text.lower()
                    in index.data(QtCore.Qt.ItemDataRole.DisplayRole).lower()
                )

            if found:
                match_index += 1

                # Keep track of the first match as a default if searching forward
                if first_match is None and not reverse:
                    first_match = index
                # Keep track of the last match as a default for when searching backward
                last_match = index

                # When doing a reverse search for the first time or when cycling to the
                # end, search until the last match.
                if self._previous_index <= 0 and reverse:
                    continue

                # Allow cycling matches by calling this function multiple times
                if repeat and (
                    (match_index <= self._previous_index and not reverse)
                    or (match_index < self._previous_index - 1 and reverse)
                ):
                    continue

                self._previous_index = match_index

                self.tree_view.selectionModel().select(
                    index,
                    QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                    | QtCore.QItemSelectionModel.SelectionFlag.Rows,
                )
                self.tree_view.scrollTo(index)

                return

        if not reverse and first_match is not None:
            # Forward search cycling, select the first match if it exists
            self._previous_index = 0
            index = first_match
        elif reverse and last_match is not None:
            # Reverse search cycling, select the last match if it exists
            self._previous_index = match_index
            index = last_match
        else:
            # No match
            return

        self.tree_view.selectionModel().select(
            index,
            QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QtCore.QItemSelectionModel.Current
            | QtCore.QItemSelectionModel.SelectionFlag.Rows,
        )
        self.tree_view.scrollTo(index)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Handles key press events.

        Args:
            event (QtGui.QKeyEvent): Event to handle.
        """
        # Clear selection if there is one, otherwise ignore event
        if event.key() == QtCore.Qt.Key.Key_Escape:
            if self.tree_view.selectionModel().selectedIndexes():
                self.clear_search_and_selection()
                return

        super().keyPressEvent(event)


class StructureTagWidget(QtWidgets.QFrame):
    """A structure tag widget for displaying structure names and a close icon.

    Attributes:
        name (str): Name of the structure this tag is for.
        separator (HorizontalSeparator): Separator between the name and close button.
    """

    removal_requested: QtCore.Signal = QtCore.Signal()

    def __init__(self, name: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self.name = name

        #
        name_label = QtWidgets.QLabel(name)

        name_label.setContentsMargins(3, 3, 3, 3)
        name_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignBottom)

        #
        pixmap_label = ResizablePixmapLabel(
            RESOURCES_ROOT / "icons" / "close-line-icon.png", icon_mode=True
        )

        pixmap_height = name_label.fontMetrics().boundingRect(name).height()
        pixmap_label.setFixedSize(pixmap_height, pixmap_height)
        pixmap_label.setContentsMargins(3, 0, 3, 0)
        pixmap_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed
        )

        #
        separator = HorizontalSeparator()

        self.separator = separator

        #
        layout = QtWidgets.QHBoxLayout()

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(name_label)
        layout.addWidget(separator)
        layout.addWidget(pixmap_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        self.setLayout(layout)

        #
        self.installEventFilter(self)

        palette = self.palette()
        if is_light_colour(palette.window().color()):  # Light theme
            colour = QtGui.QColor("#F5F5DC")
        else:  # Dark theme
            colour = QtGui.QColor("#224867")

        palette.setColor(QtGui.QPalette.ColorRole.Window, colour)
        self.setPalette(palette)
        # TODO: Fix background outside rounded frame on Windows
        self.setAutoFillBackground(True)

        self.setFrameStyle(QtWidgets.QFrame.Shape.Box | QtWidgets.QFrame.Shadow.Plain)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed
        )

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Handles events for watched objects.

        Args:
            watched (QtCore.QObject): Watched object for which to handle the event.
            event (QtCore.QEvent): Event to handle.

        Returns:
            bool: Whether the event was handled.
        """
        # Handle mouse events here rather than override signal handlers as QFrame does
        # not normally receive mouse events.
        if event.type() == QtCore.QEvent.Type.MouseButtonRelease:
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                close_rectangle = QtCore.QRect(
                    self.separator.mapToParent(self.separator.rect().topRight()),
                    self.frameRect().bottomRight(),
                )
                if close_rectangle.contains(event.position().toPoint()):
                    self.removal_requested.emit()
                    return True
            elif event.button() == QtCore.Qt.MouseButton.RightButton:
                self.removal_requested.emit()
                return True

        return super().eventFilter(watched, event)


class StructureTagHolderWidget(QtWidgets.QScrollArea):
    """A tag holder area for displaying a list of structure tag widgets.

    The layout of the scroll area handles putting tags on a new row if the current row
    would overflow.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self._tags = {}

        #
        layout = FlowLayout()

        #
        widget = QtWidgets.QWidget()

        widget.setContentsMargins(11, 11, 11, 11)
        widget.setLayout(layout)

        self.setWidget(widget)

        #
        self.setWidgetResizable(True)

    @QtCore.Slot()
    def add_tag_from_index(self, index: QtCore.QModelIndex) -> None:
        """Adds a structure tag from an index into an ABAStructureTreeModel.

        Args:
            index (QtCore.QModelIndex): Index into the model.
        """
        tag = StructureTagWidget(index.internalPointer().name)
        self._tags[tag] = index

        # Uncheck its item to trigger its own removal from self._tags
        tag.removal_requested.connect(
            lambda: index.model().setData(
                index,
                QtCore.Qt.CheckState.Unchecked,
                QtCore.Qt.ItemDataRole.CheckStateRole,
            )
        )

        layout = self.widget().layout()
        layout.addWidget(tag)

    @QtCore.Slot()
    def remove_tag_from_index(self, index: QtCore.QModelIndex) -> None:
        """Removes a structure tag based on an index into an ABAStructureTreeModel.

        Args:
            index (QtCore.QModelIndex): Index into the model.
        """
        name = index.internalPointer().name
        tag = None
        for tag in self._tags.keys():
            if tag.name == name:
                break
        else:
            _module_logger.warning(
                f"Attempted to remove a structure tag that was not present in the "
                f"holder (name: {tag.name}."
            )

        if tag is not None:
            self._tags.pop(tag)
            tag.deleteLater()


class BoldLabel(QtWidgets.QLabel):
    def __init__(self, text: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(text, parent)

        font = QtGui.QFont()
        font.setBold(True)
        self.setFont(font)

        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Maximum
        )


class VerticalSeparator(QtWidgets.QFrame):
    def __init__(
        self, line_width: int = 1, parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)

        self.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.setLineWidth(line_width)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Maximum
        )


class HorizontalSeparator(QtWidgets.QFrame):
    def __init__(
        self, line_width: int = 1, parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)

        self.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        self.setLineWidth(line_width)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Expanding
        )


class OneHeaderFrameLayout(QtWidgets.QGridLayout):
    def __init__(
        self,
        header: str,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)

        self.addWidget(BoldLabel(header), 0, 0, 1, -1)
        self.addWidget(VerticalSeparator(), 1, 0, 1, -1)

        self.setRowStretch(2, 1)

        self.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMaximumSize)

    def add_widget(self, widget: QtWidgets.QWidget) -> None:
        self.addWidget(
            widget, 2, 0, 1, -1, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter
        )

    def add_layout(self, layout: QtWidgets.QLayout) -> None:
        self.addLayout(layout, 2, 0, 1, -1)


class TableWidget(QtWidgets.QTableWidget):
    def __init__(
        self,
        row_count: int,
        headers: list[str],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(row_count, len(headers), parent)

        self.setHorizontalHeaderLabels(headers)
        self.horizontalHeader().setDefaultAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter
        )
        for i in range(len(headers)):
            self.setColumnWidth(i, 150)

        self.verticalHeader().hide()

        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        self.setFixedWidth(150 * len(headers) + 1)
        self.setFixedHeight(
            self.horizontalHeader().height() + self.rowHeight(0) * row_count
        )

        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def setItem(self, row: int, column: int, item: QtWidgets.QTableWidgetItem) -> None:
        super().setItem(row, column, item)

        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)


class CollapsibleWidget(QtWidgets.QWidget):
    """A collapsible widget using an animation to expand and collapse.

    Adapted from a StackOverflow answer[1].

    Attributes:
        animation_duration (int): Duration for the expand/collapse animation. Set to 0
                                  to make it instantaneous.
        toggle_button (QtWidgets.QToolButton): Button on which the user clicks to
                                               trigger the animation.
        toggle_animation (QtCore.QParallelAnimationGroup): Animation group for the
                                                           transition between collapsed
                                                           and expanded.
        content_area (QtWidgets.QScrollArea): Widget containing the inner layout. This
                                              is where new row widgets get added.

    References:
        [1]: https://stackoverflow.com/a/52617714
    """

    animation_duration: int
    expanded: bool

    toggle_button: QtWidgets.QToolButton
    toggle_animation: QtCore.QParallelAnimationGroup
    content_area: QtWidgets.QScrollArea

    def __init__(
        self,
        title: str = "",
        animation_duration: int = 500,
        expanded: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """A collapsible widget using an animation to expand and collapse.

        Args:
            title (str, optional): Title used for the toggle button of the widget.
            animation_duration (int, optional): Duration of the collapse/expand
                                                animation. Set to 0 to make it
                                                instantaneous.
            expanded (bool, optional): Whether to start expanded.
            parent (Optional[QtWidgets.QWidget], optional): Parent of the widget.
        """
        super().__init__(parent)

        #
        # A duration of 1 breaks animations
        self.animation_duration = max(animation_duration, 2)

        #
        toggle_button = QtWidgets.QToolButton(
            text=title, checkable=False, checked=False
        )
        toggle_button.setStyleSheet("QToolButton { border: none; }")
        toggle_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        toggle_button.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        toggle_button.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Maximum
        )
        toggle_button.pressed.connect(self.on_pressed)

        self.toggle_button = toggle_button

        #
        content_area = QtWidgets.QScrollArea()
        content_area.setMinimumHeight(0)
        content_area.setMaximumHeight(0)
        content_area.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed
        )
        content_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self.content_area = content_area

        #
        layout = QtWidgets.QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(toggle_button)
        layout.addWidget(content_area)

        self.setLayout(layout)

        #
        toggle_animation = QtCore.QParallelAnimationGroup(self)
        toggle_animation.addAnimation(QtCore.QPropertyAnimation(self, b"minimumHeight"))
        toggle_animation.addAnimation(QtCore.QPropertyAnimation(self, b"maximumHeight"))
        toggle_animation.addAnimation(
            QtCore.QPropertyAnimation(self.content_area, b"maximumHeight")
        )

        self.toggle_animation = toggle_animation

        #
        content_layout = QtWidgets.QVBoxLayout()
        content_layout.setContentsMargins(
            toggle_button.iconSize().width() * 2,
            toggle_button.iconSize().width() // 2,
            toggle_button.iconSize().width() // 2,
            toggle_button.iconSize().width() // 2,
        )

        self.set_content_layout(content_layout)

        #
        self.expanded = expanded
        self.set_initial_state(expanded)

    def set_initial_state(self, expanded: bool) -> None:
        if expanded:
            self.toggle(immediate=True)

    def setup_animation(self) -> None:
        collapsed_height = self.sizeHint().height() - self.content_area.maximumHeight()
        content_height = self.content_area.layout().sizeHint().height()
        for i in range(self.toggle_animation.animationCount()):
            animation = self.toggle_animation.animationAt(i)
            animation.setDuration(self.animation_duration)

            animation.setStartValue(collapsed_height)
            animation.setEndValue(collapsed_height + content_height)

        content_animation = self.toggle_animation.animationAt(
            self.toggle_animation.animationCount() - 1
        )
        content_animation.setDuration(self.animation_duration)

        content_animation.setStartValue(0)
        content_animation.setEndValue(content_height)

    def add_row(self, text: Optional[str], widget: QtWidgets.QWidget) -> None:
        row_layout = QtWidgets.QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)

        if text is not None:
            row_layout.addWidget(QtWidgets.QLabel(text))
            row_layout.addStretch()
        row_layout.addWidget(widget)

        row_widget = QtWidgets.QWidget()
        row_widget.setLayout(row_layout)

        self.content_area.layout().addWidget(row_widget)
        self.setup_animation()

    def set_content_layout(self, layout: QtWidgets.QLayout) -> None:
        current_layout = self.content_area.layout()
        if current_layout is not None:
            del current_layout

        self.content_area.setLayout(layout)
        self.setup_animation()

    def toggle(self, immediate: bool = False) -> None:
        if immediate:
            old_animation_duration = self.animation_duration
            self.animation_duration = 2
            self.setup_animation()
            self.animation_duration = old_animation_duration

        connect_single_shot_slot(self.toggle_animation.finished, self.setup_animation)
        self.toggle_button.click()

    @QtCore.Slot()
    def on_pressed(self) -> None:
        self.toggle_button.setArrowType(
            QtCore.Qt.ArrowType.RightArrow
            if self.expanded
            else QtCore.Qt.ArrowType.DownArrow
        )
        self.toggle_animation.setDirection(
            QtCore.QAbstractAnimation.Direction.Backward
            if self.expanded
            else QtCore.QAbstractAnimation.Direction.Forward
        )
        self.toggle_animation.start()
        self.expanded = ~self.expanded


class SwitchWidget(QtWidgets.QWidget):
    index: int

    up_arrow: QtWidgets.QToolButton
    down_arrow: QtWidgets.QToolButton
    inner_widget: QtWidgets.QWidget
    inner_layout: QtWidgets.QVBoxLayout()

    move_up_requested: QtCore.Signal = QtCore.Signal(int)
    move_down_requested: QtCore.Signal = QtCore.Signal(int)

    def __init__(
        self,
        widget: QtWidgets.QWidget,
        index: int,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        #
        self.index = index

        #
        up_arrow = QtWidgets.QToolButton()
        up_arrow.setStyleSheet("QToolButton { border: none; }")
        up_arrow.setArrowType(QtCore.Qt.ArrowType.UpArrow)

        up_arrow.clicked.connect(lambda: self.move_up_requested.emit(self.index))

        self.up_arrow = up_arrow

        #
        down_arrow = QtWidgets.QToolButton()
        down_arrow.setStyleSheet("QToolButton { border: none; }")
        down_arrow.setArrowType(QtCore.Qt.ArrowType.DownArrow)

        down_arrow.clicked.connect(lambda: self.move_down_requested.emit(self.index))

        self.down_arrow = down_arrow

        #
        inner_widget = QtWidgets.QWidget()

        self.inner_widget = inner_widget

        #
        inner_layout = QtWidgets.QVBoxLayout()
        inner_layout.setContentsMargins(0, 0, 0, 0)

        self.inner_layout = inner_layout

        #
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(up_arrow, 1, 0)
        layout.addWidget(down_arrow, 2, 0)
        layout.addWidget(HorizontalSeparator(), 0, 1, -1, 1)
        layout.addLayout(inner_layout, 0, 2, 4, 1)

        layout.setRowStretch(0, 1)
        layout.setRowStretch(3, 1)
        layout.setColumnStretch(2, 1)

        self.setLayout(layout)

        #
        self.set_widget(widget)

    def set_widget(self, widget: Optional[QtWidgets.QWidget]) -> None:
        if self.inner_widget is not None:
            self.inner_widget.setParent(None)
            self.inner_widget.deleteLater()

        if widget is None:
            return

        self.inner_widget = widget
        self.inner_layout.addWidget(
            widget, alignment=QtCore.Qt.AlignmentFlag.AlignVCenter
        )


class SwitchWidgetContainer(QtWidgets.QScrollArea):
    widget_list: list[SwitchWidget]

    content_layout: QtWidgets.QVBoxLayout

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self.widget_list = []

        #
        self.setWidgetResizable(True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        # self.setMinimumHeight(1000)

        #
        content_layout = QtWidgets.QVBoxLayout()
        content_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        self.content_layout = content_layout

        self.setLayout(content_layout)

    def add_widget(self, widget: QtWidgets.QWidget) -> None:
        switch_widget = SwitchWidget(widget, len(self.widget_list))
        switch_widget.move_up_requested.connect(self.move_widget_up)
        switch_widget.move_down_requested.connect(self.move_widget_down)

        self.content_layout.addWidget(
            switch_widget, alignment=QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.widget_list.append(switch_widget)

    def swap_widgets(
        self, bottom_widget: SwitchWidget, top_widget: SwitchWidget
    ) -> None:
        # We need to takeAt the top index first to avoid a segfault
        top_widget_index = self.content_layout.indexOf(top_widget)
        top_widget_item = self.content_layout.takeAt(top_widget_index)
        bottom_widget_index = self.content_layout.indexOf(bottom_widget)
        bottom_widget_item = self.content_layout.takeAt(bottom_widget_index)

        self.content_layout.insertItem(bottom_widget_index, top_widget_item)
        self.content_layout.insertItem(top_widget_index, bottom_widget_item)

        top_index = top_widget.index
        bottom_index = bottom_widget.index
        bottom_widget.index = top_index
        top_widget.index = bottom_index

    @QtCore.Slot()
    def move_widget_up(self, index: int) -> None:
        if index < 1:
            return

        bottom_widget = self.widget_list[index - 1]
        top_widget = self.widget_list[index]
        self.widget_list[index] = bottom_widget
        self.widget_list[index - 1] = top_widget

        self.swap_widgets(bottom_widget, top_widget)

    @QtCore.Slot()
    def move_widget_down(self, index: int) -> None:
        if index > len(self.widget_list) - 2:
            return

        bottom_widget = self.widget_list[index]
        top_widget = self.widget_list[index + 1]
        self.widget_list[index + 1] = bottom_widget
        self.widget_list[index] = top_widget

        self.swap_widgets(bottom_widget, top_widget)


class BasicMenuBar(QtWidgets.QMenuBar):
    file_menu: QtWidgets.QMenu
    open_action: QtGui.QAction
    close_action: QtGui.QAction
    exit_action: QtGui.QAction

    open_requested: QtCore.Signal = QtCore.Signal()
    close_requested: QtCore.Signal = QtCore.Signal()
    exit_requested: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        file_menu = self.addMenu("&File")

        self.file_menu = file_menu

        #
        open_action = QtGui.QAction("&Open", file_menu)

        open_action.setStatusTip("Open an existing project")
        open_action.setShortcut(QtGui.QKeySequence("Ctrl+o"))
        open_action.setShortcutContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        open_action.triggered.connect(self.open_requested.emit)

        self.open_action = open_action

        #
        close_action = QtGui.QAction("&Close", file_menu)

        close_action.setStatusTip("Close the current project")
        close_action.setShortcut(QtGui.QKeySequence("Ctrl+w"))
        close_action.setShortcutContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        close_action.triggered.connect(self.close_requested.emit)

        self.close_action = close_action

        #
        exit_action = QtGui.QAction("E&xit", file_menu)

        exit_action.setStatusTip("Exit the application")
        exit_action.setShortcut(QtGui.QKeySequence("Ctrl+Shift+w"))
        exit_action.setShortcutContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        exit_action.triggered.connect(self.exit_requested.emit)

        self.exit_action = exit_action

        #
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        file_menu.addAction(close_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)


class BasicApplicationWindow(QtWidgets.QMainWindow, FakeQtABC):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self.set_up_menu_bar()

        #
        status_bar = self.statusBar()
        status_bar.setObjectName("MainStatusBar")

        frame_colour = lua_aware_shift(
            status_bar.palette().window().color(), 10
        ).getRgb()

        status_bar.setStyleSheet(
            "#MainStatusBar {{ border-top: 1px solid rgba({}, {}, {}, {}); }}".format(
                *frame_colour
            )
        )

    def set_up_menu_bar(self) -> None:
        menu_bar = BasicMenuBar()

        menu_bar.open_requested.connect(self.show_open_project_dialog)
        menu_bar.close_requested.connect(self.close_project)
        menu_bar.exit_requested.connect(self.exit_application)

        self.setMenuBar(menu_bar)

    @QtCore.Slot()
    def show_open_project_dialog(self) -> None:
        dialog = OpenProjectDialog(self)
        dialog.submitted.connect(self.open_project)
        dialog.exec()

    @abstractmethod
    @QtCore.Slot()
    def open_project(self, project_file_path: str) -> None:
        raise NotImplementedError

    @QtCore.Slot()
    def close_project(self) -> None:
        if self.close():
            try:
                self.parent().open_centralised_window()
            except AttributeError:
                _module_logger.error(
                    "Failed to open centralised window, quitting application instead."
                )

    @QtCore.Slot()
    def exit_application(self) -> None:
        if self.close():
            exit()


class DynamicThemeIcon(QtGui.QIcon):
    """An icon that automatically adjusts its colour to match the theme.

    Note that this relies on the input images being "binarisable" to background versus
    foreground (e.g., SVGs).

    Adapted from: https://stackoverflow.com/a/37213313.
    """

    _pixmap: QtGui.QPixmap

    def __init__(self, icon_path: str | Path) -> None:
        pixmap = QtGui.QPixmap(icon_path)

        self._pixmap = pixmap.copy()

        painter = QtGui.QPainter(pixmap)
        painter.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
        )

        painter.setBrush(
            QtGui.QBrush(QtWidgets.QApplication.instance().palette().text())
        )

        painter.drawRect(pixmap.rect())

        painter.end()

        super().__init__(pixmap)


class ShortcutAwareFilter(QtCore.QObject):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        if not hasattr(parent, "shortcut"):
            # Filter is useless on a widget that does not have a shortcut
            self.deleteLater()

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.ToolTip:
            if not watched.shortcut().isEmpty():
                shortcut_text = watched.shortcut().toString(
                    QtGui.QKeySequence.SequenceFormat.NativeText
                )
                watched.setToolTip(watched.toolTip() + "  " + shortcut_text)

            # Delete itself once the job is done
            self.deleteLater()

        return super().eventFilter(watched, event)


class ShortcutAwarePushButton(QtWidgets.QPushButton):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self.installEventFilter(ShortcutAwareFilter(self))


class ShortcutAwareToolButton(QtWidgets.QToolButton):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self.installEventFilter(ShortcutAwareFilter(self))


class CircularPushButton(ShortcutAwarePushButton):
    """A class implementing a circular version of PushButtons.

    Adapted from: https://forum.qt.io/post/579342.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        background = (
            self.palette().midlight() if self.isDown() else self.palette().button()
        )
        diameter = round(min(self.width(), self.height()) * 0.95)

        painter = QtGui.QPainter(self)

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QtGui.QPen(QtGui.QBrush(background), 2))
        painter.setBrush(QtGui.QBrush(background))

        painter.translate(self.width() / 2, self.height() / 2)
        painter.drawEllipse(
            QtCore.QRect(round(-diameter / 2), round(-diameter / 2), diameter, diameter)
        )
        painter.drawPixmap(
            QtCore.QRect(
                round(-diameter / 2), round(-diameter / 2), diameter, diameter
            ),
            self.icon().pixmap(diameter),
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        diameter = min(self.width(), self.height()) + 4
        x_off = round((self.width() - diameter) / 2)
        y_off = round((self.height() - diameter) / 2)

        self.setMask(
            QtGui.QRegion(
                x_off, y_off, diameter, diameter, QtGui.QRegion.RegionType.Ellipse
            )
        )


class MouseTrackingFilter(QtCore.QObject):
    leaving_callback: Optional[Callable]
    watched_type: Any
    timer: QtCore.QTimer

    def __init__(
        self,
        tracking_callback: Callable,
        leaving_callback: Optional[Callable] = None,
        watched_type: Any = object,
        polling_rate: int = 30,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        #
        self.leaving_callback = leaving_callback
        self.watched_type = watched_type

        #
        timer = QtCore.QTimer()

        timer.setInterval(int(1000 / polling_rate))
        timer.timeout.connect(tracking_callback)

        self.timer = timer

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if isinstance(watched, self.watched_type):
            match event.type():
                case QtCore.QEvent.Type.Enter:
                    self.timer.start()
                case QtCore.QEvent.Type.Leave:
                    self.timer.stop()
                    if self.leaving_callback is not None:
                        self.leaving_callback()

        return super().eventFilter(watched, event)


class AnimatedHeightWidget(QtWidgets.QWidget):
    """A base class for animating widgets by growing/shrinking their height.

    The animation is started on `showEvent`s and `hideEvent`s.
    """

    def __init__(
        self,
        animated: bool = True,
        duration: int = 200,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._animated = animated
        self.duration = duration
        self._setup_required = animated
        self.animation_group = None

        if animated:
            self.setMinimumHeight(0)
            self.setMaximumHeight(0)

    @QtCore.Property(bool)
    def animated(self) -> bool:
        return self._animated

    @animated.setter
    def animated(self, value: bool) -> None:
        self._animated = value
        self._setup_required = value

    def set_up_animation(self) -> None:
        if not self.animated:
            return

        animation_group = QtCore.QParallelAnimationGroup(self)

        minimum_height_animation = QtCore.QPropertyAnimation(self, b"minimumHeight")
        minimum_height_animation.setStartValue(0)
        minimum_height_animation.setEndValue(self.sizeHint().height())
        minimum_height_animation.setDuration(self.duration)

        maximum_height_animation = QtCore.QPropertyAnimation(self, b"maximumHeight")
        maximum_height_animation.setStartValue(0)
        maximum_height_animation.setEndValue(self.sizeHint().height())
        maximum_height_animation.setDuration(self.duration)

        animation_group.addAnimation(minimum_height_animation)
        animation_group.addAnimation(maximum_height_animation)

        self.animation_group = animation_group

        self._setup_required = False

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        if self._setup_required:
            self.set_up_animation()

        if not self.animated:
            return super().showEvent(event)

        self.animation_group.setDirection(QtCore.QAbstractAnimation.Direction.Forward)
        self.animation_group.start()

        return super().showEvent(event)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        if self._setup_required:
            self.set_up_animation()

        if not self.animated:
            return super().hideEvent(event)

        self.animation_group.setDirection(QtCore.QAbstractAnimation.Direction.Backward)
        self.animation_group.start()

        return super().hideEvent(event)


class SliceNamesComboBox(QtWidgets.QComboBox):
    file_picked: QtCore.Signal = QtCore.Signal(str)

    name_to_path_map: dict[str, str]

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.name_to_path_map = {}

        self.currentTextChanged.connect(self.notify_change)

        self.setMinimumWidth(300)
        # Limits number of visible items to 10
        self.setStyleSheet("QComboBox { combobox-popup: 0; }")

    def parse_results(self, metadata_path: str) -> None:
        with open(metadata_path) as handle:
            paths = json.load(handle).get("slice_paths")

        if paths is None:
            return

        self.clear()

        metadata_root = Path(metadata_path).parent
        self.addItem("")
        for file_path in paths:
            file_name = Path(file_path).stem
            self.name_to_path_map[file_name] = file_path
            self.addItem(file_name)

            if (
                not Path(file_path).exists()
                or not (
                    metadata_root
                    / f"{HistologySlice.generate_file_name_hash(file_path)}.json"
                ).exists()
            ):
                self.model().item(self.findText(file_name)).setEnabled(False)

    def clear(self) -> None:
        super().clear()
        self.name_to_path_map = {"": ""}

    @QtCore.Slot()
    def notify_change(self, file_name) -> None:
        return
        self.file_picked.emit(self.name_to_path_map[file_name])


class Canvas(FigureCanvasQTAgg):
    def __init__(self) -> None:
        figure = plt.Figure()

        self.axes = figure.add_subplot(111)

        super().__init__(figure)


class Icon(QtWidgets.QPushButton):
    def __init__(
        self,
        icon_path: Optional[str | Path] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        #
        self.setFlat(True)

        #
        if icon_path is not None:
            self.setIcon(DynamicThemeIcon(icon_path))

    def event(self, e: QtCore.QEvent) -> bool:
        if e.type() != QtCore.QEvent.Type.Paint:
            return False

        return super().event(e)


class PointGraphicsItem(QtWidgets.QGraphicsObject):
    """Graphics item shown as a point and a surrounding circle."""

    selected: QtCore.Signal = QtCore.Signal()
    deselected: QtCore.Signal = QtCore.Signal()
    clicked: QtCore.Signal = QtCore.Signal(QtCore.Qt.MouseButton)
    moved: QtCore.Signal = QtCore.Signal(QtCore.QPointF)
    deleted: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        position: QtCore.QPointF,
        size: int,
        parent: Optional[QtWidgets.QGraphicsObject] = None,
    ) -> None:
        super().__init__(parent)

        #
        self.setPos(position)
        self.size = size

        self._user_selection = True

        #
        self.setFlags(
            self.flags()
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges
        )

    @staticmethod
    def generate_pixmaps() -> None:
        """Generates and caches the relevant pixmaps for this item."""
        pixmap_out = QtGui.QPixmap(RESOURCES_ROOT / "icons" / "circle-center-icon.png")
        painter = QtGui.QPainter(pixmap_out)
        painter.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
        )
        painter.setBrush(QtGui.QBrush(QtCore.Qt.GlobalColor.blue))
        painter.drawRect(pixmap_out.rect())
        painter.end()

        pixmap_in = pixmap_out.copy()
        painter = QtGui.QPainter(pixmap_in)
        painter.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
        )
        painter.setBrush(QtGui.QBrush(QtCore.Qt.GlobalColor.green))
        painter.drawRect(pixmap_in.rect())
        painter.end()

        QtGui.QPixmapCache.insert("PointGraphicsItem_focus_out", pixmap_out)
        QtGui.QPixmapCache.insert("PointGraphicsItem_focus_in", pixmap_in)

    def boundingRect(self) -> QtCore.QRectF:
        """Returns the item's bounding rectangle.

        Returns:
            QtCore.QRectF: The bounding rectangle.
        """
        return QtCore.QRectF(-self.size / 2, -self.size / 2, self.size, self.size)

    def shape(self) -> QtGui.QPainterPath:
        """Returns the item's collision/interactable area.

        Returns:
            QtGui.QPainterPath: The collision/interactable area.
        """
        path = QtGui.QPainterPath()
        path.addEllipse(self.boundingRect())

        return path

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """Paints the item in local coordinates.

        Args:
            painter (QtGui.QPainter): Painter to use for painting.
            option (QtWidgets.QStyleOptionGraphicsItem): Options to use for painting.
            widget (Optional[QtWidgets.QWidget], optional): Widget to paint on.
        """
        pixmap_key = (
            "PointGraphicsItem_focus_in"
            if self.isSelected()
            else "PointGraphicsItem_focus_out"
        )
        pixmap = QtGui.QPixmap()
        if not QtGui.QPixmapCache.find(pixmap_key, pixmap):
            self.generate_pixmaps()
            QtGui.QPixmapCache.find(pixmap_key, pixmap)

        painter.drawPixmap(self.boundingRect(), pixmap, pixmap.rect().toRectF())

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        """Handles mouse press events."""
        super().mousePressEvent(event)

        self._button = event.button()
        self._dragging = False

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        """Handles mouse move events."""
        super().mouseMoveEvent(event)

        self._dragging = True

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        """Handles mouse release events."""
        super().mouseReleaseEvent(event)

        if not self._dragging:
            self.clicked.emit(self._button)
        self._dragging = False

    def itemChange(
        self, change: QtWidgets.QGraphicsItem.GraphicsItemChange, value: Any
    ) -> Any:
        """Handles item changes notifications.

        Args:
            change (QtWidgets.QGraphicsItem.GraphicsItemChange): Change type.
            value (Any): Change-relevant input value.

        Returns:
            Any: Change-relevant return value.
        """
        match change:
            case QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
                if self._user_selection:
                    if value:
                        self.selected.emit()
                    else:
                        self.deselected.emit()
                self._user_selection = True
            case QtWidgets.QGraphicsItem.GraphicsItemChange.ItemScenePositionHasChanged:
                self.moved.emit(value)

        return super().itemChange(change, value)

    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        """Handles focus out events."""
        super().focusOutEvent(event)
        self.setSelected(False)

    def select(self) -> None:
        """Selects the item without direct user input (i.e., programmatically)."""
        self._user_selection = False
        self.setSelected(True)

    def deselect(self) -> None:
        """Deselects the item without direct user input (i.e., programmatically)."""
        self._user_selection = False
        self.setSelected(False)

    def delete(self) -> None:
        """Deletes the widget while broadcasting its deletion."""
        self.deleteLater()
        self.deleted.emit()


class ZoomAndPanView(QtWidgets.QGraphicsView):
    """A view providing a zoom-ad-pan mechanism using the mouse.

    The view also provides a way to give a rectangle in scene coordinates which should
    by default be shown as zoomed-in as possible while fitting completely in view when
    the view is first made visible.
    Once the user interacts with the view to pan and zoom, the relative size of the
    focus rectangle will be maintained.

    Attributes:
        general_zoom (float):
            General level of zoom controlled through user interaction. This is limited
            to values between 0.5 and 25 (i.e., zoom out to half the size and zoom in to
            25 times the size).
        focus_zoom (float):
            Level of zoom required to fit `focus_rect` into view. This makes
            `focus_rect` fill the view when `general_zoom` is 1.0.
        view_centre (QtCore.QPointF):
        focus_rect (QtCore.QRectF):
    """

    general_zoom: float = 1.0
    focus_zoom: float = 1.0
    view_centre: QtCore.QPointF = QtCore.QPointF(0, 0)
    focus_rect: QtCore.QRectF

    # Position is in scene coordinates
    clicked: QtCore.Signal = QtCore.Signal(QtCore.QPointF)

    def __init__(
        self,
        scene: QtWidgets.QGraphicsScene,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(scene, parent)

        #
        self.general_zoom = 1.0
        self.view_centre = QtCore.QPointF(0, 0)
        self.focus_rect = scene.sceneRect()

        self._dragging = False
        self._drag_button = QtCore.Qt.MouseButton.LeftButton
        self._zoom_modifier = None

        #
        self.setTransformationAnchor(
            QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter
        )

        #
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.horizontalScrollBar().valueChanged.connect(self.ensure_focus_rect_visible)

        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalScrollBar().valueChanged.connect(self.ensure_focus_rect_visible)

    def set_drag_button(self, button: QtCore.Qt.MouseButton) -> None:
        self._drag_button = button

    def set_focus_rect(
        self,
        rect: QtCore.QRectF,
        centre_on: bool = True,
        reset_general_zoom: bool = True,
    ) -> None:
        """Sets the focus rectangle.

        Args:
            rect (QtCore.QRectF):
                Rectangle which should always have a single visible pixel. This should
                be in scene coordinates.
            centre_on (bool, optional): Whether to centre on the focus rect.
            reset_general_zoom (bool, optional): Whether to reset the general zoom to 1.
        """
        self.focus_rect = rect
        self.update_focus_zoom()

        if centre_on:
            self.centre_on_focus()
        if reset_general_zoom:
            self.general_zoom = 1
            self.update_focus_zoom()

    def set_zoom_modifier(
        self, modifier: QtCore.Qt.KeyboardModifier.ControlModifier
    ) -> None:
        self._zoom_modifier = modifier

    def update_focus_zoom(self) -> None:
        """Updates the focus zoom level."""
        if self.focus_rect.width() <= 0 or self.focus_rect.height() <= 0:
            return

        view_rect = self.mapToScene(self.viewport().geometry()).boundingRect()

        zoom = min(
            view_rect.width() / self.focus_rect.width() * self.general_zoom,
            view_rect.height() / self.focus_rect.height() * self.general_zoom,
        )

        self.focus_zoom *= zoom
        self.scale(zoom, zoom)

    def update_view_centre(self) -> None:
        """Updates the view centre with the current viewport centre."""
        self.view_centre = self.mapToScene(self.viewport().rect().center())

    def ensure_focus_rect_visible(self) -> None:
        """Ensures at least a pixel of the focus rectangle is visible.

        Note the visible pixel will be a view pixel, not a scene pixel.
        """
        view_rect = self.viewport().rect()
        focus_rect = self.mapFromScene(self.focus_rect).boundingRect()
        # Offset left and top edges to ensure at least a pixel can be visible along them
        view_rect.adjust(1, 1, 0, 0)

        horizontal_bar = self.horizontalScrollBar()
        vertical_bar = self.verticalScrollBar()

        # Handle case where focus is to the left of the view
        if view_rect.left() > focus_rect.right():
            delta = view_rect.left() - focus_rect.right()
            horizontal_bar.setValue(horizontal_bar.value() - delta)
        # Handle case where focus is below the view
        if view_rect.bottom() < focus_rect.top():
            delta = focus_rect.top() - view_rect.bottom()
            vertical_bar.setValue(vertical_bar.value() + delta)
        # Handle case where focus is to the right of the view
        if view_rect.right() < focus_rect.left():
            delta = focus_rect.left() - view_rect.right()
            horizontal_bar.setValue(horizontal_bar.value() + delta)
        # Handle case where focus is above the view
        if view_rect.top() > focus_rect.bottom():
            delta = view_rect.top() - focus_rect.bottom()
            vertical_bar.setValue(vertical_bar.value() - delta)

    def centerOn(self, position: QtCore.QPoint | QtCore.QPointF) -> None:
        """Centres the view on the given scene coordinates.

        Args:
            position (QtCore.QPoint | QtCore.QPointF): Position to centre on.
        """
        if isinstance(position, QtCore.QPoint):
            position = position.toPointF()
        self.view_centre = position

        super().centerOn(position)

    def centre_on_focus(self) -> None:
        if self.focus_rect is not None:
            self.centerOn(self.focus_rect.center())

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == self._drag_button:
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
            if self._drag_button != QtCore.Qt.MouseButton.LeftButton:
                self.setInteractive(False)  # Prevent moving items with drag button
            if self._drag_button != QtCore.Qt.MouseButton.LeftButton:
                event = QtGui.QMouseEvent(
                    QtCore.QEvent.Type.MouseButtonPress,
                    event.position(),
                    QtCore.Qt.MouseButton.LeftButton,
                    event.buttons(),
                    event.modifiers(),
                )

        super().mousePressEvent(event)

        self._dragging = False

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handles mouse release events.

        Args:
            event (QtGui.QMouseEvent): Event to handle.
        """
        if event.button() == self._drag_button:
            if self._drag_button != QtCore.Qt.MouseButton.LeftButton:
                event = QtGui.QMouseEvent(
                    QtCore.QEvent.Type.MouseButtonRelease,
                    event.position(),
                    QtCore.Qt.MouseButton.LeftButton,
                    event.buttons(),
                    event.modifiers(),
                )

            # Update the view centre after dragging
            self.update_view_centre()
            self._dragging = False

        super().mouseReleaseEvent(event)
        if self._drag_button != QtCore.Qt.MouseButton.LeftButton:
            self.setInteractive(True)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)

        # Notify of single clicks (no dragging)
        if not self._dragging and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self.mapToScene(event.pos()))

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        super().mouseMoveEvent(event)

        self._dragging = True

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """Handles wheel events.

        This allows zooming in and out around the cursor.

        Args:
            event (QtGui.QWheelEvent): Event to handle
        """
        if self._zoom_modifier is not None and self._zoom_modifier != event.modifiers():
            self.horizontalScrollBar().setEnabled(False)
            self.verticalScrollBar().setEnabled(False)
            super().wheelEvent(event)
            self.horizontalScrollBar().setEnabled(True)
            self.verticalScrollBar().setEnabled(True)
            return

        # Zoom calculation
        zoom_factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25
        new_zoom_level = self.general_zoom * zoom_factor
        if new_zoom_level < 0 or new_zoom_level > 25:
            # Limit the zoom range to half the original size to 25 times the original
            # size. This is more of a UX limitation than a technical one.
            return
        self.general_zoom = new_zoom_level
        self.focus_zoom *= zoom_factor

        # Scaling
        cursor = self.window().cursor()
        original_cursor_position = self.mapToScene(self.mapFromGlobal(cursor.pos()))
        self.scale(zoom_factor, zoom_factor)
        new_cursor_position = self.mapToScene(self.mapFromGlobal(cursor.pos()))

        # Correct so that the cursor is still above the same scene coordinates (i.e.,
        # cursor-centric zooming)
        viewport_centre = (
            self.mapToScene(self.viewport().rect()).boundingRect().center()
        )
        self.centerOn(
            viewport_centre + (original_cursor_position - new_cursor_position)
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        """Handles resize events.

        This ensures the view will remain centred on the same coordinates and that the
        relative size of the focus rectangle grows and shrinks with the view.

        Args:
            event (QtGui.QResizeEvent): Event to handle.
        """
        super().resizeEvent(event)

        self.centerOn(self.view_centre)
        self.update_focus_zoom()

    # noinspection PyTypeChecker
    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        self.scene().setFocusItem(None)  # type: ignore[arg-type]
        super().focusOutEvent(event)


class AnimatedCheckBox(QtWidgets.QCheckBox):
    """Animated toggle checkbox widget.

    This is slightly adapted from the following tutorial:
    https://www.pythonguis.com/tutorials/pyside-animated-widgets/
    """

    _transparent_pen = QtGui.QPen(QtCore.Qt.GlobalColor.transparent)
    _light_grey_pen = QtGui.QPen(QtCore.Qt.GlobalColor.lightGray)

    def __init__(
        self,
        bar_colour: QtCore.Qt.GlobalColor = QtCore.Qt.GlobalColor.gray,
        checked_colour: str = "#0099ff",
        handle_colour: QtCore.Qt.GlobalColor = QtCore.Qt.GlobalColor.white,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        #
        self._bar_brush = QtGui.QBrush(bar_colour)
        self._bar_checked_brush = QtGui.QBrush(checked_colour)

        self._handle_brush = QtGui.QBrush(handle_colour)
        self._handle_checked_brush = QtGui.QBrush(
            QtGui.QColor(checked_colour).lighter()
        )

        #
        self.setContentsMargins(0, 0, 0, 0)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed
        )
        self._handle_position = 0

        #
        self.animation = QtCore.QPropertyAnimation(self, b"handle_position", self)
        self.animation.setEasingCurve(QtCore.QEasingCurve.Type.InOutCubic)
        self.animation.setDuration(200)

        self.checkStateChanged.connect(self.set_up_animation)

    @QtCore.Property(float)
    def handle_position(self) -> int:
        return self._handle_position

    @handle_position.setter
    def handle_position(self, pos: float) -> None:
        self._handle_position = pos
        self.update()

    def hitButton(self, pos: QtCore.QPoint) -> bool:
        return self.contentsRect().contains(pos)

    def sizeHint(self) -> QtCore.QSize:
        # TODO: Figure out how to compute a line edit height without creating an object
        line_edit = QtWidgets.QLineEdit()
        line_edit.setFont(self.font())

        return QtCore.QSize(
            line_edit.sizeHint().height() * 2, line_edit.sizeHint().height()
        )

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        contents_rect = self.contentsRect()
        # -2 to fit inside potential borders
        handle_radius = 0.5 * (contents_rect.height() - 2)

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        bar_rect = QtCore.QRectF(
            0,
            0,
            contents_rect.width() - handle_radius,
            0.5 * contents_rect.height(),
        )
        bar_rect.moveCenter(contents_rect.center())
        # Adjust bar_rect so that it fits evenly around handle centre
        if handle_radius % 1 == 0:
            bar_rect.translate(0, 1)
        else:
            bar_rect.adjust(0, 0, 0, 1)
        rounding = bar_rect.height() / 2

        trail_length = contents_rect.width() - 2 * handle_radius
        x_pos = contents_rect.x() + handle_radius + trail_length * self._handle_position

        # Draw the trail
        painter.setPen(self._transparent_pen)
        if self.isChecked():
            painter.setBrush(self._bar_checked_brush)
            painter.drawRoundedRect(bar_rect, rounding, rounding)
            painter.setBrush(self._handle_checked_brush)
        else:
            painter.setBrush(self._bar_brush)
            painter.drawRoundedRect(bar_rect, rounding, rounding)
            painter.setPen(self._light_grey_pen)
            painter.setBrush(self._handle_brush)

        # Draw the handle
        painter.drawEllipse(
            QtCore.QPointF(x_pos, contents_rect.top() + contents_rect.height() / 2),
            handle_radius,
            handle_radius,
        )

        painter.end()

    @QtCore.Slot(QtCore.Qt.CheckState)
    def set_up_animation(self, value: QtCore.Qt.CheckState) -> None:
        self.animation.stop()
        if value == QtCore.Qt.CheckState.Checked:
            self.animation.setEndValue(1)
        else:
            self.animation.setEndValue(0)
        self.animation.start()


class TitleFrame(QtWidgets.QFrame):
    """A frame which holds its title on the frame.

    A rough representation looks like so:
     -- Title -----------
    |                    |
    |                    |
     -- -----------------

    Attributes:
        title (str): Title of the frame
        bold (bool): Whether to render the title bold.
        italic (bool): Whether to render the title in italics.
    """

    def __init__(
        self,
        title: str = "",
        bold: bool = False,
        italic: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        #
        # Add space padding to avoid clipping on Windows
        if title:
            title = " " + title + " "
        self.title = title
        self.bold = bold
        self.italic = italic

        #
        self.adjust_margins()
        self.setFrameStyle(QtWidgets.QFrame.Shape.Box | QtWidgets.QFrame.Shadow.Plain)

    def adjust_font(self, font: QtGui.QFont) -> None:
        """Adjusts the provided font with own settings.

        The font is modified in-place to use the `bold` and `italic` settings of the
        current object.

        Args:
            font (QtGui.QFont): Font to adjust.
        """
        font.setBold(self.bold)
        font.setItalic(self.italic)

    def adjust_margins(self) -> None:
        """Adjusts the margins to fit the title on the frame."""
        current_font = self.font()

        margin_font = QtGui.QFont(current_font)
        self.adjust_font(margin_font)
        margin_font.setBold(True)

        metrics = QtGui.QFontMetrics(margin_font)
        margin = metrics.boundingRect(self.title).height() - metrics.xHeight()
        # Janky adjustment, seems to work with most "normal" fonts. See `paintEvent`.
        if "win" in sys.platform:
            margin -= self.fontMetrics().xHeight()
        self.setContentsMargins(margin, margin, margin, margin)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Handles paint events.

        The event is handled by painting the frame, erasing the title rect, then drawing
        the title text.

        Args:
            event (QtGui.QPaintEvent): Event to handle.
        """
        super().paintEvent(event)

        painter = QtGui.QPainter(self)

        font = painter.font()
        self.adjust_font(font)
        painter.setFont(font)

        text_option = QtGui.QTextOption(QtCore.Qt.AlignmentFlag.AlignCenter)
        text_option.setWrapMode(QtGui.QTextOption.NoWrap)

        text_rect = (
            painter.fontMetrics().boundingRect(self.title, text_option).toRectF()
        )
        text_rect.moveBottomLeft(self.frameRect().topLeft())
        text_rect.translate(20, painter.fontMetrics().xHeight())
        # Janky adjustment, seems to work with most "normal" fonts I've tested to ensure
        # the text aligns with the frame vertically.
        if "win" in sys.platform:
            text_rect.translate(0, painter.fontMetrics().xHeight())

        erase_rect = QtCore.QRectF(text_rect)
        erase_rect.adjust(-5, 0, 5, 0)
        painter.eraseRect(erase_rect)

        painter.drawText(text_rect, self.title, text_option)


class ToggleWidget(QtWidgets.QFrame):
    def __init__(
        self,
        header_text: str = "",
        sub_item: QtWidgets.QWidget | QtWidgets.QLayout | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        #
        border_colour = self.palette().window().color()
        if is_light_colour(border_colour):  # Light theme
            border_colour = border_colour.darker()
        else:
            border_colour = border_colour.lighter()

        #
        header_label = QtWidgets.QLabel(header_text)

        self.header_label = header_label

        #
        check_box = AnimatedCheckBox()

        check_box.checkStateChanged.connect(self.toggle_sub_item)

        self.check_box = check_box

        #
        header_layout = QtWidgets.QHBoxLayout()

        header_layout.setContentsMargins(11, 0, 11, 0)

        header_layout.addWidget(
            header_label, alignment=QtCore.Qt.AlignmentFlag.AlignLeft
        )
        header_layout.addWidget(check_box, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        #
        header_widget = QtWidgets.QWidget()

        palette = header_widget.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Window, palette.window().color().lighter()
        )
        header_widget.setPalette(palette)
        header_widget.setAutoFillBackground(True)

        header_widget.setLayout(header_layout)

        self.header_widget = header_widget

        #
        sub_layout = QtWidgets.QHBoxLayout()

        sub_layout.setContentsMargins(11, 11, 11, 11)

        self.sub_layout = sub_layout

        #
        sub_frame = QtWidgets.QFrame()

        sub_frame.setContentsMargins(0, 0, 0, 0)
        sub_frame.setObjectName("SubFrame")
        sub_frame.setStyleSheet(
            f"""
            #SubFrame {{ 
              border: {sub_frame.lineWidth()}px solid {border_colour.name()};
              border-left: none;
              border-right: none;
              border-bottom: none;
            }}
            """
        )

        sub_frame.setLayout(sub_layout)

        self.sub_frame = sub_frame

        #
        layout = QtWidgets.QVBoxLayout()

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(header_widget)
        layout.addWidget(sub_frame)

        self.setLayout(layout)

        #
        self.setObjectName("MainFrame")
        self.setStyleSheet(
            f"""
            #MainFrame {{
                border: {self.lineWidth()}px solid {border_colour.name()};
            }}
            """
        )

        #
        self._sub_item = None
        self.update_sub_item(sub_item)

    def update_sub_item(
        self, item: QtWidgets.QWidget | QtWidgets.QLayout | None
    ) -> None:
        current_item = self._sub_item
        self._sub_item = item

        if current_item is not None:
            index = self.sub_layout.indexOf(current_item)
            layout_item = self.sub_layout.itemAt(index)
            layout_item.widget().deleteLater()
        if item is not None:
            if isinstance(item, QtWidgets.QWidget):
                self.sub_layout.addWidget(item)
            elif isinstance(item, QtWidgets.QLayout):
                self.sub_layout.addLayout(item)

        self.toggle_sub_item(self.check_box.checkState())

    @QtCore.Slot(QtCore.Qt.CheckState)
    def toggle_sub_item(self, state: QtCore.Qt.CheckState) -> None:
        if self._sub_item is None:
            return

        if state == QtCore.Qt.CheckState.Checked:
            self.sub_frame.setVisible(True)
        else:
            self.sub_frame.setVisible(False)


class FlowLayout(QtWidgets.QLayout):
    """A flow layout that rearranges children in rows if they would overflow.

    Adapted from the official PySide documentation:
    https://doc.qt.io/qtforpython-6/examples/example_widgets_layouts_flowlayout.html
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)

        if parent is not None:
            self.setContentsMargins(QtCore.QMargins(0, 0, 0, 0))

        self._item_list = []

    def addItem(self, item: QtWidgets.QLayoutItem) -> None:
        self._item_list.append(item)

    def count(self) -> int:
        return len(self._item_list)

    def expandingDirections(self) -> QtCore.Qt.Orientation:
        return QtCore.Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def itemAt(self, index: int) -> Optional[QtWidgets.QLayoutItem]:
        try:
            item = self._item_list[index]
        except IndexError:
            item = None

        return item

    def minimumSize(self) -> QtCore.QSize:
        size = QtCore.QSize()

        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())

        size += QtCore.QSize(
            self.contentsMargins().top() + self.contentsMargins().bottom(),
            self.contentsMargins().left() + self.contentsMargins().right(),
        )

        return size

    def setGeometry(self, rect: QtCore.QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSize()

    def takeAt(self, index: int) -> Optional[QtWidgets.QLayoutItem]:
        try:
            item = self._item_list.pop(index)
        except IndexError:
            item = None

        return item

    def _do_layout(self, rect: QtCore.QRect, dry_run: bool = False) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._item_list:
            # Compute left edge of potential next item
            next_x = x + item.sizeHint().width() + spacing
            # Check right edge of current item can fit on current line
            if next_x - spacing > rect.right():
                # Go to next line
                x = rect.x()
                y = y + line_height + spacing
                next_x = x + item.sizeHint().width() + spacing
                line_height = 0

            if not dry_run:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()


class ResizablePixmapLabel(QtWidgets.QLabel):
    def __init__(
        self,
        file_path: str | Path,
        icon_mode: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        #
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        #
        self._pixmap = None
        self._aspect_ratio = 1

        pixmap = QtGui.QPixmap(file_path)

        if icon_mode:  # Make icon dynamic based on theme
            painter = QtGui.QPainter(pixmap)
            painter.setCompositionMode(
                QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
            )

            painter.setBrush(QtGui.QBrush(self.palette().text()))

            rect = pixmap.rect()
            painter.drawRect(rect)

            painter.end()

        self.setPixmap(pixmap)

    def setPixmap(self, pixmap: QtGui.QPixmap, overwrite: bool = False) -> None:
        if self._pixmap is None or overwrite:
            self._pixmap = pixmap
            if pixmap.height() > 0:
                self._aspect_ratio = pixmap.width() / pixmap.height()

        super().setPixmap(pixmap)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int | float) -> float:
        return width / self._aspect_ratio

    def resize_pixmap(self) -> None:
        width = self.height() * self._aspect_ratio
        height = self.width() / self._aspect_ratio
        if width > self.width():
            width = height * self._aspect_ratio
        elif height > self.height():
            height = width / self._aspect_ratio

        self.setPixmap(self._pixmap.scaled(int(width), int(height)))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        self.resize_pixmap()


class PixmapFlowLayout(QtWidgets.QLayout):
    """A layout that rearranges and resizes pixmaps in a grid if they would overflow.

    In comparison to a normal FlowLayout, this has a grid-like layout which leaves
    space for missing widgets. Additionally, it has helpers for replacing widgets or
    swapping two widgets based on indices.

    Adapted from the official PySide documentation:
    https://doc.qt.io/qtforpython-6/examples/example_widgets_layouts_flowlayout.html
    """

    def __init__(
        self,
        pixmap_minimum_width: int = 100,
        pixmap_maximum_width: int = 200,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)

        if pixmap_maximum_width / pixmap_minimum_width < 2:
            raise ValueError(
                "Thumbnail maximum width should be at least twice the minimum width."
            )
        self.pixmap_minimum_width = pixmap_minimum_width
        self.pixmap_maximum_width = pixmap_maximum_width

        self._item_dict = {}

    def addItem(self, item: QtWidgets.QLayoutItem) -> None:
        index = self.maximumIndex() + 1
        self._item_dict[index] = item

    def count(self) -> int:
        return len(self._item_dict)

    def expandingDirections(self) -> QtCore.Qt.Orientation:
        return QtCore.Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def indexOf(self, widget: QtWidgets.QWidget) -> Optional[int]:
        for index, item in self._item_dict.items():
            if widget is item.widget():
                return index

        return None

    def itemAt(self, index: int) -> Optional[QtWidgets.QLayoutItem]:
        try:
            item = self._item_dict[index]
        except KeyError:
            item = None

        return item

    def maximumIndex(self) -> int:
        index = 0
        if self._item_dict:
            index = max(self._item_dict.keys())

        return index

    def minimumSize(self) -> QtCore.QSize:
        return QtCore.QSize(self.pixmap_minimum_width, self.pixmap_minimum_width)

    def replaceAt(
        self,
        index: int,
        widget: QtWidgets.QWidget,
        allow_missing: bool = True,
        auto_delete: bool = True,
    ) -> None:
        current_item = self.takeAt(index)
        if current_item is None and not allow_missing:
            raise ValueError(
                f"Attempted to replace widget at index {index} when none was present."
            )
        elif current_item is not None and auto_delete:
            current_item.widget().deleteLater()

        self.addChildWidget(widget)
        new_item = QtWidgets.QWidgetItem(widget)
        self._item_dict[index] = new_item

    def setGeometry(self, rect: QtCore.QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSize()

    def swapItems(self, index1: int, index2: int) -> None:
        if index1 not in self._item_dict.keys():
            raise ValueError("Swap index 1 is not valid.")
        if index2 not in self._item_dict.keys():
            raise ValueError("Swap index 2 is not valid.")

        self._item_dict[index2], self._item_dict[index1] = (
            self._item_dict[index1],
            self._item_dict[index2],
        )

        self.update()

    def takeAt(self, index: int) -> Optional[QtWidgets.QLayoutItem]:
        try:
            item = self._item_dict.pop(index)
        except KeyError:
            item = None

        return item

    def _compute_column_count(
        self, width: int, column_count: Optional[int] = None
    ) -> int:
        if column_count is None:
            column_count = 1

        if column_count == 0:
            return 1

        if width / column_count <= self.pixmap_minimum_width:
            return self._compute_column_count(width, column_count - 1)
        elif width / column_count <= self.pixmap_maximum_width:
            return column_count
        else:
            return self._compute_column_count(width, column_count + 1)

    def _do_layout(self, rect: QtCore.QRect, dry_run: bool = False) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()

        column_count = min(
            self.maximumIndex() + 1, self._compute_column_count(rect.width())
        )
        column_count = max(1, column_count)
        row_count = math.ceil(self.maximumIndex() + 1 / column_count)
        item_width = round((rect.width() - (column_count - 1) * spacing) / column_count)

        current_row_index = 0
        for row_index, column_index in itertools.product(
            range(row_count), range(column_count)
        ):
            if current_row_index != row_index:
                y += line_height + spacing
                line_height = 0
                current_row_index = row_index

            item_index = row_index * column_count + column_index
            item = self.itemAt(item_index)
            if item is None:
                if item_index > self.maximumIndex():
                    break
                continue

            current_x = x + column_index * item_width + spacing * column_index

            if not dry_run:
                item_height = item_width
                if item.widget().hasHeightForWidth():
                    item_height = item.widget().heightForWidth(item_width)
                item.setGeometry(
                    QtCore.QRectF(
                        QtCore.QPointF(current_x, y),
                        QtCore.QSizeF(item_width, item_height),
                    ).toRect()
                )

            line_height = max(line_height, item.widget().height())

        return y + line_height - rect.y()


class CutOffLabel(QtWidgets.QLabel):
    def __init__(self, text: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(text, parent)

        self._text = text
        self.setToolTip(text)

    def setText(self, text: str, overwrite: bool = True) -> None:
        if overwrite:
            self._text = text

        super().setText(text)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        rect = self.contentsRect()
        if rect.width() < 1:
            return

        text = self._text

        if rect.width() > QtGui.QFontMetrics(self.font()).boundingRect(text).width():
            self.setText(text, overwrite=False)
            return

        text += "..."
        while not (
            rect.width() > QtGui.QFontMetrics(self.font()).boundingRect(text).width()
        ):
            text = text[:-4] + "..."

        self.setText(text, overwrite=False)


class BinaryAlphaPixmap(QtGui.QPixmap):
    def __init__(self, image_path: str | Path) -> None:
        """A pixmap that draws its binary content as foreground vs alpha.

        Args:
            image_path (str | Path): Path to the image to draw.
        """
        image = QtGui.QImage(str(image_path))

        pixmap = QtGui.QPixmap(image)

        painter = QtGui.QPainter(pixmap)

        painter.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_SourceAtop
        )
        painter.setBrush(
            QtGui.QBrush(
                lua_aware_shift(
                    QtWidgets.QApplication.instance().palette().window().color(), 100
                )
            )
        )

        painter.drawRect(pixmap.rect())

        painter.end()

        super().__init__(pixmap)


class HoverMixin:
    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        /,
        colour_change: int | QtGui.QColor = 20,
        *args,
        roles: Optional[list[QtGui.QPalette.ColorRole]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, *args, **kwargs)

        #
        self.colour_change = colour_change

        self._palette = self.palette()
        self._auto_fill_background = True

        self._roles = roles or [QtGui.QPalette.ColorRole.Window]

        #
        self.setAutoFillBackground(True)

    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)

        if event.type() == QtCore.QEvent.Type.EnabledChange:
            self.reset_temporary_changes()

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        """Handles enter events.

        On enter, the palette and the background fill are temporarily changed.

        Args:
            event (QtGui.QEnterEvent): Event to handle.
        """
        super().enterEvent(event)

        if not self.isEnabled():
            return

        palette = self.palette()

        if isinstance(self.colour_change, int):
            new_colour = lua_aware_shift(palette.button().color(), self.colour_change)
        else:
            new_colour = self.colour_change

        for role in self._roles:
            palette.setColor(role, new_colour)

        self.setPalette(palette, overwrite=False)

        self.setAutoFillBackground(True, overwrite=False)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        """Handles leave events.

        On leave, any temporary modifications of the palette and background fill are
        reverted.

        Args:
            event (QtCore.QEvent): Event to handle.
        """
        super().leaveEvent(event)

        self.reset_temporary_changes()

    def reset_temporary_changes(self) -> None:
        self.setAutoFillBackground(self._auto_fill_background)
        self.setPalette(self._palette)

    def setAutoFillBackground(self, enabled: bool, overwrite: bool = True) -> None:
        """Sets the autofill background property.

        Args:
            enabled (bool): Value to set the property to.
            overwrite (bool, optional):
                Whether the new value should overwrite the cache or be considered
                temporary.
        """
        if overwrite:
            self._auto_fill_background = enabled

        super().setAutoFillBackground(enabled)

    def setPalette(self, palette: QtGui.QPalette, overwrite: bool = True) -> None:
        """Sets the palette for this widget.

        Args:
            palette (QtGui.QPalette): Palette to set on this widget.
            overwrite (bool, optional):
                Whether the new value should overwrite the cache or be considered
                temporary.
        """
        if overwrite:
            self._palette = palette

        super().setPalette(palette)


class HoverButton(HoverMixin, QtWidgets.QPushButton):
    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        /,
        colour_change: int | QtGui.QColor = 20,
        flat: bool = True,
        icon_path: Optional[str | Path] = None,
        roles: Optional[list[QtGui.QPalette.ColorRole]] = None,
    ) -> None:
        """A button that reacts when hovered by changing its background color.

        Args:
            parent (QtWidgets.QWidget, optional): Parent of this widget.
            colour_change (int | QtGui.QColor, optional):
                Shift in the background colour on hover or the hover colour.
            flat (bool, optional): Whether the button should be flat.
        """
        roles = (
            roles
            if roles is not None
            else [
                QtGui.QPalette.ColorRole.Window,
                QtGui.QPalette.ColorRole.Button,
            ]
        )

        super().__init__(
            parent,
            colour_change,
            roles=roles,
        )

        #
        self.setFlat(flat)

        self.setAutoFillBackground(True)

        #
        if icon_path is not None:
            self.setIcon(DynamicThemeIcon(icon_path))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        icon_dimension = min(
            *self.contentsRect().size().toTuple()
        ) - self.style().pixelMetric(QtWidgets.QStyle.PixelMetric.PM_ButtonMargin)
        icon_size = QtCore.QSize(icon_dimension, icon_dimension)

        self.setIconSize(icon_size)


class CollapsibleWidgetArea(QtWidgets.QWidget):
    collapsed: QtCore.Signal = QtCore.Signal()
    expanded: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        expand_direction: Literal[
            "left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top"
        ] = "left_to_right",
        icon_dimension: int = 20,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        #
        self.expand_direction = expand_direction
        self.icon_dimension = icon_dimension

        self._icons = []
        self._widgets = []
        self._expanded_widget = None

        #
        icon_widget = QtWidgets.QWidget(self)
        icon_widget.setObjectName("IconWidget")

        frame_colour = lua_aware_shift(
            icon_widget.palette().window().color(), 10
        ).getRgb()

        if expand_direction == "left_to_right":
            icon_layout = QtWidgets.QVBoxLayout()
            icon_layout.setContentsMargins(0, 5, 3, 5)
            border = "right"
        elif expand_direction == "right_to_left":
            icon_layout = QtWidgets.QVBoxLayout()
            icon_layout.setContentsMargins(3, 5, 0, 5)
            border = "left"
        elif expand_direction == "top_to_bottom":
            icon_layout = QtWidgets.QHBoxLayout()
            icon_layout.setContentsMargins(5, 0, 5, 3)
            border = "bottom"
        elif expand_direction == "bottom_to_top":
            icon_layout = QtWidgets.QHBoxLayout()
            icon_layout.setContentsMargins(5, 3, 5, 0)
            border = "top"
        else:
            raise Exception("ASSERT NOT REACHED")

        stylesheet = (
            "#IconWidget {{ border-{}: 1px solid rgba({}, {}, {}, {}); }}".format(
                border, *frame_colour
            )
        )
        icon_widget.setStyleSheet(stylesheet)

        icon_layout.addStretch(1)

        icon_widget.setLayout(icon_layout)

        self.icon_layout = icon_layout

        #
        widget_layout = QtWidgets.QVBoxLayout()

        widget_layout.setContentsMargins(0, 0, 0, 0)

        self.widget_layout = widget_layout

        #
        if expand_direction in ["left_to_right", "right_to_left"]:
            layout = QtWidgets.QHBoxLayout()
        else:
            layout = QtWidgets.QVBoxLayout()

        layout.setContentsMargins(0, 0, 0, 0)

        if expand_direction in ["left_to_right", "top_to_bottom"]:
            layout.addWidget(icon_widget)
            layout.addLayout(widget_layout)
        else:
            layout.addLayout(widget_layout)
            layout.addWidget(icon_widget)

        self.setLayout(layout)

        #
        self.set_maximum_dimension()

    def add_widget(
        self, widget: QtWidgets.QWidget, icon_path: str | None = None
    ) -> None:
        widget.hide()

        self._widgets.append(widget)

        icon_button = HoverButton(
            icon_path=icon_path or RESOURCES_ROOT / "icons" / "add-categories-icon.png"
        )

        icon_button.setFixedSize(self.icon_dimension, self.icon_dimension)

        icon_button.clicked.connect(lambda: self.toggle_widget(widget))

        self._icons.append(icon_button)

        self.icon_layout.insertWidget(len(self._widgets) - 1, icon_button)

    def collapse(self, widget: QtWidgets.QWidget | None = None) -> None:
        if self._expanded_widget is not None:
            self.widget_layout.removeWidget(self._expanded_widget)

        self.set_maximum_dimension()

        if widget is not None:
            widget.hide()
        self._expanded_widget = None

        self.collapsed.emit()

    def expand(self, widget: QtWidgets.QWidget) -> None:
        self.reset_maximum_dimension()

        self.widget_layout.addWidget(widget)

        self._expanded_widget = widget
        widget.show()

        self.expanded.emit()

    def reset_maximum_dimension(self) -> None:
        if self.expand_direction in ["left_to_right", "right_to_left"]:
            self.setMaximumWidth(QWIDGETSIZE_MAX)
        else:
            self.setMaximumHeight(QWIDGETSIZE_MAX)

    def set_maximum_dimension(self) -> None:
        if self.expand_direction in ["left_to_right", "right_to_left"]:
            self.setMaximumWidth(
                self.icon_dimension
                + self.contentsMargins().left()
                + self.contentsMargins().right()
                + self.layout().contentsMargins().left()
                + self.layout().contentsMargins().right()
            )
        else:
            self.setMaximumHeight(
                self.icon_dimension
                + self.contentsMargins().top()
                + self.contentsMargins().bottom()
                + self.layout().contentsMargins().top()
                + self.layout().contentsMargins().bottom()
            )

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)

        if len(self._widgets):
            self.expand(self._widgets[0])

    @QtCore.Slot()
    def toggle_widget(self, widget: QtWidgets.QWidget) -> None:
        if self._expanded_widget is None:
            self.expand(widget)
        else:
            should_expand = widget != self._expanded_widget

            self.collapse(self._expanded_widget)
            if should_expand:
                self.expand(widget)


class VisibleSplitterHandle(QtWidgets.QSplitterHandle):
    """A splitter handle with a visible ellipsis icon."""

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Handles paint events.

        Args:
            event (QtGui.QPaintEvent): Event to handle.
        """
        if not self.isEnabled():
            return

        painter = QtGui.QPainter(self)

        icon_rect = QtCore.QRect(0, 0, 4 * self.rect().width(), 4 * self.rect().width())
        icon_rect.moveCenter(self.rect().center())

        if self.orientation() == QtCore.Qt.Orientation.Vertical:
            pixmap = BinaryAlphaPixmap(RESOURCES_ROOT / "icons" / "ellipsis-h-icon.png")
        else:
            pixmap = BinaryAlphaPixmap(RESOURCES_ROOT / "icons" / "ellipsis-v-icon.png")
        painter.drawPixmap(icon_rect, pixmap, pixmap.rect())

        painter.end()


class VisibleHandleSplitter(QtWidgets.QSplitter):
    """A splitter with handles showing up as ellipsis icons."""

    def createHandle(self) -> VisibleSplitterHandle:
        """Creates a visible handle.

        Returns:
            VisibleSplitterHandle: The newly created handle.
        """
        return VisibleSplitterHandle(self.orientation(), self)


class StackWidget(QtWidgets.QWidget):
    index_changed: QtCore.Signal = QtCore.Signal(int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self._widget_stack = []
        self._index = -1

        #
        layout = QtWidgets.QGridLayout()

        layout.setContentsMargins(0, 0, 0, 0)

        layout.setRowStretch(0, 1)
        layout.setColumnStretch(0, 1)

        self.setLayout(layout)

    def in_stack(self, widget: QtWidgets.QWidget) -> bool:
        return widget in self._widget_stack

    def has_next(self) -> bool:
        return self._index < len(self._widget_stack) - 1

    def has_previous(self) -> bool:
        return self._index > 0

    def next(self) -> None:
        if not self.has_next():
            return

        self._widget_stack[self._index].hide()
        self._index += 1
        self._widget_stack[self._index].show()

        self.index_changed.emit(self._index)

    def pop(self) -> None:
        self._pop()

        with suppress(IndexError):
            self._widget_stack[self._index].show()

    def previous(self) -> None:
        if not self.has_previous():
            return

        self._widget_stack[self._index].hide()
        self._index -= 1
        self._widget_stack[self._index].show()

    def put(self, widget: QtWidgets.QWidget) -> None:
        with suppress(IndexError):
            self._widget_stack[self._index].hide()

        self._clean_stack()

        self._widget_stack.append(widget)
        self._index += 1

        self.layout().addWidget(widget, 0, 0)

    def _clean_stack(self) -> None:
        while self._index < len(self._widget_stack) - 1:
            self._pop()

    def _pop(self) -> None:
        with suppress(IndexError):
            widget = self._widget_stack.pop()
            index = self.layout().indexOf(widget)
            item = self.layout().takeAt(index)
            if item.widget().parent() is None:
                item.widget().deleteLater()

        self._index = min(self._index, len(self._widget_stack) - 1)


class FileWidget(HoverMixin, QtWidgets.QWidget):
    clicked: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        /,
        colour_change: int | QtGui.QColor = 20,
        path: Path = None,
        is_folder: bool = False,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            colour_change,
            roles=[QtGui.QPalette.ColorRole.Window, QtGui.QPalette.ColorRole.Button],
            *args,
            **kwargs,
        )

        #
        self._clicked = False

        #
        icon_file = "folder-icon.png" if is_folder else "file-black-icon.png"

        icon = Icon(icon_path=RESOURCES_ROOT / "icons" / icon_file)

        self.icon = icon

        #
        label = CutOffLabel(str(path))

        self.label = label

        #
        layout = QtWidgets.QHBoxLayout()

        layout.addWidget(icon)
        layout.addWidget(label, stretch=1)

        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.setLayout(layout)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        super().mousePressEvent(event)

        self._clicked = True

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        super().mouseReleaseEvent(event)

        if self._clicked:
            self.clicked.emit()
            self._clicked = False


class DisplayableSortFilterProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)

    def filterAcceptsRow(self, source_row, source_parent):
        index = self.sourceModel().index(source_row, 0, source_parent)
        displayable = self.sourceModel().data(index, UserRole.IS_DISPLAYABLE)

        # Can potentially be `None` which should be `False`
        return displayable == True


class CheckAwareSortFilterProxyModel(QtCore.QSortFilterProxyModel):
    def lessThan(self, source_left, source_right):
        less_than = super().lessThan(source_left, source_right)

        left_checked = self.sourceModel().data(
            source_left, QtCore.Qt.ItemDataRole.CheckStateRole
        )
        right_checked = self.sourceModel().data(
            source_right, QtCore.Qt.ItemDataRole.CheckStateRole
        )

        left_checked = left_checked == True
        right_checked = right_checked == True

        if left_checked and not right_checked:
            less_than = True
        elif right_checked and not left_checked:
            less_than = False

        return less_than


class CustomDisplayRoleProxy(QtCore.QSortFilterProxyModel):
    _role: int = QtCore.Qt.ItemDataRole.DisplayRole

    def data(
        self,
        index: IndexType,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
        skip_override: bool = False,
    ) -> Any:
        if role == QtCore.Qt.ItemDataRole.DisplayRole and not skip_override:
            role = self._role

        return super().data(index, role)

    def override_display_role(self, role: int) -> None:
        self._role = role
