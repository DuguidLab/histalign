# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import json
from typing import Any, Optional

from PySide6 import QtCore, QtGui

from histalign.backend.ccf.StructureNode import StructureNode
from histalign.backend.ccf.allen_downloads import get_structures_hierarchy_path


class StructureHierarchyModel(QtGui.QStandardItemModel):
    def __init__(
        self,
        structures_hierarchy_path: Optional[str] = None,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        structures_hierarchy_path = (
            structures_hierarchy_path or get_structures_hierarchy_path()
        )

        self.build_tree(structures_hierarchy_path)

    def data(
        self,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        role: QtCore.Qt.ItemDataRole = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        match role:
            case _:
                return super().data(index, role)

    def setData(
        self,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        value: Any,
        role: QtCore.Qt.ItemDataRole = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> bool:
        match role:
            case QtCore.Qt.ItemDataRole.CheckStateRole:
                if value == QtCore.Qt.CheckState.Checked.value:
                    # Replicate the Allen 3D viewer behaviour of unchecking structures
                    # that are children of structure that was just checked.
                    self.propagate_uncheck(self.itemFromIndex(index), skip_root=True)

                return super().setData(index, value, role)
            case _:
                return super().setData(index, value, role)

    def propagate_uncheck(
        self, root: QtGui.QStandardItem, skip_root: bool = False
    ) -> None:
        if root.checkState() == QtCore.Qt.CheckState.Checked and not skip_root:
            root.setCheckState(QtCore.Qt.CheckState.Unchecked)
        for row in range(root.rowCount()):
            self.propagate_uncheck(root.child(row, 0))

    def build_tree(self, structures_hierarchy_path: str) -> None:
        """Builds a `StructureNode` tree from a hierarchy file.

        This method is overly careful about the state of the hierarchy. It does not
        assume the hierarchy can be completely parsed in a single pass and makes sure
        there aren't any orphaned nodes (i.e., nodes without a parent). These checks
        are most likely unnecessary but I'm not aware of any guarantees the Allen SDK
        makes about the hierarchy and these checks don't impact the performance of the
        tree building.

        Args:
            structures_hierarchy_path (str): Path to the hierarchy file on disk. This
                                             should be a JSON file as obtained from the
                                             Allen SDK.
        """

        def find_node(nodes: list[StructureNode], id_: int) -> int:
            for index, node in enumerate(nodes):
                if node.id == id_:
                    return index

            raise ValueError(f"Cannot find node with id {id_}")

        nodes_to_insert = self.parse_hierarchy(structures_hierarchy_path)
        nodes_inserted = []

        while nodes_to_insert:
            processed_a_node = False
            i = 0
            while i < len(nodes_to_insert):
                current_node = nodes_to_insert[i]
                if current_node.name == "root":
                    self.invisibleRootItem().appendRow(current_node)
                    nodes_inserted.append(nodes_to_insert.pop(i))
                    processed_a_node = True
                    continue

                parent_id = current_node.structure_id_path[-2]

                try:
                    items = self.findItems(
                        nodes_inserted[find_node(nodes_inserted, parent_id)].name,
                        QtCore.Qt.MatchFlag.MatchRecursive,
                    )
                except ValueError:
                    i += 1
                    continue

                if not items:
                    # Could not find its parent
                    i += 1
                    continue
                elif len(items) > 1:
                    raise ValueError(
                        f"Tried to add node ({current_node.name} - {current_node.id}) "
                        f"already present in the model."
                    )

                items[0].appendRow(current_node)
                nodes_inserted.append(nodes_to_insert.pop(i))
                processed_a_node = True

            if not processed_a_node:
                raise ValueError(f"Found orphaned nodes: \n{nodes_to_insert}")

    @staticmethod
    def parse_hierarchy(structures_hierarchy_path: str) -> list[StructureNode]:
        with open(structures_hierarchy_path) as handle:
            contents = json.load(handle)

        nodes = []
        for node_dict in contents:
            node = StructureNode(**node_dict)

            node.setEditable(False)
            node.setCheckable(True)
            node.setCheckState(QtCore.Qt.CheckState.Unchecked)

            nodes.append(node)

        return nodes
