# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.frontend.common_widgets import BasicApplicationWindow
from histalign.frontend.dialogs import OpenProjectDialog
from histalign.frontend.preprocessing.prepare import PrepareWidget
from histalign.frontend.preprocessing.results import ResultsWidget


class PreprocessingMainWindow(BasicApplicationWindow):
    project_directory: Path

    project_loaded: bool = False

    tab_widget: QtWidgets.QTabWidget
    prepare_widget: PrepareWidget
    results_widget: ResultsWidget

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        prepare_widget = PrepareWidget()

        self.prepare_widget = prepare_widget

        #
        results_widget = ResultsWidget()

        self.results_widget = results_widget

        #
        tab_widget = QtWidgets.QTabWidget()
        tab_widget.setEnabled(False)

        tab_widget.addTab(prepare_widget, "Prepare")
        tab_widget.addTab(results_widget, "Results")

        self.tab_widget = tab_widget

        #
        container_layout = QtWidgets.QHBoxLayout()
        container_layout.setContentsMargins(0, 10, 0, 0)
        container_layout.addWidget(tab_widget)

        container_widget = QtWidgets.QWidget()
        container_widget.setLayout(container_layout)

        self.setCentralWidget(container_widget)

    @QtCore.Slot()
    def open_project(self, project_file_path: str) -> None:
        self.project_directory = Path(project_file_path).parent

        self.prepare_widget.parse_project(self.project_directory)
        # self.results_widget.parse_project(project_path)

        self.tab_widget.setEnabled(True)

        self.project_loaded = True
