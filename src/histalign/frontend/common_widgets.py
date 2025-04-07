# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
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
from histalign.backend.io import (
    ALIGNMENT_FILE_NAME_PATTERN,
    load_alignment_settings,
    RESOURCES_ROOT,
)
from histalign.backend.workspace import HistologySlice
from histalign.frontend.dialogs import OpenProjectDialog
from histalign.frontend.events import (
    AboutToCollapseEvent,
    CollapsedEvent,
    ExpandedEvent,
    UserEventType,
)
from histalign.frontend.pyside_helpers import (
    connect_single_shot_slot,
    FakeQtABC,
    find_parent,
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
    def __init__(
        self,
        *,
        enabled: bool = True,
        icon_path: str | Path = "",
        shortcut: Optional[QtGui.QKeySequence] = None,
        tool_tip: str = "",
        status_tip: str = "",
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setEnabled(enabled)

        if icon_path:
            self.setIcon(DynamicThemeIcon(icon_path))

        if shortcut is not None:
            self.setShortcut(shortcut)
        self.setToolTip(tool_tip)
        self.setStatusTip(status_tip or tool_tip)

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

        super().mouseReleaseEvent(event)
        if self._drag_button != QtCore.Qt.MouseButton.LeftButton:
            self.setInteractive(True)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)

        # Notify of single clicks (no dragging)
        if not self._dragging and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self.mapToScene(event.pos()))

        self._dragging = False

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
    """A label that truncates its text automatically when resized.

    The original text is truncated character per character until it fits inside the
    available space.
    Note that because the truncation is indicated by "...", the first truncation removes
    the first four characters.

    Args:
        text (str): Text to set on the label.
        parent (Optional[QtWidgets.QWidget], optional): Parent of this widget.
    """

    _text: str

    def __init__(self, text: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.update_minimum_size()

        self._text = text
        self.setText(text)

    @property
    def full_text(self) -> str:
        return self._text

    def truncate_text_if_needed(self) -> None:
        """Truncates original text until it fits in the contents rect."""
        rect = self.contentsRect()
        if not rect.isValid():
            return

        # Truncate text one character at a time until it fits in the available space
        text = self._text
        font_metrics = self.fontMetrics()
        while rect.width() < font_metrics.horizontalAdvance(text) and text != "...":
            text = text[:-4] + "..."

        # Set tool tip when text has been cut off
        if text != self._text:
            self.setToolTip(self._text)
        self.setText(text, overwrite=False)

    def update_minimum_size(self) -> None:
        """Updates the minimum size of the widget to allow shrinking down to "..."."""
        self.setMinimumSize(
            self.fontMetrics().horizontalAdvance("..."), super().minimumHeight()
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        """Handles resize events.

        Args:
            event (QtGui.QResizeEvent): Event to handle.
        """
        super().resizeEvent(event)

        self.truncate_text_if_needed()

    def setFont(self, font: QtGui.QFont | str | Sequence[str]) -> None:
        """Sets the font on this label.

        Args:
            font (QtGui.QFont | str | Sequence[str]): Font to set on this label.
        """
        super().setFont(font)

        self.update_minimum_size()

    def setText(self, text: str, overwrite: bool = True) -> None:
        """Sets the text on this label.

        Args:
            text (str): Text to set on this label.
            overwrite (bool, optional):
                Whether the text provided should overwrite that base text. This is meant
                to be user internally when truncating.
        """
        if overwrite:
            self._text = text
            return self.truncate_text_if_needed()

        super().setText(text)

    def sizeHint(self) -> QtCore.QSize:
        """Returns the size hint for this widget.

        Returns:
            QtCore.QSize: The size hint for this widget.
        """
        return QtCore.QSize(
            self.fontMetrics().horizontalAdvance(self._text),
            super().sizeHint().height(),
        )


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


# noinspection PyPep8Naming
class HoverMixIn:
    """A mix-in for QWidgets to allows them to react to mouse hovers by changing colour.

    Args:
        shift (int | QtGui.QColor, optional):
            Shift of the background colour or new background colour.

    Attributes:
        shift (int | QtGui.QColor, optional):
            Shift of the background colour or new background colour.
        roles (QtGui.QPalette.ColorRole, optional):
            Roles to change the colour of. Most widgets are fine with the default
            (window) but buttons or line edits might need to change this.

        _palette (QtGui.QPalette): Cached palette.
        _auto_fill_background (bool): Cached auto-fill background property.
    """

    shift: int | QtGui.QColor

    _palette: QtGui.QPalette
    _auto_fill_background: bool

    def __init__(
        self: QtWidgets.QWidget,
        *args,
        shift: int | QtGui.QColor = 20,
        roles: list[QtGui.QPalette.ColorRole] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.shift = shift
        self.roles = roles or [QtGui.QPalette.ColorRole.Window]

        self._palette = self.palette()
        self._auto_fill_background = self.autoFillBackground()

    def changeEvent(self: QtWidgets.QWidget, event: QtCore.QEvent) -> None:
        """Handles change events.

        This provides a way to capture enable changes.

        Args:
            event (QtCore.QEvent): A change event.
        """
        super().changeEvent(event)

        # Reset changes when getting disabled
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            self.reset_temporary_changes()

    def enterEvent(self: QtWidgets.QWidget, event: QtCore.QEvent) -> None:
        """Handles enter events.

        This changes the palette when the user hovers over the widget.

        Args:
            event (QtCore.QEvent): An enter event.
        """
        super().enterEvent(event)

        if not self.isEnabled():
            return

        # Update the palette with a new background colour
        palette = self.palette()
        new_colour = self.shift

        for role in self.roles:
            if isinstance(self.shift, int):
                new_colour = lua_aware_shift(palette.color(role), self.shift)

            palette.setColor(role, new_colour)

        self.setPalette(palette, overwrite=False)
        self.setAutoFileBackground(True, overwrite=False)

    def leaveEvent(self: QtWidgets.QWidget, event: QtCore.QEvent) -> None:
        """Handles leave events.

        This resets the temporary changes when the user stops hovering the widget.

        Note that, on some platforms (e.g., WSL), if the widget is close to a window
        edge and the cursor is quickly moved outside said window, a leave event is not
        always received and the widget considers it is being hovered until the cursor
        returns to the window.

        Args:
            event (QtCore.QEvent): A leave event.
        """
        super().leaveEvent(event)

        if not self.isEnabled:
            return

        self.reset_temporary_changes()

    def setAutoFileBackground(
        self: QtWidgets.QWidget, enabled: bool, overwrite: bool = True
    ) -> None:
        """Sets the autofill background property.

        Args:
            enabled (bool): Value to set the property to.
            overwrite (bool, optional):
                Whether the new value should overwrite the cache or be considered
                temporary.
        """
        super().setAutoFillBackground(enabled)

        if overwrite:
            self._auto_fill_background = enabled

    def setPalette(
        self,
        palette: QtGui.QPalette | QtCore.Qt.GlobalColor | QtGui.QColor,
        overwrite: bool = True,
    ) -> None:
        """Sets the palette for this widget.

        Args:
            palette (QtGui.QPalette): Palette to set on this widget.
            overwrite (bool, optional):
                Whether the new value should overwrite the cache or be considered
                temporary.
        """
        super().setPalette(palette)

        if overwrite:
            self._palette = palette

    def reset_temporary_changes(self: QtWidgets.QWidget) -> None:
        """Resets temporary background and palette changes."""
        self.setPalette(self._palette)
        self.setAutoFileBackground(self._auto_fill_background)


class HoverButton(HoverMixIn, QtWidgets.QPushButton):
    def __init__(
        self,
        text: str = "",
        shift: int | QtGui.QColor = 20,
        icon_path: str | Path = "",
        parent: Optional[QtWidgets.QWidget] = None,
        *,
        flat: bool = True,
    ) -> None:
        super().__init__(
            text,
            shift=shift,
            roles=[QtGui.QPalette.ColorRole.Button],
            parent=parent,
            flat=flat,
        )

        if icon_path:
            self.setIcon(DynamicThemeIcon(icon_path))


class CollapsibleWidgetArea(QtWidgets.QWidget):
    def __init__(
        self,
        expand_direction: Literal[
            "left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top"
        ] = "left_to_right",
        icon_dimension: int = 20,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.expand_direction = expand_direction
        self.icon_dimension = icon_dimension

        self._expanded_widget: QtWidgets.QWidget | None = None

        self.icon_widget, self.icon_layout = self.build_icon_widget()

        widget_layout = QtWidgets.QVBoxLayout()
        widget_layout.setContentsMargins(0, 0, 0, 0)
        self.widget_layout = widget_layout

        self.setLayout(self.build_layout())

    def build_icon_widget(self) -> tuple[QtWidgets.QWidget, QtWidgets.QLayout]:
        icon_widget = QtWidgets.QWidget()
        expand_direction = self.expand_direction

        if expand_direction == "left_to_right":
            icon_layout = QtWidgets.QVBoxLayout()
            icon_layout.setContentsMargins(3, 5, 3, 5)
            icon_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
            border = "right"
        elif expand_direction == "right_to_left":
            icon_layout = QtWidgets.QVBoxLayout()
            icon_layout.setContentsMargins(3, 5, 3, 5)
            icon_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
            border = "left"
        elif expand_direction == "top_to_bottom":
            icon_layout = QtWidgets.QHBoxLayout()
            icon_layout.setContentsMargins(5, 3, 5, 3)
            icon_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
            border = "bottom"
        elif expand_direction == "bottom_to_top":
            icon_layout = QtWidgets.QHBoxLayout()
            icon_layout.setContentsMargins(5, 3, 5, 3)
            icon_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
            border = "top"
        else:
            raise ValueError("Invalid expand direction.")

        icon_widget.setObjectName("IconWidget")
        frame_colour = lua_aware_shift(icon_widget.palette().base().color())
        icon_widget.setStyleSheet(
            f"#IconWidget {{ border-{border}: 1px solid rgba{frame_colour.getRgb()}; }}"
        )

        if expand_direction in ["left_to_right", "right_to_left"]:
            icon_widget.setMaximumWidth(
                self.icon_dimension
                + icon_layout.contentsMargins().left()
                + icon_layout.contentsMargins().right()
            )
        else:
            icon_widget.setMaximumHeight(
                self.icon_dimension
                + icon_layout.contentsMargins().top()
                + icon_layout.contentsMargins().bottom()
            )

        icon_widget.setLayout(icon_layout)

        return icon_widget, icon_layout

    def build_layout(self) -> QtWidgets.QLayout:
        expand_direction = self.expand_direction

        if expand_direction in ["left_to_right", "right_to_left"]:
            layout = QtWidgets.QHBoxLayout()
        else:
            layout = QtWidgets.QVBoxLayout()

        if expand_direction in ["left_to_right", "top_to_bottom"]:
            layout.addWidget(self.icon_widget)
            layout.addLayout(self.widget_layout)
        else:
            layout.addLayout(self.widget_layout)
            layout.addWidget(self.icon_widget)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        return layout

    def add_widget(self, widget: QtWidgets.QWidget, icon_path: str | Path = "") -> None:
        icon_path = (
            Path(icon_path)
            if icon_path
            else RESOURCES_ROOT / "icons" / "three-horizontal-lines-icon.png"
        )

        icon_button = HoverButton(icon_path=icon_path)
        icon_button.setFixedSize(QtCore.QSize(self.icon_dimension, self.icon_dimension))
        icon_button.setIconSize(
            QtCore.QSize(self.icon_dimension - 4, self.icon_dimension - 4)
        )
        icon_button.clicked.connect(lambda: self.toggle_widget(widget))
        self.icon_layout.addWidget(icon_button)

        self.widget_layout.addWidget(widget)

        if self._expanded_widget is None:
            self._expanded_widget = widget
        else:
            widget.hide()

    def collapse(self, widget: QtWidgets.QWidget | None = None) -> None:
        QtWidgets.QApplication.instance().postEvent(self, AboutToCollapseEvent())
        if self._expanded_widget is not None:
            self.widget_layout.removeWidget(self._expanded_widget)

        self.set_maximum_dimension()

        if widget is not None:
            widget.hide()
        self._expanded_widget = None

        QtWidgets.QApplication.instance().postEvent(self, CollapsedEvent())

    def expand(self, widget: QtWidgets.QWidget) -> None:
        self.reset_maximum_dimension()

        self.widget_layout.addWidget(widget)

        self._expanded_widget = widget
        widget.show()

        QtWidgets.QApplication.instance().postEvent(self, ExpandedEvent())

    def reset_maximum_dimension(self) -> None:
        if self.expand_direction in ["left_to_right", "right_to_left"]:
            self.setMaximumWidth(QWIDGETSIZE_MAX)
        else:
            self.setMaximumHeight(QWIDGETSIZE_MAX)

    def set_maximum_dimension(self) -> None:
        if self.expand_direction in ["left_to_right", "right_to_left"]:
            self.setMaximumWidth(
                self.icon_dimension
                + self.icon_layout.contentsMargins().left()
                + self.icon_layout.contentsMargins().right()
            )
        else:
            self.setMaximumHeight(
                self.icon_dimension
                + self.icon_layout.contentsMargins().top()
                + self.icon_layout.contentsMargins().bottom()
            )

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
            source_left.siblingAtColumn(1), QtCore.Qt.ItemDataRole.CheckStateRole
        )
        right_checked = self.sourceModel().data(
            source_right.siblingAtColumn(1), QtCore.Qt.ItemDataRole.CheckStateRole
        )

        left_checked = left_checked == QtCore.Qt.CheckState.Checked
        right_checked = right_checked == QtCore.Qt.CheckState.Checked

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


class ThumbnailWidget(QtWidgets.QFrame):
    double_clicked: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        file_path: str | Path,
        text: str = "",
        index: int = -1,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        #
        self.file_path = file_path
        self.index = index

        self._active = False

        #
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)

        self.setObjectName("ThumbnailWidget")
        self._palette = self.palette()
        self.set_highlighted(False, False)

        #
        pixmap_label = ResizablePixmapLabel(file_path)

        self.pixmap_label = pixmap_label

        #
        text_label = CutOffLabel(text)

        text_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.text_label = text_label

        #
        layout = QtWidgets.QVBoxLayout()

        layout.setContentsMargins(0, 0, 0, layout.spacing())

        layout.addWidget(pixmap_label)
        layout.addWidget(text_label)

        self.setLayout(layout)

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        super().enterEvent(event)
        self.set_highlighted(True, self.hasFocus() or self._active)

    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:
        super().focusInEvent(event)
        self.set_highlighted(True, True)

    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.set_highlighted(False, self._active)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.clearFocus()

        super().keyPressEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        super().leaveEvent(event)
        self.set_highlighted(self.hasFocus(), self.hasFocus() or self._active)

    def set_active(self, active: bool) -> None:
        self._active = active

        # Avoid highlighting when activating programmatically
        highlight = self.rect().contains(
            self.mapFromGlobal(self.window().cursor().pos())
        )
        self.set_highlighted(highlight, active)

    def set_completed(self, completed: bool) -> None:
        if not completed:
            self.pixmap_label.setPixmap(QtGui.QPixmap(self.file_path), overwrite=True)
            self.pixmap_label.resize_pixmap()
            return

        pixmap = self.pixmap_label._pixmap
        if pixmap is None:
            return

        complete_icon_pixmap = QtGui.QPixmap()
        if not QtGui.QPixmapCache.find(
            "ThumbnailWidget_complete", complete_icon_pixmap
        ):
            complete_icon_pixmap = QtGui.QPixmap(
                RESOURCES_ROOT / "icons" / "check-mark-square-icon.png"
            )
            QtGui.QPixmapCache.insert("ThumbnailWidget_complete", complete_icon_pixmap)

        icon_dimension = pixmap.width() // 7
        complete_icon_pixmap = complete_icon_pixmap.scaled(
            icon_dimension, icon_dimension
        )

        icon_painter = QtGui.QPainter(complete_icon_pixmap)

        icon_painter.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
        )
        icon_painter.setBrush(QtGui.QBrush("#66CC00"))
        icon_painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        icon_painter.drawRect(complete_icon_pixmap.rect())

        icon_painter.end()

        main_painter = QtGui.QPainter(pixmap)

        main_painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        main_painter.drawPixmap(
            QtCore.QPoint(pixmap.width() - icon_dimension - 5, 5),
            complete_icon_pixmap,
        )

        main_painter.end()

        self.pixmap_label.setPixmap(pixmap)
        self.pixmap_label.resize_pixmap()

    def set_highlighted(self, highlighted: bool, selected: bool) -> None:
        colour = (
            self._palette.highlight().color()
            if highlighted
            else self._palette.window().color()
        )

        if selected:
            border_colour = "black"
            if self._active:
                border_colour = "blue"
        else:
            border_colour = "rgba(0, 0, 0, 0)"
        border = f"2px solid {border_colour};"

        self.setStyleSheet(
            f"""
            #ThumbnailWidget {{
                background: {colour.name()};
                border: {border};
            }}
            """
        )

    def setPalette(self, palette: QtGui.QPalette) -> None:
        super().setPalette(palette)
        self._palette = palette

    def setPixmap(self, pixmap: QtGui.QPixmap) -> None:
        self.pixmap_label.setPixmap(pixmap)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        super().mouseDoubleClickEvent(event)

        self.double_clicked.emit()


class ThumbnailsContainerWidget(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        layout = PixmapFlowLayout()

        self.setLayout(layout)

    def layout(self) -> PixmapFlowLayout:
        return self._layout

    def setLayout(self, layout: PixmapFlowLayout) -> None:
        if not isinstance(layout, PixmapFlowLayout):
            raise ValueError(
                "_ThumbnailsContainerWidget only accepts PixmapFlowLayout as a layout."
            )

        self._layout = layout
        super().setLayout(layout)


# noinspection PyPep8Naming
class DoubleClickMixIn:
    """A mix-in for any QWidget to make it double-clickable.

    Note that single clicking is therefore disabled by default.
    You should still connect to the `clicked` signal as that is what is emitted on
    double clicks.
    The inheriting widget does not need to have a clicked signal by default. If it does
    not, one is added to it.

    Signals:
        clicked (QtCore.Signal): Emitted when the widget is double clicked.
    """

    def __init__(self: QtWidgets.QWidget, *args, **kwargs) -> None:
        if not hasattr(type(self), "clicked"):
            type(self).clicked = QtCore.Signal()

        super().__init__(*args, **kwargs)

        self._double_clicking = False

        self.installEventFilter(self)

    def eventFilter(
        self: QtWidgets.QWidget, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        """Filters events on a watched object.

        Single clicks are ignored while double clicks apply the clicked logic.

        Args:
            watched (QtCore.QObject): A watched object.
            event (QtCore.QEvent): Event to filer

        Returns:
            bool: Whether the event was handled.
        """
        if event.type() == QtCore.QEvent.Type.MouseButtonPress:
            return True
        elif event.type() == QtCore.QEvent.Type.MouseButtonRelease:
            if self._double_clicking:
                self._double_clicking = False
                self.clicked.emit()
                return super().eventFilter(watched, event)
            return True
        elif event.type() == QtCore.QEvent.Type.MouseButtonDblClick:
            self.mousePressEvent(
                QtGui.QMouseEvent(
                    QtCore.QEvent.Type.MouseButtonPress,
                    event.localPos(),
                    event.globalPos(),
                    event.button(),
                    event.buttons(),
                    event.modifiers(),
                    event.device(),
                )
            )
            self._double_clicking = True
            return True

        return super().eventFilter(watched, event)


class DoubleClickButton(DoubleClickMixIn, QtWidgets.QPushButton):
    """A QPushButton that only allows double clicks."""


class DoubleClickHoverButton(DoubleClickMixIn, HoverButton):
    """A QPushButton that only allows double clicks and reacts to hovering."""


class FilePathLabel(CutOffLabel):
    def __init__(
        self, text: str = "", parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(text, parent)

        self.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.setMargin(4)
        font = self.font()
        font.setPixelSize(12)
        self.setFont(font)

        background_colour = self.palette().window().color()
        new_colour = lua_aware_shift(background_colour, 20)

        self.setObjectName("CustomLabel")
        self.setStyleSheet(
            f"#CustomLabel {{ background-color: rgba{new_colour.getRgb()}; }}"
        )
        self.setMinimumWidth(20)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )


class FileWidget(HoverMixIn, DoubleClickMixIn, QtWidgets.QWidget):
    def __init__(
        self,
        text: str = "",
        is_folder: bool = False,
        icon_path: str | Path = "",
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent=parent)

        if not icon_path:
            icon_file_name = "folder-icon.svg" if is_folder else "file-black-icon.svg"
            icon_path = RESOURCES_ROOT / "icons" / icon_file_name
        icon = Icon(icon_path)
        icon.setFixedSize(QtCore.QSize(30, 30))
        icon.setIconSize(QtCore.QSize(20, 20))

        label = CutOffLabel(text)
        self.label = label

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(icon)
        layout.addWidget(label)
        layout.setContentsMargins(5, 0, 5, 0)
        self.setLayout(layout)


class FileListWidget(QtWidgets.QWidget):
    def __init__(
        self,
        file_icon_path: str | Path = "",
        folder_icon_path: str | Path = "",
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.file_icon_path = file_icon_path
        self.folder_icon_path = folder_icon_path

        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    @property
    def path_list(self) -> list[str]:
        path_list = []
        for widget in self.children():
            if isinstance(widget, FileWidget):
                path_list.append(widget.label.full_text)

        return path_list

    def add_file(self, path: str | Path) -> FileWidget:
        widget = FileWidget(str(path), icon_path=self.file_icon_path)
        self.layout().addWidget(widget)

        return widget

    def add_folder(self, path: str | Path) -> FileWidget:
        widget = FileWidget(str(path), is_folder=True, icon_path=self.folder_icon_path)
        self.layout().addWidget(widget)

        return widget


class NavigationWidget(QtWidgets.QWidget):
    open_image_requested: QtCore.Signal = QtCore.Signal(Path)
    open_volume_requested: QtCore.Signal = QtCore.Signal(Path)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.project_root = None

        area = NavigationArea()
        area.open_image_requested.connect(self.open_image_requested.emit)
        area.open_volume_requested.connect(self.open_volume_requested.emit)
        self.area = area

        header = NavigationHeader()
        header.put_on_stack("Pick dimensionality")
        header.back_button.setEnabled(False)
        header.forward_button.setEnabled(False)
        header.back_button.clicked.connect(area.decrease_stack_index)
        header.forward_button.clicked.connect(area.increase_stack_index)
        area.stack_start_reached.connect(lambda: header.back_button.setEnabled(False))
        area.stack_start_reached.connect(lambda: header.forward_button.setEnabled(True))
        area.stack_end_reached.connect(lambda: header.back_button.setEnabled(True))
        area.stack_end_reached.connect(lambda: header.forward_button.setEnabled(False))
        header.back_button.clicked.connect(
            lambda: header.forward_button.setEnabled(True)
        )
        header.forward_button.clicked.connect(
            lambda: header.back_button.setEnabled(True)
        )
        area.folders_2d_opened.connect(lambda: header.put_on_stack("Slices"))
        area.files_3d_opened.connect(lambda: header.put_on_stack("Volumes"))
        area.folder_2d_opened.connect(lambda x: header.put_on_stack(str(x)))
        self.header = header

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(header)
        layout.addWidget(area)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.setLayout(layout)

    def parse_project(self, path: Path) -> None:
        self.project_root = path
        self.area.parse_project(path)


class NavigationHeader(QtWidgets.QWidget):
    back_button: QtWidgets.QPushButton
    forward_button: QtWidgets.QPushButton
    label: FilePathLabel

    _stack_index: int
    _title_stack: list[str]

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self._stack_index = -1
        self._title_stack = []

        back_button = HoverButton(flat=True)
        back_button.clicked.connect(self.decrease_stack_index)
        back_button.setFixedSize(40, 40)
        back_button.setIcon(
            QtGui.QIcon(str(RESOURCES_ROOT / "icons" / "thin-arrow-left-icon.png"))
        )
        back_button.setIconSize(QtCore.QSize(18, 18))
        self.back_button = back_button

        forward_button = HoverButton(flat=True)
        forward_button.clicked.connect(self.increase_stack_index)
        forward_button.setFixedSize(40, 40)
        forward_button.setIcon(
            QtGui.QIcon(str(RESOURCES_ROOT / "icons" / "thin-arrow-right-icon.png"))
        )
        forward_button.setIconSize(QtCore.QSize(18, 18))
        self.forward_button = forward_button

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(back_button)
        button_layout.addWidget(forward_button)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(0)

        label = FilePathLabel()
        self.label = label

        label_layout = QtWidgets.QHBoxLayout()
        label_layout.addWidget(label)
        label_layout.setContentsMargins(5, 5, 5, 5)

        layout = QtWidgets.QHBoxLayout()
        layout.addLayout(button_layout)
        layout.addLayout(label_layout, stretch=1)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.setFixedHeight(40)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.MinimumExpanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    def put_on_stack(self, title: str) -> None:
        self._stack_index += 1
        self._title_stack[self._stack_index :] = [title]

        self.update_title()

    def increase_stack_index(self) -> None:
        self._stack_index += 1
        if self._stack_index >= len(self._title_stack):
            self._stack_index -= 1
            return

        self.update_title()

    def decrease_stack_index(self) -> None:
        self._stack_index -= 1
        if self._stack_index < 0:
            self._stack_index += 1
            return

        self.update_title()

    def update_title(self) -> None:
        title = self._title_stack[self._stack_index]
        self.label.setText(title)

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(300, 40)


class NavigationArea(QtWidgets.QScrollArea):
    _widget_stack: list[QtWidgets.QWidget]

    folder_2d_opened: QtCore.Signal = QtCore.Signal(Path)
    folders_2d_opened: QtCore.Signal = QtCore.Signal()
    files_3d_opened: QtCore.Signal = QtCore.Signal()
    open_image_requested: QtCore.Signal = QtCore.Signal(Path)
    open_volume_requested: QtCore.Signal = QtCore.Signal(Path)
    stack_start_reached: QtCore.Signal = QtCore.Signal()
    stack_end_reached: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.project_root = None

        self._dimension_picker_widget = None
        self._folders_2d_widget = FileListWidget(parent=self)
        self._folders_2d_widget.hide()
        self._files_3d_widget = FileListWidget(
            file_icon_path=RESOURCES_ROOT / "icons" / "innovative-brain-icon.svg",
            parent=self,
        )
        self._files_3d_widget.hide()

        self._visible_widget = None
        self._stack_index = -1
        self._widget_stack = []

        folder_2d_button = DoubleClickHoverButton(
            icon_path=RESOURCES_ROOT / "icons" / "2d-folder-icon.svg"
        )
        folder_2d_button.clicked.connect(self.show_2d_folders)
        folder_2d_button.setFixedSize(QtCore.QSize(100, 100))
        folder_2d_button.setIconSize(QtCore.QSize(80, 80))

        folder_3d_button = DoubleClickHoverButton(
            icon_path=RESOURCES_ROOT / "icons" / "3d-folder-icon.svg"
        )
        folder_3d_button.clicked.connect(self.show_3d_files)
        folder_3d_button.setFixedSize(QtCore.QSize(100, 100))
        folder_3d_button.setIconSize(QtCore.QSize(80, 80))

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(folder_2d_button)
        button_layout.addWidget(folder_3d_button)
        button_layout.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft
        )

        widget = QtWidgets.QWidget(self)
        widget.setLayout(button_layout)
        self._dimension_picker_widget = widget
        self.put_on_stack(widget)

        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setAutoFillBackground(True)
        self.setPalette(lua_aware_shift(self.palette().window().color(), 10))
        self.setWidgetResizable(True)

    def parse_project(self, path: Path) -> None:
        self.project_root = path
        self.parse_2d_folders()
        self.parse_3d_files()

    def put_on_stack(self, widget: QtWidgets.QWidget) -> None:
        if self._visible_widget is not None:
            self._visible_widget.hide()

        self._stack_index += 1
        self._widget_stack[self._stack_index :] = [widget]

        self.takeWidget()
        self.setWidget(widget)
        widget.show()

        self.stack_end_reached.emit()

    def increase_stack_index(self) -> None:
        self._stack_index += 1
        if self._stack_index >= len(self._widget_stack):
            self._stack_index -= 1
            return
        elif self._stack_index == len(self._widget_stack) - 1:
            self.stack_end_reached.emit()

        self.update_visible_widget()

    def decrease_stack_index(self) -> None:
        self._stack_index -= 1
        if self._stack_index < 0:
            self._stack_index += 1
            return
        elif self._stack_index == 0:
            self.stack_start_reached.emit()

        self.update_visible_widget()

    def update_visible_widget(self) -> None:
        visible_widget = self._widget_stack[self._stack_index]
        if self._visible_widget is not None and visible_widget != self._visible_widget:
            self._visible_widget.hide()

        self.takeWidget()
        self.setWidget(visible_widget)
        self._visible_widget = visible_widget

    def parse_2d_folders(self) -> None:
        if self.project_root is None:
            return

        path_list = self._folders_2d_widget.path_list
        for path in self.project_root.iterdir():
            if re.fullmatch(HASHED_DIRECTORY_NAME_PATTERN, path.name) is None:
                continue

            try:
                with open(path / "metadata.json") as handle:
                    contents = json.load(handle)
            except FileNotFoundError:
                _module_logger.error(
                    f"Could not parse 'metadata.json' file "
                    f"for alignment folder '{path}'."
                )
                continue

            try:
                user_friendly_path = Path(contents["directory_path"])
            except KeyError:
                _module_logger.error(
                    f"Could not retrieve original directory name "
                    f"for alignment folder '{path}'."
                )
                continue

            # Only add new paths
            if str(user_friendly_path) in path_list:
                continue

            widget = self._folders_2d_widget.add_folder(user_friendly_path)
            widget.clicked.connect(lambda: "Clicked")
            widget.clicked.connect(
                lambda x=path, y=user_friendly_path: self.open_2d_folder(x, y)
            )

    def show_2d_folders(self) -> None:
        self.put_on_stack(self._folders_2d_widget)
        self.folders_2d_opened.emit()

    def open_2d_folder(
        self, path: Path, user_friendly_path: Path, should_panic: bool = False
    ) -> None:
        widget = ThumbnailsContainerWidget()

        try:
            with open(path / "metadata.json") as handle:
                contents = json.load(handle)
        except FileNotFoundError:
            _module_logger.error(
                f"Could not parse 'metadata.json' file "
                f"for alignment folder '{path}'."
            )
            return

        try:
            slice_order = list(map(Path, contents["slice_paths"]))
        except KeyError:
            if should_panic:
                _module_logger.error(
                    f"Could not retrieve slices order for alignment folder '{path}' "
                    f"after a second pass. Aborting."
                )
                return

            _module_logger.error(
                f"Could not retrieve slices order for alignment folder '{path}'. "
                f"Falling back to arbitrary (`Path.iterdir()`) order."
            )

            try:
                workspace = Workspace.load(str(self.project_root))
            except ValueError:
                _module_logger.error(
                    f"Could not load project file '{self.project_root}'. "
                    f"Aborting folder parsing."
                )
                return

            workspace.parse_image_directory(str(user_friendly_path))
            return self.open_2d_folder(path, original_directory, should_panic=True)

        aligned_paths = []
        path_index_map = {}
        for child_path in path.iterdir():
            if re.fullmatch(ALIGNMENT_FILE_NAME_PATTERN, child_path.name) is None:
                continue

            aligned_paths.append(child_path)

            alignment_settings = load_alignment_settings(child_path)
            histology_path = alignment_settings.histology_path

            path_index_map[child_path] = slice_order.index(histology_path)

        aligned_paths.sort(key=lambda x: path_index_map[x])
        for index, path in enumerate(aligned_paths):
            thumbnail = self._get_thumbnail(path)

            widget.layout().replaceAt(index, thumbnail)

        self.folder_2d_opened.emit(user_friendly_path)
        self.put_on_stack(widget)

    def parse_3d_files(self) -> None:
        if self.project_root is None:
            return

        volumes_file_path = self.project_root / "volumes.json"

        try:
            with open(volumes_file_path) as handle:
                contents = json.load(handle)
        except FileNotFoundError:
            _module_logger.debug("No volumes found.")
            return

        try:
            volume_paths = list(map(Path, contents["interpolated"]))
        except KeyError:
            _module_logger.error(
                f"Could not parse 'volumes.json' file "
                f"for project '{self.project_root}'."
            )
            return

        path_list = self._files_3d_widget.path_list
        for path in volume_paths:
            try:
                with open(path.parent.parent.parent / "metadata.json") as handle:
                    contents = json.load(handle)
            except FileNotFoundError:
                _module_logger.error(
                    f"Could not parse 'metadata.json' file for volume '{path}'."
                )
                continue

            try:
                user_friendly_path = Path(contents["directory_path"])
            except KeyError:
                _module_logger.error(
                    f"Could not retrieve original directory name "
                    f"for volume '{path}'."
                )
                continue

            # Only add new paths
            if str(user_friendly_path) in path_list:
                continue

            widget = self._files_3d_widget.add_file(user_friendly_path)
            widget.clicked.connect(lambda x=path: self.open_volume_requested.emit(x))

    def show_3d_files(self) -> None:
        self.put_on_stack(self._files_3d_widget)
        self.files_3d_opened.emit()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        self.widget().setMaximumWidth(self.viewport().width())

    def _get_thumbnail(self, alignment_path: Path) -> ThumbnailWidget:
        alignment_settings = load_alignment_settings(alignment_path)
        histology_path = alignment_settings.histology_path

        # TODO: Thread this in case the thumbnail cache was cleared since registration
        thumbnail_path = HistologySlice(str(histology_path)).generate_thumbnail(
            str(alignment_path.parent)
        )

        widget = ThumbnailWidget(thumbnail_path, histology_path.name)

        widget.double_clicked.connect(
            lambda: self.open_image_requested.emit(alignment_path)
        )

        return widget


class PreferentialSplitter(QtWidgets.QSplitter):
    """A splitter that applies all non-splitter size changes to the central widget.

    Note that this widget is meant to work with three widget, either laid out
    horizontally or vertically. The second widget added will be considered the central
    widget and will be the one to be resized when the window is resized or when a
    CollapsibleWidgetArea is collapsed/expanded.
    """

    _resize_index: int = 0

    def __init__(
        self,
        orientation: QtCore.Qt.Orientation = QtCore.Qt.Orientation.Horizontal,
        ratios: tuple[int, int, int] = (1, 3, 1),
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(orientation, parent)

        self._ratios = ratios

        self._widgets: Optional[list[QtWidgets.QWidget]] = None
        self._collapse_snapshot: list[int] = [-1, -1, -1]

    def compute_baseline_sizes(self) -> list[int]:
        """Computes starting sizes based on ratios provided at construction.

        Returns:
            list[int]: The baseline sizes weighed by the ratios.
        """
        if self.orientation() == QtCore.Qt.Orientation.Horizontal:
            dimension = self.width()
        else:
            dimension = self.height()
        dimension -= self.handleWidth() * (self.count() - 1)

        sizes = []
        total = sum(self._ratios)
        for ratio in self._ratios:
            sizes.append(round(ratio / total * dimension))

        return sizes

    def addWidget(self, _: Never) -> None:
        """N/A

        Do not use this function. Instead, use `add_widgets()` to add all three widgets
        at the same time.
        """
        raise NotImplementedError("Use `add_widgets` instead.")

    def add_widgets(self, widgets: list[QtWidgets.QWidget]) -> None:
        """Adds widgets to this splitter.

        Args:
            widgets (list[QtWidgets.QWidget):
                The three widgets to add to this splitter. The first widget should be
                the left/top widget, the second the central one, and the third the
                right/bottom one.

        Raises:
            ValueError: When not providing exactly 3 widgets.
        """
        if len(widgets) != 3:
            raise ValueError(
                f"{self.__class__.__qualname__} only supports exactly 3 widgets."
            )

        for widget in widgets:
            super().addWidget(widget)
            widget.installEventFilter(self)

        # Set stretch factors so super implementation will only resize central widget
        # when window is resized.
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)
        self.setStretchFactor(2, 0)

        self._widgets = widgets

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        """Handles resize events.

        The first one or two resize events are used to set the baseline sizes given the
        ratios passed at construction.

        Args:
            event (QtGui.QResizeEvent): Event to handle.
        """
        super().resizeEvent(event)

        # If outside of a QTabWidget, set baseline sizes on first resize only. If inside
        # a QTabWidget, set baseline sizes second resize as well. Otherwise, the sizes
        # are set on an incorrect total size. The actual size o the widget is either
        # known on the first resize when the widget is outside of a QTabWidget, or on
        # the second when inside of one.
        if self._resize_index == 0 or (
            self._resize_index == 1
            and isinstance(
                find_parent(self, QtWidgets.QTabWidget), QtWidgets.QTabWidget
            )
        ):
            self._resize_index += 1
            self.setSizes(self.compute_baseline_sizes())

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Filters events on a watched object.

        This filter is meant to be automatically installed on split widgets and will not
        have any effect on other objects or widgets.

        Args:
            watched (QtCore.QObject): A watched object.
            event (QtCore.QEvent): Event to filter.

        Returns:
            bool: Whether the event was handled.
        """
        if (
            self._widgets is None
            or not isinstance(watched, QtWidgets.QWidget)
            or watched not in self._widgets
        ):
            return super().eventFilter(watched, event)

        if event.type() == UserEventType.AboutToCollapse.value:
            # Snapshot sizes before collapsing since widgets are not resized in time
            # when expanding and we need their target size to restore it.
            index = self._widgets.index(watched)
            self._collapse_snapshot[index] = self.sizes()[index]
        elif event.type() == UserEventType.Collapsed.value:
            # self.sizes() still has the old values before collapsing so we can adjust
            # them to only grow the central widget.
            index = self._widgets.index(watched)

            # Compute widget size decrease. We can trust its size as it has already been
            # resized.
            current_size = self.sizes()[index]
            if self.orientation() == QtCore.Qt.Orientation.Horizontal:
                size_decrease = current_size - watched.width()
            else:
                size_decrease = current_size - watched.height()

            # Compute correct sizes
            sizes = self.sizes()
            sizes[1] += size_decrease  # Add newly available space to central widget
            sizes[index] -= size_decrease  # Remove space from collapsed widget

            self.setSizes(sizes)
        elif event.type() == UserEventType.Expanded.value:
            # self.sizes() still has the old values before expanding so we can adjust
            # them to only shrink the central widget.
            index = self._widgets.index(watched)

            # Retrieve snapshot of widget size before expansion.
            # We can't trust widget.size() because it has not been resized to
            # accommodate expanded widget.
            target_size = self._collapse_snapshot[index]
            current_size = self.sizes()[index]

            # Compute widget size increase
            size_increase = target_size - current_size

            # Compute correct sizes
            sizes = self.sizes()
            sizes[1] -= size_increase  # Remove expanded space from central widget
            sizes[index] += size_increase  # Restore space to target size

            self.setSizes(sizes)

        return super().eventFilter(watched, event)
