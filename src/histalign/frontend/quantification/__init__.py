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


class MainMenuBar(QtWidgets.QMenuBar):
    open_project_requested: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        file_menu = self.addMenu("&File")

        open_project_action = QtGui.QAction("Open p&roject", self)
        open_project_action.triggered.connect(self.open_project_requested.emit)

        file_menu.addAction(open_project_action)


class ResultsWidget(QtWidgets.QFrame):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        layout = QtWidgets.QFormLayout()
        layout.addRow("Date:", QtWidgets.QLabel("01/01/1970"))
        layout.addRow("Directory:", QtWidgets.QLabel("/home/etc/project1"))
        layout.addRow("Measure:", QtWidgets.QLabel("Average fluorescence"))
        layout.addRow(
            "Structures:", QtWidgets.QLabel("primary motor cortex, hypothalamus")
        )

        #
        self.setLayout(layout)

        #
        self.setFrameStyle(QtWidgets.QFrame.Shape.StyledPanel)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed
        )
        self.setAutoFillBackground(True)


class QuantificationMainWindow(QtWidgets.QMainWindow):
    project_directory: str

    menu_bar: MainMenuBar
    tab_widget: QtWidgets.QWidget

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
        results_layout = QtWidgets.QGridLayout()
        for i in range(10):
            for j in range(5):
                if i == 0 and j == 0:
                    widget = ResultsWidget()
                    widget.layout().addRow(
                        "", QtWidgets.QLabel("isocortex, root, cerebrum")
                    )
                    widget.layout().addRow(
                        "", QtWidgets.QLabel("isocortex, root, cerebrum")
                    )
                    results_layout.addWidget(
                        widget, i, j, alignment=QtCore.Qt.AlignmentFlag.AlignTop
                    )
                else:
                    results_layout.addWidget(
                        ResultsWidget(),
                        i,
                        j,
                        alignment=QtCore.Qt.AlignmentFlag.AlignTop,
                    )

        results_widget = QtWidgets.QWidget()
        results_widget.setLayout(results_layout)

        #
        view_placeholder_widget = QtWidgets.QLabel("PLACEHOLDER")

        view_layout = QtWidgets.QVBoxLayout()
        view_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        view_layout.addWidget(view_placeholder_widget)

        view_widget = QtWidgets.QWidget()
        view_widget.setLayout(view_layout)

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

    def show_open_project_dialog(self) -> None:
        dialog = OpenProjectDialog(self)
        dialog.submitted.connect(self.open_project)
        dialog.open()

    @QtCore.Slot()
    def open_project(self, project_path: str) -> None:
        self.project_directory = str(Path(project_path).parent)

        self.prepare_widget.parse_project(project_path)

        self.tab_widget.setEnabled(True)


if __name__ == "__main__":
    app = QtWidgets.QApplication()
    # app.setStyleSheet("* { border: 1px solid blue; }")

    window = QuantificationMainWindow()
    window.resize(1920, 1080)
    window.show()

    sys.exit(app.exec())
