# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Any, Optional

from PySide6 import QtWidgets

from histalign.backend.models import QuantificationResults
from histalign.frontend.common_widgets import OneHeaderFrameLayout, TableWidget


class SliceResultsSummaryWidget(QtWidgets.QFrame):
    def __init__(
        self,
        file_name: str,
        data: dict[str, Any],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        #
        main_layout = OneHeaderFrameLayout(file_name)

        #
        table_widget = TableWidget(len(data), ["Structure", "Measure"])
        for i, (structure, measure) in enumerate(data.items()):
            table_widget.setItem(i, 0, QtWidgets.QTableWidgetItem(structure))
            table_widget.setItem(i, 1, QtWidgets.QTableWidgetItem(str(measure)))

        main_layout.add_widget(table_widget)

        self.setLayout(main_layout)

        self.setFrameStyle(QtWidgets.QFrame.Shape.Box | QtWidgets.QFrame.Shadow.Plain)
        self.setLineWidth(2)


class ResultsSummaryWidget(QtWidgets.QFrame):
    def __init__(
        self, results: QuantificationResults, parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)

        #
        main_layout = OneHeaderFrameLayout(str(results.settings.original_directory))

        #
        table_layout = QtWidgets.QGridLayout()

        table_layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMaximumSize)
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.setHorizontalSpacing(20)
        table_layout.setVerticalSpacing(10)

        for index, (file_name, result) in enumerate(results.data.items()):
            slice_summary = SliceResultsSummaryWidget(file_name, result)

            table_layout.addWidget(slice_summary, *divmod(index, 2))

        main_layout.add_layout(table_layout)

        self.setLayout(main_layout)

        self.setFrameStyle(QtWidgets.QFrame.Shape.Box | QtWidgets.QFrame.Shadow.Plain)
        self.setLineWidth(2)


class ViewWidget(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().addWidget(QtWidgets.QWidget())

        # from PySide6 import QtCore
        #
        # self._timer = QtCore.QTimer()
        # self._timer.timeout.connect(self.dumpObjectTree)
        # self._timer.start(1000)

    def parse_results(self, results_list: list[QuantificationResults]) -> None:
        self.layout().takeAt(0).widget().deleteLater()

        container_widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        container_widget.setLayout(layout)

        for i, results in enumerate(results_list):
            results_summary_widget = ResultsSummaryWidget(results)
            layout.addWidget(results_summary_widget, *divmod(i, 2))

        self.layout().addWidget(container_widget)

    def remove_layout(self) -> None:
        self.layout().setParent(QtWidgets.QWidget())
