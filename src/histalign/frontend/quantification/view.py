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
    content_area: QtWidgets.QScrollArea
    container_widget: QtWidgets.QWidget

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        container_widget = QtWidgets.QWidget()

        self.container_widget = container_widget

        #
        content_area = QtWidgets.QScrollArea()
        content_area.setWidgetResizable(True)
        content_area.setWidget(container_widget)

        self.content_area = content_area

        #
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(content_area)

        self.setLayout(layout)

    def parse_results(self, results_list: list[QuantificationResults]) -> None:
        container_widget = QtWidgets.QWidget()
        grid_layout = QtWidgets.QGridLayout()
        container_widget.setLayout(grid_layout)
        self.content_area.setWidget(container_widget)

        self.container_widget = container_widget

        for i, results in enumerate(results_list):
            print(results)
            results_summary_widget = ResultsSummaryWidget(results)
            grid_layout.addWidget(results_summary_widget, *divmod(i, 2))
