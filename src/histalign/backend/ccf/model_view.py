# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations, annotations

from collections.abc import Iterator
from functools import cached_property
import json
import logging
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, computed_field
from PySide6 import QtCore

from histalign.backend import UserRole
from histalign.backend.ccf.paths import get_structures_hierarchy_path

# Structure set IDs for which no structure mask exists. These were found by
# brute-forcing GET requests for structure IDs and collecting the sets for which the
# requests failed. Some structures filtered this way might still be displayable in other
# software (e.g., Brain Explorer) but I am unsure where to get the mask in that case.
# For example, Uvula (IX), granular layer (UVUgr) with ID 10732 does not have a mask but
# can be shown in Brain Explorer.
# Note that the mesh for UVUgr is not available either from the official Brain Explorer
# meshes directory (ccf_2017).
MAGIC_ID_SETS = [
    (),
    (10,),
    (10, 12),
    (12,),
    (12, 112905813),
    (184527634,),
    (12, 184527634),
    (114512891, 112905828),
    (12, 184527634, 687527945),
]

Index = QtCore.QModelIndex
IndexType = QtCore.QModelIndex | QtCore.QPersistentModelIndex

_module_logger = logging.getLogger(__name__)


class StructureNode(BaseModel):
    """A structure node in the Allen Mouse Brain Atlas hierarchy.

    Attributes:
        acronym (str): Acronym of the structure.
        id (int): ID of the structure.
        name (str): Name of the structure.
        structure_id_path (list[int]): Parenting hierarchy of the structure.
        structure_set_ids (list[int]): Set IDs the structure belongs to.
        parent (Optional[StructureNode]): Parent node of the structure.
        children (list[StructureNode]): Children nodes of the structure.
        displayable (bool):
            Whether the structure has a mask available from the Allen Institute.
    """

    acronym: str
    id: int
    name: str
    structure_id_path: list[int]
    structure_set_ids: list[int]

    parent: Optional[StructureNode] = None
    children: list[StructureNode] = []

    @computed_field  # type: ignore[misc]
    @cached_property
    def displayable(self) -> bool:
        return tuple(sorted(self.structure_set_ids)) not in MAGIC_ID_SETS


class ABAStructureModel(QtCore.QAbstractItemModel):
    """An abstract base model class for Allen Mouse Brain Atlas structure models.

    Args:
        root (str):
            Name of the node to make root. If such a node does not exist, the root
            is left as-is.
        json_path (str | Path, optional):
            Path to the hierarchy file to parse. If left empty, the path is
            retrieved from the application's default directory.
        parent (Optional[QtCore.QObject], optional): Parent of this object.

    Signals:
        item_checked (QtCore.QModelIndex):
            Emits an item's index when it has been checked.
        item_unchecked (QtCore.QModelIndex):
            Emits an item's index when it has been unchecked.
    """

    item_checked: QtCore.Signal = QtCore.Signal(QtCore.QModelIndex)
    item_unchecked: QtCore.Signal = QtCore.Signal(QtCore.QModelIndex)

    def __init__(
        self,
        root: str = "Basic cell groups and regions",
        json_path: str | Path = "",
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        #
        self._root = build_structure_tree(json_path or get_structures_hierarchy_path())
        self._checked_indices = []

        if root:
            self._replace_root(root)

    def data(
        self, index: IndexType, role: int = QtCore.Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if not index.isValid():
            return None

        if index.column() == 1:
            if role == QtCore.Qt.ItemDataRole.CheckStateRole:
                return (
                    QtCore.Qt.CheckState.Checked
                    if index in self._checked_indices
                    else QtCore.Qt.CheckState.Unchecked
                )
            else:
                return None

        item = index.internalPointer()
        if (
            role == QtCore.Qt.ItemDataRole.DisplayRole
            or role == QtCore.Qt.ItemDataRole.ToolTipRole
        ):
            return f"{item.name} ({item.acronym})"
        elif role == UserRole.IS_DISPLAYABLE:
            return item.displayable
        elif role == UserRole.SHORTENED_NAME:
            name = f"{item.name} ({item.acronym})"
            if item.parent is not None:
                name = name.replace(item.parent.name, "")

            if name.startswith(","):
                name = name[1:]

            name = name.strip()

            name = name[0].upper() + name[1:]

            return name
        elif role == UserRole.NAME_NO_ACRONYM:
            return item.name

        return None

    def setData(
        self,
        index: IndexType,
        value: Any,
        role: int = QtCore.Qt.ItemDataRole.EditRole,
    ) -> bool:
        if not index.isValid():
            return False

        if role == QtCore.Qt.ItemDataRole.CheckStateRole:
            if value == QtCore.Qt.CheckState.Checked.value:
                self._checked_indices.append(index)
                self.item_checked.emit(index)
            else:
                self._checked_indices.remove(index)
                self.item_unchecked.emit(index)

            self.dataChanged.emit(index, index)

            return True

        return super().setData(index, value, role)

    def _replace_root(self, name: str) -> None:
        items = [*self._root.children]
        while items:
            item = items.pop(0)
            if item.name == name:
                self.beginResetModel()
                self._root = item
                self.endResetModel()
                return

            items.extend(item.children)

        _module_logger.error(f"Could not replace root with new item named '{name}'.")


class ABAStructureListModel(ABAStructureModel):
    """A model for the Allen Mouse Brain Atlas structure hierarchy in list form."""

    def __init__(
        self,
        root: str = "Basic cell groups and regions",
        json_path: str | Path = "",
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(root, json_path, parent)

        self._flatten()

    def index(self, row: int, column: int, parent: IndexType = Index()) -> Index:
        if not self.hasIndex(row, column, parent):
            return Index()

        return self.createIndex(row, column, self._root[row])

    # noinspection PyMethodOverriding
    def parent(self, child: IndexType) -> Index:  # type: ignore[override]
        return Index()

    def rowCount(self, parent: IndexType = Index()) -> int:
        return len(self._root)

    def columnCount(self, parent: IndexType = Index()) -> int:
        return 2

    def flags(self, index: IndexType) -> QtCore.Qt.ItemFlag:
        flags = QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable

        if index.column() == 1:
            flags |= (
                QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsEditable
            )

        return flags

    def _flatten(self) -> None:
        data = [self._root]
        for item in data:
            data.extend(item.children)

        self._root = data


class ABAStructureTreeModel(ABAStructureModel):
    """A model for the Allen Mouse Brain Atlas structure hierarchy in tree form."""

    def index(self, row: int, column: int, parent: IndexType = Index()) -> Index:
        if not self.hasIndex(row, column, parent):
            return Index()

        if not parent.isValid():
            parent_node = self._root
        else:
            parent_node = parent.internalPointer()
        child_node = parent_node.children[row]

        return self.createIndex(row, column, child_node)

    # noinspection PyMethodOverriding
    def parent(self, child: IndexType) -> Index:  # type: ignore[override]
        if not child.isValid():
            return Index()

        child_node = child.internalPointer()
        parent_node = child_node.parent
        if parent_node == self._root:
            return Index()

        return self.createIndex(
            parent_node.parent.children.index(parent_node), 0, parent_node
        )

    def rowCount(self, parent: IndexType = Index()) -> int:
        if not parent.isValid():
            return len(self._root.children)

        return len(parent.internalPointer().children)

    def columnCount(self, parent: IndexType = Index()) -> int:
        return 2

    def flags(self, index: IndexType) -> QtCore.Qt.ItemFlag:
        flags = QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable

        if index.column() == 1:
            flags |= (
                QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsEditable
            )

        return flags


def build_structure_tree(json_path: str | Path) -> StructureNode:
    """Builds a structure node tree from a JSON file.

    Args:
        json_path (str | Path): Path to the JSON file containing the hierarchy.

    Returns:
        StructureNode: The root node of the tree.
    """
    with open(json_path) as handle:
        contents = json.load(handle)

    return parse_structure_list(contents)


def parse_structure_list(structure_list: list[dict[str, Any]]) -> StructureNode:
    """Parses a structure list made up of node dictionaries into a tree.

    Note this assumes the list is provided in such an order that adding the nodes
    sequentially following a depth-first approach is possible.

    Args:
        structure_list (list[dict[str, Any]]): List of structure dictionaries.

    Returns:
        StructureNode: The root node of the tree.

    Raises:
        ValueError:
            When attempting to parse a child before its parent has been added to the
            tree.
    """
    root = StructureNode(**structure_list.pop(0))

    child = root
    parent = None
    while len(structure_list) > 0:
        structure = StructureNode(**structure_list.pop(0))
        if parent is None or parent is not structure.parent:
            parent = find_parent(child, structure.structure_id_path[-2])
            if parent is None:
                raise ValueError(
                    f"Parent (ID {structure.structure_id_path[-2]}) for "
                    f"structure (ID {structure.id}) not found."
                )
        structure.parent = parent
        parent.children.append(structure)

        child = structure

    return root


def find_parent(structure: StructureNode, id: int) -> Optional[StructureNode]:
    """Finds the node with ID `id` in the structure hierarchy.

    Note this does check the input node as well.

    Args:
        structure (StructureNode): Child node to walk the hierarchy of.
        id (int): ID of the parent node to look for.

    Returns:
        Optional[StructureNode]:
            The node with the given ID or `None` if such a node was not found.
    """
    if structure.id == id:
        return structure

    while structure.parent is not None:
        structure = structure.parent

        if structure.id == id:
            return structure

    return None


def iterate_tree_model_dfs(model: QtCore.QAbstractItemModel) -> Iterator[Index]:
    """Iterates a tree model using depth-first search.

    Args:
        model (QtCore.QAbstractItemModel): Model to traverse.

    Returns:
        Iterator[Index]: An iterator over the structure tree.
    """
    queue = [model.index(0, 0)]
    while len(queue) > 0:
        index = queue.pop(0)
        yield index
        for row_index in range(model.rowCount(index)):
            queue.append(model.index(row_index, 0, index))
