# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class MainMenuBar(QtWidgets.QMenuBar):
    open_results_directory_requested: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        file_menu = self.addMenu("&File")

        open_results_directory = QtGui.QAction("&Open results directory", self)
        open_results_directory.triggered.connect(
            self.open_results_directory_requested.emit
        )

        file_menu.addAction(open_results_directory)
