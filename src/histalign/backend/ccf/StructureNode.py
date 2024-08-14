# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from typing import Any

from PySide6 import QtCore, QtGui


@dataclass
class StructureNode(QtGui.QStandardItem):
    acronym: str
    rgb_triplet: list[int]
    graph_id: int
    graph_order: int
    id: int
    name: str
    structure_id_path: list[int]
    structure_set_ids: list[int]

    def __post_init__(self) -> None:
        super().__init__()

    def data(
        self, role: QtCore.Qt.ItemDataRole = QtCore.Qt.ItemDataRole.DisplayRole
    ) -> Any:
        match role:
            case QtCore.Qt.ItemDataRole.DisplayRole:
                return self.name
            case _:
                return super().data(role)

    def uncheck(self) -> None:
        if self.checkState() == QtCore.Qt.CheckState.Checked:
            self.setCheckState(QtCore.Qt.CheckState.Unchecked)
