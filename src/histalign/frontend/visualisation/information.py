# SPDX-FileCopyrightText: 2025-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import re

from PySide6 import QtCore, QtWidgets

from histalign.backend import UserRole
from histalign.backend.ccf.model_view import ABAStructureListModel
from histalign.frontend.common_widgets import (
    CheckAwareSortFilterProxyModel,
    DisplayableSortFilterProxyModel,
    StructureTableView,
)


class InformationWidget(QtWidgets.QTabWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        #
        tab1 = StructuresWidget()

        self.structures_widget = tab1

        #
        tab2 = QtWidgets.QWidget()

        self.tab2 = tab2

        #
        tab3 = QtWidgets.QWidget()

        self.tab3 = tab3

        #
        self.addTab(tab1, "Structures")
        self.addTab(tab2, "PLACEHOLDER")
        self.addTab(tab3, "PLACEHOLDER")


class StructuresWidget(QtWidgets.QWidget):
    structure_checked: QtCore.Signal = QtCore.Signal(str)
    structure_unchecked: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        #
        search_line_edit = QtWidgets.QLineEdit()

        search_line_edit.textChanged.connect(self.filter_model)

        self.search_line_edit = search_line_edit

        #
        list_model = ABAStructureListModel()

        list_model.item_checked.connect(
            lambda x: self.structure_checked.emit(x.data(UserRole.NAME_NO_ACRONYM))
        )
        list_model.item_unchecked.connect(
            lambda x: self.structure_unchecked.emit(x.data(UserRole.NAME_NO_ACRONYM))
        )

        self.list_model = list_model

        #
        intermediate_model = DisplayableSortFilterProxyModel()

        intermediate_model.setSourceModel(list_model)

        self._intermediate_sort_proxy = intermediate_model

        #
        sorted_list_model = CheckAwareSortFilterProxyModel()

        sorted_list_model.setSourceModel(intermediate_model)

        sorted_list_model.setFilterCaseSensitivity(
            QtCore.Qt.CaseSensitivity.CaseInsensitive
        )
        sorted_list_model.setSortCaseSensitivity(
            QtCore.Qt.CaseSensitivity.CaseInsensitive
        )
        sorted_list_model.sort(0)

        # Dynamic sorting does not allow changing check state through a proxy
        sorted_list_model.setDynamicSortFilter(False)
        list_model.dataChanged.connect(lambda _: sorted_list_model.sort(0))

        self._sorted_list_model = sorted_list_model

        #
        table_view = StructureTableView(sorted_list_model)

        self.table_view = table_view

        #
        layout = QtWidgets.QVBoxLayout()

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(search_line_edit)
        layout.addWidget(table_view, stretch=1)

        self.setLayout(layout)

    @QtCore.Slot()
    def filter_model(self, regex: str) -> None:
        search_regex = regex.split(" ")
        search_regex = map(re.escape, search_regex)
        search_regex = ".*".join(search_regex)

        self._sorted_list_model.setFilterRegularExpression(rf".*{search_regex}.*")
