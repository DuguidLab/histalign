# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import sys
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.ccf.StructureHierarchyModel import StructureHierarchyModel
from histalign.frontend.qa.TreeView import TreeView


class StructureFinderWidget(QtWidgets.QWidget):
    structure_model: StructureHierarchyModel
    line_edit: QtWidgets.QLineEdit
    tree_view: TreeView

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        structure_model = StructureHierarchyModel()
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
