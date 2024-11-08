# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtWidgets

from histalign.backend.models import QuantificationResults
from histalign.frontend.quantification.visualisers import (
    CorticalDepthVisualiser,
    ResultsSummaryWidget,
)


def get_appropriate_visualiser(quantification_measure: str) -> type[QtWidgets.QWidget]:
    match quantification_measure:
        case "average_fluorescence":
            return ResultsSummaryWidget
        case "cortical_depth":
            return CorticalDepthVisualiser
        case other:
            raise ValueError(f"Unknown quantification measure '{other}'.")


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

        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(content_area)

        self.setLayout(layout)

    def parse_results(self, results_list: list[QuantificationResults]) -> None:
        # TODO: Add `parse_results` to `ResultSummaryWidget` to get rid of match here
        visualiser = get_appropriate_visualiser(
            results_list[0].settings.quantification_measure
        )
        match results_list[0].settings.quantification_measure:
            case "average_fluorescence":
                container_widget = QtWidgets.QWidget()
                grid_layout = QtWidgets.QGridLayout()
                container_widget.setLayout(grid_layout)
                self.content_area.setWidget(container_widget)

                self.container_widget = container_widget

                for i, results in enumerate(results_list):
                    results_summary_widget = visualiser(results)
                    grid_layout.addWidget(results_summary_widget, *divmod(i, 2))
            case "cortical_depth":
                self.container_widget = visualiser()
                self.content_area.setWidget(self.container_widget)
                self.container_widget.parse_results(results_list)
            case other:
                raise ValueError(f"Unknown quantification measure '{other}'.")
