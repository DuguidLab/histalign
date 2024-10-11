# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from abc import abstractmethod
import json
import logging
from pathlib import Path
import re
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.ccf.model_view import StructureModel, StructureNode
from histalign.frontend.dialogs import NewProjectDialog, OpenProjectDialog
from histalign.frontend.pyside_helpers import FakeQtABC, connect_single_shot_slot

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


class TreeView(QtWidgets.QTreeView):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setHeaderHidden(True)
        self.setStyleSheet(
            f"""
            QTreeView {{
                padding-top: 15px;
                padding-bottom: 15px;
                background-color: {self.palette().color(QtGui.QPalette.Base).name()};
            }}
            """
        )


class StructureTagFrame(QtWidgets.QFrame):
    removal_requested: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        text: str,
        font_pixel_size: int = 12,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        button = QtWidgets.QPushButton("X")
        button.setFixedSize(font_pixel_size, font_pixel_size)
        font = QtGui.QFont()
        font.setPixelSize(font_pixel_size - 3)
        button.setFont(font)
        button.setFlat(True)
        button.clicked.connect(self.removal_requested)

        label = QtWidgets.QLabel(text)
        font = QtGui.QFont()
        font.setPixelSize(font_pixel_size)
        label.setFont(font)
        label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)

        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)

        layout.addWidget(button)
        layout.addWidget(label)

        self.setLayout(layout)

        self.removal_requested.connect(self.deleteLater)

        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)


class StructureFinderWidget(QtWidgets.QWidget):
    structure_model: StructureModel
    line_edit: QtWidgets.QLineEdit
    tree_view: TreeView

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        structure_model = StructureModel()
        self.structure_model = structure_model

        #
        line_edit = QtWidgets.QLineEdit(self)
        line_edit.returnPressed.connect(lambda: self.select_structure(line_edit.text()))
        self.line_edit = line_edit

        #
        tree_view = TreeView(self)
        tree_view.setModel(structure_model)
        tree_view.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        tree_view.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tree_view = tree_view

        #
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(line_edit)
        layout.addWidget(tree_view)

        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

        #
        self.installEventFilter(self)

    def select_structure(self, text: str) -> None:
        # Skip looking up the whole tree with searches smaller than 3 characters
        if len(text) < 3:
            return

        matching_model_indices = []
        selected_index = -2
        for node in self.structure_model.iterate_nodes():
            if (
                node.text().lower().startswith(text.lower())
                or text.lower() in node.text().lower()
            ):
                model_index = self.structure_model.indexFromItem(node)
                matching_model_indices.append(model_index)

                if self.tree_view.selectionModel().isSelected(model_index):
                    selected_index = len(matching_model_indices) - 1

                # Break early if current model_index is the one we want. This is the
                # case when the previous model_index was selected.
                if len(matching_model_indices) - 2 == selected_index:
                    break

        if selected_index == -2:
            model_index = matching_model_indices[0]
        else:
            model_index = matching_model_indices[
                (selected_index + 1) % len(matching_model_indices)
            ]

        self.tree_view.scrollTo(model_index)
        self.tree_view.selectionModel().select(
            model_index,
            QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect,
        )

    def eventFilter(self, watched: QtWidgets.QWidget, event: QtCore.QEvent) -> bool:
        match event.type():
            case QtCore.QEvent.Type.KeyPress:
                if event.key() == QtCore.Qt.Key.Key_Escape:
                    self.tree_view.selectionModel().clearCurrentIndex()
                    self.tree_view.selectionModel().clearSelection()
                    return True
            case _:
                pass

        return super().eventFilter(watched, event)


class SelectedStructuresWidget(QtWidgets.QWidget):
    structure_tags_mapping: dict[str, StructureTagFrame]

    add_tag_button: QtWidgets.QPushButton
    structure_finder_widget: StructureFinderWidget
    scroll_area: QtWidgets.QScrollArea
    tag_layout: QtWidgets.QHBoxLayout

    structure_added: QtCore.Signal = QtCore.Signal(str)
    structure_removed: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(
            f"{self.__module__}.{self.__class__.__qualname__}"
        )

        self.structure_tags_mapping = {}

        self.structure_finder_widget = StructureFinderWidget()
        self.structure_finder_widget.structure_model.itemChanged.connect(
            self.handle_structure_change
        )
        self.structure_finder_widget.layout().setSpacing(0)
        self.structure_finder_widget.hide()

        layout = QtWidgets.QHBoxLayout()
        layout.setAlignment(QtCore.Qt.AlignLeft)

        self.add_tag_button = QtWidgets.QPushButton("+")

        self.add_tag_button.clicked.connect(self.show_popup_structure_finder_widget)

        self.structure_finder_widget.setFocusProxy(self.add_tag_button)

        scroll_layout = QtWidgets.QHBoxLayout()
        scroll_layout.setAlignment(QtCore.Qt.AlignLeft)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        scroll_area_widget = QtWidgets.QWidget()
        self.tag_layout = QtWidgets.QHBoxLayout()
        self.tag_layout.setAlignment(QtCore.Qt.AlignLeft)
        scroll_area_widget.setLayout(self.tag_layout)
        self.scroll_area.setWidget(scroll_area_widget)
        self.scroll_area.setFixedHeight(self.tag_layout.sizeHint().height() + 10)
        self.tag_layout.setContentsMargins(5, 0, 5, 0)

        scroll_layout.addWidget(self.scroll_area)

        layout.addLayout(scroll_layout, 1)
        layout.addWidget(self.add_tag_button)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.setLayout(layout)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed
        )

        self.add_tag_button.setFixedSize(
            scroll_layout.sizeHint().height(), scroll_layout.sizeHint().height()
        )

    def add_structure(self, node: StructureNode) -> None:
        structure_tag_frame = StructureTagFrame(node.name)
        structure_tag_frame.removal_requested.connect(node.uncheck)

        self.structure_tags_mapping[node.name] = structure_tag_frame

        self.tag_layout.addWidget(structure_tag_frame)

        self.structure_added.emit(node.name)

    def remove_structure(self, structure_name: str) -> None:
        try:
            self.structure_tags_mapping.pop(structure_name, None).deleteLater()
            self.structure_removed.emit(structure_name)
        except AttributeError:
            self.logger.error("Tried removing a structure tag that was not present.")

    @QtCore.Slot()
    def handle_structure_change(self, node: StructureNode) -> None:
        match node.checkState():
            case QtCore.Qt.CheckState.Unchecked:
                self.remove_structure(node.name)
            case QtCore.Qt.CheckState.Checked:
                self.add_structure(node)
            case _:
                raise NotImplementedError

    @QtCore.Slot()
    def show_popup_structure_finder_widget(self) -> None:
        if self.structure_finder_widget.isVisible():
            self.structure_finder_widget.hide()
            return

        # Assign own parent to popup, this way it can be shown over other widgets.
        # This relies on self being child of main window.
        if self.structure_finder_widget.parent() is None:
            self.structure_finder_widget.setParent(self.parent())

            position = self.mapToParent(self.scroll_area.geometry().bottomLeft())

            self.structure_finder_widget.setGeometry(
                position.x(),
                position.y(),
                self.width(),
                500,
            )

        self.structure_finder_widget.show()
        self.structure_finder_widget.line_edit.setFocus()


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
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.setLineWidth(2)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Maximum
        )


class HorizontalSeparator(QtWidgets.QFrame):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        self.setLineWidth(2)
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
        self.statusBar()

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

    def __init__(self, icon_path: str) -> None:
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
