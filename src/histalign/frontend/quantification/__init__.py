# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets

from histalign.frontend.quantification.prepare import (
    PrepareWidget,
    QuantificationParametersFrame,
)
from histalign.frontend.quantification.results import ResultsWidget
from histalign.frontend.quantification.view import ViewWidget

_module_logger = logging.getLogger(__name__)


class QuantificationWidget(QtWidgets.QWidget):
    project_loaded: bool = False

    prepare_tab: PrepareWidget
    results_tab: ResultsWidget
    view_tab: ViewWidget
    tab_widget: QtWidgets.QTabWidget

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        prepare_tab = PrepareWidget()

        self.prepare_tab = prepare_tab

        #
        results_tab = ResultsWidget()

        self.results_tab = results_tab

        #
        view_tab = ViewWidget()
        results_tab.submitted.connect(view_tab.parse_results)
        results_tab.submitted.connect(
            lambda: self.tab_widget.tabBar().setCurrentIndex(
                self.tab_widget.indexOf(self.view_tab)
            )
        )

        self.view_tab = view_tab

        #
        tab_widget = QtWidgets.QTabWidget()

        tab_widget.addTab(prepare_tab, "Prepare")
        prepare_tab.setAutoFillBackground(True)
        tab_widget.addTab(results_tab, "Results")
        results_tab.setAutoFillBackground(True)
        tab_widget.addTab(view_tab, "View")
        view_tab.setAutoFillBackground(True)

        self.tab_widget = tab_widget

        #
        layout = QtWidgets.QHBoxLayout()

        layout.addWidget(tab_widget)

        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

    @QtCore.Slot()
    def open_project(self, project_root: str | Path, *args, **kwargs) -> None:
        project_directory = Path(project_root)

        self.prepare_tab.parse_project(project_directory)
        self.results_tab.parse_project(project_directory)

        self.tab_widget.setEnabled(True)
        self.project_loaded = True
