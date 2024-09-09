# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import json
import logging
from pathlib import Path
from typing import Any, Optional

from PySide6 import QtCore, QtGui, QtWidgets
from pydantic import ValidationError

from histalign.backend.models import QuantificationResults


class ResultsTableModel(QtCore.QAbstractTableModel):
    def __init__(
        self, project_directory: str, parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)

        self._data = self.parse_project(project_directory)
        self._columns = ["", "Date", "Measure", "Structures", "Directory"]

    def data(
        self, index: QtCore.QModelIndex | QtCore.QPersistentModelIndex, role: int = ...
    ) -> Any:
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if index.column() > 0:
                return self._data[index.row()][index.column()]
        elif role == QtCore.Qt.ItemDataRole.TextAlignmentRole:
            if index.column() != len(self._columns) - 1:
                return QtCore.Qt.AlignmentFlag.AlignCenter
        elif role == QtCore.Qt.ItemDataRole.CheckStateRole:
            if index.column() == 0:
                if self._data[index.row()][0] == "[ ]":
                    return QtCore.Qt.CheckState.Unchecked
                else:
                    return QtCore.Qt.CheckState.Checked
        elif role == QtCore.Qt.ItemDataRole.UserRole:
            return self._data[index.row()][-1]

    def setData(
        self,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        value: Any,
        role: int = ...,
    ) -> bool:
        if role == QtCore.Qt.ItemDataRole.CheckStateRole:
            if index.column() == 0:
                state = self._data[index.row()][index.column()]
                if state == "[ ]":
                    toggled_state = "[X]"
                else:
                    toggled_state = "[ ]"
                self._data[index.row()][index.column()] = toggled_state

        return True

    def headerData(
        self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...
    ) -> Any:
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._columns[section]

    def rowCount(
        self, parent: QtCore.QModelIndex | QtCore.QPersistentModelIndex = ...
    ) -> int:
        return len(self._data)

    def columnCount(
        self, parent: QtCore.QModelIndex | QtCore.QPersistentModelIndex = ...
    ) -> int:
        return len(self._columns)

    def flags(self, index):
        if index.column() == 0:
            return super().flags(index) | QtCore.Qt.ItemFlag.ItemIsUserCheckable

        return super().flags(index)

    @staticmethod
    def parse_project(project_directory: str) -> list[list[str]]:
        data = []

        quantification_path = Path(project_directory) / "quantification"
        if not quantification_path.exists():
            return data

        for file in quantification_path.iterdir():
            try:
                with open(file) as handle:
                    contents = json.load(handle)
                results = QuantificationResults(**contents)
            except (ValidationError, json.JSONDecodeError) as error:
                logging.getLogger(__name__).error(
                    f"Failed to load quantification results from '{file}'."
                )
                logging.getLogger(__name__).error(error)
                continue

            data.append(
                [
                    "[ ]",
                    results.timestamp.strftime("%Y/%m/%d - %H:%M"),
                    results.settings.quantification_measure.value,
                    ", ".join(results.settings.structures),
                    str(results.settings.original_directory),
                    results,
                ]
            )

        return data


class ResultsTableView(QtWidgets.QTableView):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

        self.verticalHeader().hide()
        self.horizontalHeader().setStretchLastSection(True)

        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )

        self.installEventFilter(self)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        for i in range(self.model().columnCount() - 1):
            self.resizeColumnToContents(i)

            if i > 0:
                self.horizontalHeader().resizeSection(
                    i, self.horizontalHeader().sectionSize(i) + 20
                )

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        match event.type():
            case QtCore.QEvent.Type.KeyPress:
                if event.key() == QtCore.Qt.Key.Key_Escape:
                    self.selectionModel().clearSelection()
                    self.selectionModel().clearCurrentIndex()

                    return True
            case QtCore.QEvent.Type.FocusIn:
                # Disable ugly single-cell selection when gaining focus from non-click
                event.accept()
                return True
            case QtCore.QEvent.Type.FocusOut:
                self.selectionModel().clearSelection()
                self.selectionModel().clearCurrentIndex()

                return True

        return super().eventFilter(watched, event)


class ResultsWidgets(QtWidgets.QWidget):
    project_directory: str = ""

    model: ResultsTableModel
    view: QtWidgets.QTableView
    submit_button: QtWidgets.QPushButton

    submitted: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        view = ResultsTableView()

        self.view = view

        #
        submit_button = QtWidgets.QPushButton("Submit")
        submit_button.clicked.connect(self.submitted.emit)

        self.submit_button = submit_button

        #
        layout = QtWidgets.QVBoxLayout()

        layout.addWidget(view, stretch=1)
        layout.addWidget(
            submit_button,
            alignment=QtCore.Qt.AlignmentFlag.AlignBottom
            | QtCore.Qt.AlignmentFlag.AlignLeft,
        )

        self.setLayout(layout)

    def parse_project(self, project_path: str = "") -> None:
        if project_path:
            self.project_directory = str(Path(project_path).parent)
        elif not self.project_directory:
            raise ValueError("Cannot parse project without providing a path first.")

        model = ResultsTableModel(self.project_directory, self)

        self.view.setModel(model)
        self.model = model

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self.parse_project()
