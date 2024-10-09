# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from pathlib import Path
import sys
from typing import Optional

from PySide6 import QtCore, QtWidgets

from histalign.frontend.common_widgets import BasicMenuBar, HistalignMainWindow
from histalign.frontend.dialogs import OpenProjectDialog
from histalign.frontend.quantification.prepare import PrepareWidget
from histalign.frontend.quantification.results import ResultsWidget
from histalign.frontend.quantification.view import ViewWidget


class QuantificationMainWindow(HistalignMainWindow):
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

        self.view_tab = view_tab

        #
        tab_widget = QtWidgets.QTabWidget()
        tab_widget.addTab(prepare_tab, "Prepare")
        tab_widget.addTab(results_tab, "Results")
        tab_widget.addTab(view_tab, "View")
        tab_widget.setEnabled(False)

        #
        self.setCentralWidget(tab_widget)
        self.tab_widget = tab_widget

    @QtCore.Slot()
    def open_project(self, project_file_path: str) -> None:
        project_directory = Path(project_file_path).parent

        self.prepare_tab.parse_project(project_directory)
        self.results_tab.parse_project(project_directory)

        self.tab_widget.setEnabled(True)
        self.project_loaded = True
