# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.ccf.StructureHierarchyModel import StructureHierarchyModel
from histalign.backend.ccf.StructureNode import StructureNode
from histalign.frontend.qa.PopUpTreeView import PopUpTreeView
from histalign.frontend.qa.StructureTagFrame import StructureTagFrame


class AddTagButton(QtWidgets.QPushButton):
    focus_lost: QtCore.Signal = QtCore.Signal()

    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        self.focus_lost.emit()


class StructureSelectorFrame(QtWidgets.QFrame):
    structure_tags_mapping: dict[str, StructureTagFrame]

    add_tag_button: QtWidgets.QPushButton
    structures_tree_view: PopUpTreeView
    scroll_area: QtWidgets.QScrollArea
    tag_layout: QtWidgets.QHBoxLayout

    structure_added: QtCore.Signal = QtCore.Signal(str)
    structure_removed: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)

        self.structure_tags_mapping = {}

        self.structures_tree_view = PopUpTreeView()
        self.structures_tree_view.setModel(StructureHierarchyModel())
        self.structures_tree_view.model().itemChanged.connect(
            self.handle_structure_change
        )
        self.structures_tree_view.hide()

        layout = QtWidgets.QHBoxLayout()
        layout.setAlignment(QtCore.Qt.AlignLeft)

        self.add_tag_button = AddTagButton("+")
        self.add_tag_button.setFixedSize(22, 22)

        self.add_tag_button.clicked.connect(self.show_popup_structures_tree_view)
        self.add_tag_button.focus_lost.connect(self.structures_tree_view.hide)

        self.structures_tree_view.setFocusProxy(self.add_tag_button)

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

        layout.addWidget(self.add_tag_button, 1)
        layout.addLayout(scroll_layout, 100)
        layout.setContentsMargins(3, 7, 3, 7)

        self.setLayout(layout)

        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.setFixedHeight(layout.sizeHint().height())

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
    def show_popup_structures_tree_view(self) -> None:
        if self.structures_tree_view.isVisible():
            self.structures_tree_view.hide()
            return

        # Assign own parent to popup, this way it can be shown over other widgets.
        # This relies on self being child of main window.
        if self.structures_tree_view.parent() is None:
            self.structures_tree_view.setParent(self.parent())

            # position = self.mapToParent(self.add_tag_button.geometry().bottomLeft())
            position = self.mapToParent(self.scroll_area.geometry().bottomLeft())

            self.structures_tree_view.setGeometry(
                position.x(),
                position.y(),
                self.scroll_area.width(),  # 400,
                500,
            )

        self.structures_tree_view.show()
