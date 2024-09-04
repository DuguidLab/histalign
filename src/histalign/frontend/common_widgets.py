# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import json
import logging
from pathlib import Path
import re
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.ccf.model_view import StructureModel, StructureNode

HASHED_DIRECTORY_NAME_PATTERN = re.compile(r"[0-9a-f]{10}")


class ProjectDirectoriesComboBox(QtWidgets.QComboBox):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

    def parse_project(self, project_path: str) -> None:
        self.clear()

        project_directory = Path(project_path).parent
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

        self.logger = logging.getLogger(__name__)

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
