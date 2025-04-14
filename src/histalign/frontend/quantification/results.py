# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Optional

from pydantic import ValidationError
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.models import (
    AverageFluorescenceMeasureSettings,
    CorticalDepthMeasureSettings,
    MeasureSettings,
    QuantificationResults,
)
from histalign.frontend.quantification.view import get_appropriate_visualiser


def get_appropriate_measure_settings(
    quantification_measure: str,
) -> type[MeasureSettings]:
    match quantification_measure:
        case "average_fluorescence":
            settings = AverageFluorescenceMeasureSettings
        case "cortical_depth":
            settings = CorticalDepthMeasureSettings
        case _:
            raise ValueError(
                f"Unknown quantification measure '{quantification_measure}'."
            )

    return settings


def get_default_export_directory(project_directory: Path) -> Path:
    export_directory = project_directory / "exports"
    if not export_directory.exists():
        os.makedirs(export_directory, exist_ok=True)

    return export_directory


class ResultsTableModel(QtCore.QAbstractTableModel):
    def __init__(
        self, project_directory: Path, parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)

        self._data = self.parse_project(project_directory)
        self._columns = ["", "Date", "Measure", "Directory"]

    def data(
        self, index: QtCore.QModelIndex | QtCore.QPersistentModelIndex, role: int = ...
    ) -> Any:
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if 0 < index.column() < self.columnCount():
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
    def parse_project(project_directory: Path) -> list[list[str]]:
        data = []

        quantification_path = project_directory / "quantification"
        if not quantification_path.exists():
            return data

        for file in quantification_path.iterdir():
            try:
                with open(file) as handle:
                    contents = json.load(handle)
                results = QuantificationResults(**contents)

                results.settings.measure_settings = get_appropriate_measure_settings(
                    contents["settings"]["quantification_measure"]
                )(**contents["settings"]["measure_settings"])
            except (ValidationError, json.JSONDecodeError) as error:
                logging.getLogger(__name__).error(
                    f"Failed to load quantification results from '{file}'."
                )
                logging.getLogger(__name__).error(error)
                continue

            quantification_measure = (
                results.settings.quantification_measure.value.replace("_", " ")
            )
            quantification_measure = (
                quantification_measure[0].upper() + quantification_measure[1:]
            )
            data.append(
                [
                    "[ ]",
                    results.timestamp.strftime("%Y/%m/%d - %H:%M"),
                    quantification_measure,
                    str(results.settings.original_directory),
                    results,
                ]
            )

        return data


class ResultsTableFilterProxyModel(QtCore.QSortFilterProxyModel):
    measure_regex: str = ""

    filter_changed: QtCore.Signal = QtCore.Signal()
    checked_state_changed: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)

    def set_measure_regular_expression(self, pattern: str) -> None:
        self.measure_regex = pattern
        self.invalidateFilter()

    def setData(
        self,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        value: Any,
        role: int = ...,
    ) -> bool:
        result = super().setData(index, value, role)
        self.checked_state_changed.emit()
        return result

    def filterAcceptsRow(
        self, source_row: int, source_parent: QtCore.QModelIndex
    ) -> bool:
        measure_index = self.sourceModel().index(source_row, 2, source_parent)
        measure = measure_index.data(QtCore.Qt.ItemDataRole.DisplayRole)

        return bool(re.findall(self.measure_regex, measure))

    def invalidateFilter(self):
        super().invalidateFilter()

        self.filter_changed.emit()


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

    def resizeColumnsToContents(self):
        for i in range(self.model().columnCount() - 1):
            self.resizeColumnToContents(i)

            if i > 0:
                self.horizontalHeader().resizeSection(
                    i, self.horizontalHeader().sectionSize(i) + 20
                )

    def setModel(self, model: QtCore.QAbstractItemModel) -> None:
        super().setModel(model)

        model.filter_changed.connect(self.resizeColumnsToContents)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        self.resizeColumnsToContents()

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


class ResultsWidget(QtWidgets.QWidget):
    project_directory: Optional[Path] = None

    filter_layout: QtWidgets.QFormLayout
    model: ResultsTableModel
    proxy_model: ResultsTableFilterProxyModel
    view: ResultsTableView
    view_button: QtWidgets.QPushButton
    export_button: QtWidgets.QPushButton
    parsed_timestamp: float = -1.0

    submitted: QtCore.Signal = QtCore.Signal(list)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        measure_widget = QtWidgets.QComboBox()
        measure_widget.addItems(["Average fluorescence", "Cortical depth"])

        measure_widget.currentTextChanged.connect(self.filter_model)

        self.measure_widget = measure_widget

        #
        filter_layout = QtWidgets.QFormLayout()
        filter_layout.addRow("Measure", measure_widget)

        self.filter_layout = filter_layout

        #
        view = ResultsTableView()
        self.measure_widget.currentTextChanged.connect(self.update_buttons_state)

        self.view = view

        #
        view_button = QtWidgets.QPushButton("View")
        view_button.clicked.connect(self.submit_checked)
        view_button.setEnabled(False)

        self.view_button = view_button

        #
        export_button = QtWidgets.QPushButton("Export")
        export_button.clicked.connect(self.export_checked)
        export_button.setEnabled(False)

        self.export_button = export_button

        #
        button_layout = QtWidgets.QHBoxLayout()

        button_layout.addWidget(view_button)
        button_layout.addWidget(export_button)

        #
        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(filter_layout)
        layout.addWidget(view, stretch=1)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def has_at_least_one_checked(self) -> bool:
        if not hasattr(self, "proxy_model"):
            return False

        for i in range(self.proxy_model.rowCount()):
            if (
                self.proxy_model.index(i, 0).data(QtCore.Qt.ItemDataRole.CheckStateRole)
                == QtCore.Qt.CheckState.Checked
            ):
                return True

        return False

    def get_checked_items(self) -> list[QuantificationResults]:
        checked_items = []
        for i in range(self.proxy_model.rowCount()):
            index = self.proxy_model.index(i, 0)
            if (
                index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
                == QtCore.Qt.CheckState.Checked
            ):
                checked_items.append(index.data(QtCore.Qt.ItemDataRole.UserRole))

        return checked_items

    def parse_project(self, project_directory: Path) -> None:
        quantification_path = project_directory / "quantification"
        if not os.path.exists(quantification_path):
            os.makedirs(quantification_path, exist_ok=True)

        if (
            timestamp := os.stat(quantification_path).st_mtime
        ) == self.parsed_timestamp:
            return

        self.parsed_timestamp = timestamp
        self.project_directory = project_directory

        model = ResultsTableModel(project_directory, self)

        proxy_model = ResultsTableFilterProxyModel(self)
        proxy_model.setSourceModel(model)

        proxy_model.checked_state_changed.connect(self.update_buttons_state)

        self.model = model
        self.proxy_model = proxy_model
        self.view.setModel(proxy_model)

        self.filter_model(...)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)

        if self.project_directory is not None:
            self.parse_project(self.project_directory)

    def reset(self) -> None:
        self.view = ResultsTableView()
        self.update_buttons_state()

    @QtCore.Slot()
    def filter_model(self, _) -> None:
        measure_regex = self.measure_widget.currentText()
        self.proxy_model.set_measure_regular_expression(measure_regex)

    @QtCore.Slot()
    def update_buttons_state(self) -> None:
        self.view_button.setEnabled(self.has_at_least_one_checked())
        self.export_button.setEnabled(self.has_at_least_one_checked())

    @QtCore.Slot()
    def submit_checked(self) -> None:
        self.submitted.emit(self.get_checked_items())

    @QtCore.Slot()
    def export_checked(self) -> None:
        checked_items = self.get_checked_items()

        if not checked_items:
            return

        visualiser = get_appropriate_visualiser(
            checked_items[0].settings.quantification_measure
        )
        dataframe = visualiser.parse_results_to_dataframe(checked_items)

        file_dialog = QtWidgets.QFileDialog(self)
        file_dialog.setWindowTitle("Select location to save results")
        file_dialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        file_dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptSave)
        file_dialog.selectFile("quantification_result.csv")
        file_dialog.setDefaultSuffix("csv")
        file_dialog.setDirectory(
            str(get_default_export_directory(self.project_directory))
        )
        file_dialog.setNameFilter("Comma Separated Value file (*.csv)")
        file_dialog.setOption(QtWidgets.QFileDialog.Option.DontUseNativeDialog)

        file_dialog.exec()
        if file_dialog.result() == QtWidgets.QDialog.DialogCode.Rejected:
            return

        dataframe.to_csv(file_dialog.selectedFiles()[0])
