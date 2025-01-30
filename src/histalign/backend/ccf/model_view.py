# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import logging
from typing import Any

from PySide6 import QtCore, QtGui

from histalign.backend.ccf.paths import get_structures_hierarchy_path

_module_logger = logging.getLogger(__name__)


class StructureNode(QtGui.QStandardItem):
    name: str
    id: int
    acronym: str
    parent_node: StructureNode | None
    parent_id: int
    children_nodes: list[StructureNode]
    checked: bool = False

    @classmethod
    def from_dictionary(cls, dictionary: dict) -> StructureNode:
        parent_id = dictionary.get("structure_id_path", -1)
        if isinstance(parent_id, list):
            if len(parent_id) == 1:
                parent_id = parent_id[0]
            else:
                parent_id = parent_id[-2]

        instance = cls()
        instance.name = dictionary.get("name", "None")
        instance.id = dictionary.get("id", -1)
        instance.acronym = dictionary.get("acronym", "None")
        instance.parent_node = None
        instance.parent_id = parent_id
        instance.children_nodes = dictionary.get("children_nodes", [])

        instance.setCheckable(True)
        instance.setCheckState(QtCore.Qt.CheckState.Unchecked)

        return instance

    def add_child(self, child: StructureNode) -> None:
        self.children_nodes.append(child)

    def child(self, row: int, column: int | None = None) -> StructureNode:
        return self.children_nodes[row]

    def child_count(self) -> int:
        return len(self.children_nodes)

    def column_count(self) -> int:
        return 2

    # noinspection PyMethodOverriding
    def data(self, column: int) -> Any:
        if column == 0:
            return self.acronym
        elif column == 1:
            return self.name
        else:
            return None

    def is_checked(self) -> bool:
        return self.checked

    def parent(self) -> StructureNode:
        return self.parent_node

    def row(self) -> int:
        if self.parent_node is not None:
            return self.parent_node.children_nodes.index(self)
        return 0

    def set_checked(self, checked: bool) -> None:
        self.checked = checked


class ABAStructureTreeModel(QtCore.QAbstractItemModel):
    item_checked: QtCore.Signal = QtCore.Signal(QtCore.QModelIndex)
    item_unchecked: QtCore.Signal = QtCore.Signal(QtCore.QModelIndex)

    def __init__(
        self,
        json_path: str | Path | None = None,
        root_name: str | None = "Basic cell groups and regions",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        # Use the provided or default JSON file path and build the hierarchy tree
        json_path = json_path or get_structures_hierarchy_path()
        self.build_tree(json_path)

        # "Zoom in" on a node and replace the root with it
        if root_name is not None:
            self.replace_root(root_name)

    def build_tree(self, json_path: str | Path) -> None:
        with open(json_path, "rb") as handle:
            contents = json.load(handle)
        self.root = parse_structures(contents)

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex | None = None
    ) -> int:
        if parent is not None and parent.isValid():
            return parent.internalPointer().column_count()
        else:
            return self.root.column_count()

    def data(
        self,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        role: QtCore.Qt.ItemDataRole = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid():
            return None

        item = index.internalPointer()
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return item.data(index.column())
        elif role == QtCore.Qt.ItemDataRole.ToolTipRole and index.column() == 1:
            return item.data(index.column())
        elif role == QtCore.Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            return (
                QtCore.Qt.CheckState.Checked
                if item.is_checked()
                else QtCore.Qt.CheckState.Unchecked
            )

    def flags(
        self, index: QtCore.QModelIndex | QtCore.QPersistentModelIndex
    ) -> QtCore.Qt.ItemFlag:
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags

        flags = QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            flags |= QtCore.Qt.ItemFlag.ItemIsUserCheckable

        return flags

    def get_checked_items(self) -> list[StructureNode]:
        checked_items = []
        for node in iterate_structure_node_right_biased_dfs(self.root):
            if node.is_checked():
                checked_items.append(node)

        return checked_items

    def get_item_index(self, item: StructureNode) -> QtCore.QModelIndex:
        if item == self.root:
            return self.index(0, 0)

        nodes_to_root = [item]
        current_item = item
        while current_item.parent_node != self.root:
            nodes_to_root.append(current_item.parent_node)
            current_item = current_item.parent_node

        index = QtCore.QModelIndex()
        for node in nodes_to_root[::-1]:
            index = self.index(node.row(), 0, index)

        return index

    def headerData(
        self,
        column_index: int,
        orientation: QtCore.Qt.Orientation,
        role: int | None = None,
    ) -> str | None:
        if (
            orientation == QtCore.Qt.Orientation.Horizontal
            and role == QtCore.Qt.ItemDataRole.DisplayRole
        ):
            return ["Acronym", "Structure Name"][column_index]
        return None

    def index(
        self,
        row: int,
        column: int,
        parent: (
            QtCore.QModelIndex | Qtcore.QPersistentModelIndex
        ) = QtCore.QModelIndex(),
    ) -> QtCore.QModelIndex:
        if not self.hasIndex(row, column, parent) or parent is None:
            return QtCore.QModelIndex()

        if not parent.isValid():
            parent_item = self.root
        else:
            parent_item = parent.internalPointer()
        child_item = parent_item.children_nodes[row]

        return self.createIndex(row, column, child_item)

    # noinspection PyMethodOverriding
    def parent(
        self, index: QtCore.QModelIndex | QtCore.QPersistentModelIndex
    ) -> QtCore.QModelIndex:
        if not index.isValid():
            return QtCore.QModelIndex()

        child_item = index.internalPointer()
        parent_item = child_item.parent()
        if parent_item == self.root:
            return QtCore.QModelIndex()
        return self.createIndex(parent_item.row(), 0, parent_item)

    def replace_root(self, node_name: str) -> None:
        node = find_structure_node_by_name(self.root, node_name)
        if node is not None:
            self.modelAboutToBeReset.emit()
            self.root = node
            self.modelReset.emit()

    def rowCount(
        self, parent: QtCore.QModelIndex | QtCore.QPersistentModelIndex | None = None
    ) -> int:
        if parent is None:
            return self.root.child_count()
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            parent_item = self.root
        else:
            parent_item = parent.internalPointer()
        return parent_item.child_count()

    def setData(
        self,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        value: Any,
        role: QtCore.Qt.ItemDataRole = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> bool:
        if not index.isValid():
            return False

        if role == QtCore.Qt.ItemDataRole.CheckStateRole:
            item = index.internalPointer()
            item.set_checked(not item.is_checked())

            if item.is_checked():
                self.item_checked.emit(index)
            else:
                self.item_unchecked.emit(index)

            return True

        return super().setData(index, value, role)


def find_structure_node_by_id(root: StructureNode, id: int) -> StructureNode | None:
    """Searches structure tree using right-biased DFS.

    Args:
        root (StructureNode): Root node to start the search from.
        id (int): ID of the node to search for.

    Returns:
        StructureNode | None: The node with id `id` or `None` if it was not found.
    """
    for node in iterate_structure_node_right_biased_dfs(root):
        if node.id == id:
            return node

    return None


def find_structure_node_by_name(root: StructureNode, name: str) -> StructureNode | None:
    """Searches structure tree using right-biased DFS.

    Args:
        root (StructureNode): Root node to start the search from.
        name (str): Name of the node to search for.

    Returns:
        StructureNode | None: The node with name `name` or `None` if it was not found.
    """
    for node in iterate_structure_node_right_biased_dfs(root):
        if node.name == name:
            return node

    return None


def iterate_structure_node_dfs(root: StructureNode) -> Iterator[StructureNode]:
    """Iterates structure tree using depth-first search.

    Args:
        root (StructureNode): Root node to start the iteration form.

    Returns:
        Iterator[StructureNode]: An iterator over the structure tree.
    """
    queue = [root]
    while len(queue) > 0:
        node = queue.pop()
        yield node
        queue.extend(node.children_nodes[::-1])


def iterate_structure_node_right_biased_dfs(
    root: StructureNode,
) -> Iterator[StructureNode]:
    """Iterates structure tree using right-biased depth-first search.

    Given the context, this can be much slower than a regular DFS. However, when used
    to parse the Allen structures tree, the nodes are added from left to right, hence
    looking from right to left means searching fewer nodes.

    Args:
        root (StructureNode): Root node to start the iteration form.

    Returns:
        Iterator[StructureNode]: An iterator over the structure tree.
    """
    queue = [root]
    while len(queue) > 0:
        node = queue.pop()
        yield node
        queue.extend(node.children_nodes)


def parse_structures(structure_list: StructureList) -> StructureNode:
    """Parses a structure list made up of node dictionaries.

    Args:
        structure_list (StructureList): List of structure dictionaries.

    Returns:
        StructureNode: The root node containing all the other nodes.

    Raises:
        ValueError:
            When attempting to parse a child before its parent has been added to the
            tree.
    """
    root = StructureNode.from_dictionary(structure_list.pop(0))

    parent = None  # Cache parent to optimise leaf nodes
    while len(structure_list) > 0:
        node = StructureNode.from_dictionary(structure_list.pop(0))
        if parent is None or parent is not node.parent_node:
            parent = find_structure_node_by_id(root, node.parent_id)
            if parent is None:
                raise ValueError(f"Parent node with ID {node.parent_id} not found.")
        node.parent_node = parent
        parent.children_nodes.append(node)

    return root
