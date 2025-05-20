# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
from typing import Any, Optional

import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.models import (
    Quantification,
)

_module_logger = logging.getLogger(__name__)


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
        self._columns = ["", "Date", "Quantification", "Directory"]

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
                if self._data[index.row()][0]:
                    return QtCore.Qt.CheckState.Checked
                else:
                    return QtCore.Qt.CheckState.Unchecked
        elif role == QtCore.Qt.ItemDataRole.UserRole:
            return self._data[index.row()][-1]

    def setData(
        self,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        value: Any,
        role: int = ...,
    ) -> bool:
        if role == QtCore.Qt.ItemDataRole.CheckStateRole:
            self._data[index.row()][0] = not self._data[index.row()][0]

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
    def parse_project(
        project_directory: Path,
    ) -> list[list[bool | str | str | str | pd.DataFrame]]:
        data = []

        quantification_path = project_directory / "quantification"
        if not quantification_path.exists():
            return data

        for path in quantification_path.iterdir():
            if path.name.startswith(".") or path.suffix != ".csv":
                continue

            df = pd.read_csv(path, index_col=0)

            *source, quantification, timestamp_ymd, timestamp_hm = path.stem.split("_")
            source = "_".join(source)
            quantification = Quantification(quantification).display_value.capitalize()
            full_timestamp = (
                f"{timestamp_hm[:2]}:{timestamp_hm[2:]} "
                f"{timestamp_ymd[6:]}"
                f"/{timestamp_ymd[4:6]}"
                f"/{timestamp_ymd[:4]}"
            )

            data.append([False, full_timestamp, quantification, source, df])

        return data


class ResultsTableFilterProxyModel(QtCore.QSortFilterProxyModel):
    measure_regex: str = ""

    filter_changed: QtCore.Signal = QtCore.Signal()
    checked_state_changed: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)

    def set_quantification_regex(self, pattern: str) -> None:
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
        if self.model() is None:
            return

        for i in range(self.model().columnCount() - 1):
            self.resizeColumnToContents(i)

            if i > 0:
                self.horizontalHeader().resizeSection(
                    i, self.horizontalHeader().sectionSize(i) + 20
                )

    def setModel(self, model: Optional[QtCore.QAbstractItemModel]) -> None:
        super().setModel(model)

        if model is not None:
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
                model = self.selectionModel()
                if model is None:
                    return True

                model.clearSelection()
                model.clearCurrentIndex()

                return True

        return super().eventFilter(watched, event)


class ResultsWidget(QtWidgets.QWidget):
    project_directory: Optional[Path]

    filter_layout: QtWidgets.QFormLayout
    model: Optional[ResultsTableModel]
    proxy_model: Optional[ResultsTableFilterProxyModel]
    view: ResultsTableView
    export_button: QtWidgets.QPushButton
    parsed_timestamp: float = -1.0

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.project_directory = None
        self.model = None
        self.proxy_model = None

        #
        quantification_widget = QtWidgets.QComboBox()
        quantification_widget.addItems(
            [variant.display_value.capitalize() for variant in Quantification]
        )

        quantification_widget.currentTextChanged.connect(self.filter_model)

        self.quantification_widget = quantification_widget

        #
        filter_layout = QtWidgets.QFormLayout()
        filter_layout.addRow("Quantification", quantification_widget)

        self.filter_layout = filter_layout

        #
        view = ResultsTableView()
        self.quantification_widget.currentTextChanged.connect(self.update_buttons_state)

        self.view = view

        #
        export_button = QtWidgets.QPushButton("Export")
        export_button.clicked.connect(self.export_checked)
        export_button.setEnabled(False)

        self.export_button = export_button

        #
        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(filter_layout)
        layout.addWidget(view, stretch=1)
        layout.addWidget(export_button)
        self.setLayout(layout)

    def has_at_least_one_checked(self) -> bool:
        if self.proxy_model is None:
            return False

        for i in range(self.proxy_model.rowCount()):
            if (
                self.proxy_model.index(i, 0).data(QtCore.Qt.ItemDataRole.CheckStateRole)
                == QtCore.Qt.CheckState.Checked
            ):
                return True

        return False

    def get_checked_items(self) -> list[QtCore.QModelIndex]:
        checked_items = []
        for i in range(self.proxy_model.rowCount()):
            index = self.proxy_model.index(i, 0)
            if (
                index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
                == QtCore.Qt.CheckState.Checked
            ):
                checked_items.append(index)

        return checked_items

    def parse_project(self, project_directory: Path) -> None:
        quantification_path = project_directory / "quantification"
        if not os.path.exists(quantification_path):
            return

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

        self.filter_model()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)

        # Force reparse when shown
        if self.project_directory is not None:
            self.parse_project(self.project_directory)

    def reset(self) -> None:
        self.view.setModel(None)
        self.update_buttons_state()

    @QtCore.Slot()
    def filter_model(self, regex: str = "") -> None:
        quantification_regex = regex or self.quantification_widget.currentText()
        self.proxy_model.set_quantification_regex(quantification_regex)

    @QtCore.Slot()
    def update_buttons_state(self) -> None:
        self.export_button.setEnabled(self.has_at_least_one_checked())

    @QtCore.Slot()
    def export_checked(self) -> None:
        checked_items = self.get_checked_items()
        if not checked_items:
            _module_logger.error("Could not export results: no checked items found.")
            return

        dataframes = [
            index.data(QtCore.Qt.ItemDataRole.UserRole) for index in checked_items
        ]
        merged_dataframe = pd.concat(dataframes, ignore_index=True)

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

        output_path = file_dialog.selectFile()[0]
        _module_logger.debug(f"Exporting results to: {output_path}")
        merged_dataframe.to_csv(output_path)
