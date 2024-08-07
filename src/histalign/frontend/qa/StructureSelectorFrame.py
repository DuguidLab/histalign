# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from functools import partial
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.ccf.allen_downloads import get_structure_names_list
from histalign.frontend.qa.dialogs import StructureNameInputDialog
from histalign.frontend.qa.StructureTagFrame import StructureTagFrame


class StructureSelectorFrame(QtWidgets.QFrame):
    structure_names_list: list[str]

    tag_layout: QtWidgets.QHBoxLayout

    structure_added: QtCore.Signal = QtCore.Signal(str)
    structure_removed: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.structure_names_list = get_structure_names_list()

        layout = QtWidgets.QHBoxLayout()
        layout.setAlignment(QtCore.Qt.AlignLeft)

        add_tag_button = QtWidgets.QPushButton("+")
        add_tag_button.setFixedSize(22, 22)

        add_tag_button.clicked.connect(self.show_structure_name_input_dialog)

        scroll_layout = QtWidgets.QHBoxLayout()
        scroll_layout.setAlignment(QtCore.Qt.AlignLeft)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area_widget = QtWidgets.QWidget()
        self.tag_layout = QtWidgets.QHBoxLayout()
        self.tag_layout.setAlignment(QtCore.Qt.AlignLeft)
        scroll_area_widget.setLayout(self.tag_layout)
        scroll_area.setWidget(scroll_area_widget)
        scroll_area.setFixedHeight(self.tag_layout.sizeHint().height() + 10)
        self.tag_layout.setContentsMargins(5, 0, 5, 0)

        scroll_layout.addWidget(scroll_area)

        layout.addWidget(add_tag_button, 1)
        layout.addLayout(scroll_layout, 100)
        layout.setContentsMargins(3, 7, 3, 7)

        self.setLayout(layout)

        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.setFixedHeight(layout.sizeHint().height())

    @QtCore.Slot()
    def add_structure(self, name: str) -> None:
        structure_tag_frame = StructureTagFrame(name)
        structure_tag_frame.removal_requested.connect(
            lambda: self.restore_structure_to_name_list(name)
        )
        structure_tag_frame.removal_requested.connect(
            lambda: self.structure_removed.emit(name)
        )

        self.tag_layout.addWidget(structure_tag_frame)
        self.structure_names_list.remove(name)

        self.structure_added.emit(name)

    @QtCore.Slot()
    def show_structure_name_input_dialog(self) -> None:
        dialog = StructureNameInputDialog(self.structure_names_list, self)
        dialog.submitted.connect(self.add_structure)

        dialog.open()

    @QtCore.Slot()
    def restore_structure_to_name_list(self, structure_name: str) -> None:
        self.structure_names_list.append(structure_name)
