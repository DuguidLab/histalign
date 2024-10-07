# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from pathlib import Path
import sys
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.frontend.common_widgets import ProjectDirectoriesComboBox
from histalign.frontend.dialogs import OpenProjectDialog
from histalign.frontend.quantification.prepare import PrepareWidget
from histalign.frontend.quantification.results import ResultsWidgets
from histalign.frontend.quantification.view import ViewWidget


class MainMenuBar(QtWidgets.QMenuBar):
    open_project_requested: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        file_menu = self.addMenu("&File")

        open_project_action = QtGui.QAction("Open p&roject", self)
        open_project_action.triggered.connect(self.open_project_requested.emit)

        file_menu.addAction(open_project_action)


class QuantificationMainWindow(QtWidgets.QMainWindow):
    project_directory: Path

    project_loaded: bool = False

    menu_bar: MainMenuBar
    tab_widget: QtWidgets.QWidget
    prepare_widget: PrepareWidget
    results_widget: ResultsWidgets
    view_widget: ViewWidget

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        menu_bar = MainMenuBar()
        menu_bar.open_project_requested.connect(self.show_open_project_dialog)

        self.setMenuBar(menu_bar)

        self.menu_bar = menu_bar

        #
        prepare_widget = PrepareWidget()

        self.prepare_widget = prepare_widget

        #
        results_widget = ResultsWidgets()
        results_widget.submitted.connect(self.display_summaries)

        self.results_widget = results_widget

        #
        view_widget = ViewWidget()

        self.view_widget = view_widget

        #
        tab_widget = QtWidgets.QTabWidget()
        tab_widget.setEnabled(False)

        tab_widget.addTab(prepare_widget, "Prepare")
        tab_widget.addTab(results_widget, "Results")
        tab_widget.addTab(view_widget, "View")

        #
        # Wrap tab_widget to enable padding of central widget
        container_layout = QtWidgets.QHBoxLayout()
        container_layout.setContentsMargins(0, 10, 0, 0)
        container_layout.addWidget(tab_widget)

        container_widget = QtWidgets.QWidget()
        container_widget.setLayout(container_layout)

        self.setCentralWidget(container_widget)

        self.tab_widget = tab_widget

    def display_summaries(self) -> None:
        results_list = []
        for i in range(self.results_widget.model.rowCount()):
            index = self.results_widget.model.index(i, 0)
            if (
                index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
                == QtCore.Qt.CheckState.Checked
            ):
                results_list.append(index.data(QtCore.Qt.ItemDataRole.UserRole))

        self.view_widget.parse_results(results_list)

    @QtCore.Slot()
    def show_open_project_dialog(self) -> None:
        dialog = OpenProjectDialog(self)
        dialog.submitted.connect(self.open_project)
        dialog.open()

    @QtCore.Slot()
    def open_project(self, project_file_path: str) -> None:
        self.project_directory = Path(project_file_path).parent

        self.prepare_widget.parse_project(self.project_directory)
        self.results_widget.parse_project(self.project_directory)

        self.tab_widget.setEnabled(True)

        self.project_loaded = True
