# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
import json
import logging
import os
from typing import Any, Iterator, Optional

from PySide6 import QtCore, QtGui

from histalign.backend.ccf.paths import get_structures_hierarchy_path
from histalign.backend.io import DATA_ROOT

_module_logger = logging.getLogger(__name__)


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

    def toJson(self) -> dict:
        return {
            "acronym": self.acronym,
            "rgb_triplet": self.rgb_triplet,
            "graph_id": self.graph_id,
            "graph_order": self.graph_order,
            "id": self.id,
            "name": self.name,
            "structure_id_path": self.structure_id_path,
            "structure_set_ids": self.structure_set_ids,
        }


class StructureModel(QtGui.QStandardItemModel):
    def __init__(
        self,
        structures_hierarchy_path: Optional[str] = None,
        root_text: str = "Basic cell groups and regions",
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        structures_hierarchy_path = (
            structures_hierarchy_path or get_structures_hierarchy_path()
        )

        self.build_tree(structures_hierarchy_path, root_text)

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

    def build_tree(self, structures_hierarchy_path: str, root_text: str) -> None:
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
            root_text (str): Text of the root node. If a node with that text exists, it
                             will be used as the root of the model (note the root will
                             not be a visible node, instead its children will be
                             re-parented to the invisibleRootItem. If left empty, the
                             root will be the invisibleRootItem and all nodes will be
                             visible.
        """

        cache_path = DATA_ROOT / "parsed_structures.json"
        if cache_path.exists():
            _module_logger.info("Found cached structure model.")
            with open(cache_path) as handle:
                data = json.load(handle)

            if data[0] == list(os.stat(structures_hierarchy_path)):
                hierarchy = data[1]
                deserialise_hierarchy(hierarchy, self.invisibleRootItem())
                if root_text:
                    self.zoom_on(root_text)
                return
            else:
                _module_logger.info(
                    "Invalidating cache as cached stat is different from original file."
                )

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

        with open(cache_path, "w") as handle:
            _module_logger.info("Caching parsed structure model.")

            data = [
                os.stat(structures_hierarchy_path),
                serialise_hierarchy(self.invisibleRootItem()),
            ]

            json.dump(data, handle)

        if root_text:
            self.zoom_on(root_text)

    def zoom_on(self, text: str, zoom_in: bool = True) -> None:
        for node in self.iterate_nodes():
            for i in range(node.rowCount()):
                if node.child(i).text() == text:
                    child = node.takeChild(i)
                    self.clear()
                    self.invisibleRootItem().appendRow(child)

                    if zoom_in:
                        self.zoom_in()

                    return

    def zoom_in(self) -> None:
        initial_row_count = self.invisibleRootItem().rowCount()
        for i in range(initial_row_count):
            for j in range(self.invisibleRootItem().child(i).rowCount()):
                self.invisibleRootItem().appendRow(
                    self.invisibleRootItem().child(i).takeChild(j)
                )
        self.removeRows(0, initial_row_count)

    def iterate_nodes(
        self, root: Optional[QtGui.QStandardItem] = None
    ) -> Iterator[QtGui.QStandardItem]:
        """Yields nodes in a depth-first manner."""
        if root is None:
            root = self.invisibleRootItem()

        for i in range(root.rowCount()):
            child = root.child(i)
            yield child
            yield from self.iterate_nodes(child)

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


def serialise_hierarchy(
    root: QtGui.QStandardItem,
) -> list:
    hierarchy = []
    for i in range(root.rowCount()):
        child = root.child(i, 0)
        child_dictionary = child.toJson()
        if child.hasChildren():
            child_dictionary["children"] = serialise_hierarchy(child)
        else:
            child_dictionary["children"] = None

        hierarchy.append(child_dictionary)

    return hierarchy


def deserialise_hierarchy(hierarchy: list, root: QtGui.QStandardItem) -> None:
    if hierarchy is None:
        return

    for node in hierarchy:
        children = node.pop("children")
        node = StructureNode(**node)
        node.setEditable(False)
        node.setCheckable(True)
        node.setCheckState(QtCore.Qt.CheckState.Unchecked)

        deserialise_hierarchy(children, node)

        root.appendRow(node)
