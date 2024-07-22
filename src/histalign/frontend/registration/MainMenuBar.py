# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierDelrée@protonmail.com>
#
# SPDX-License-Identifier: MIT

import os
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class MainMenuBar(QtWidgets.QMenuBar):
    action_groups: dict[str, list[QtGui.QAction]]

    create_project_requested: QtCore.Signal = QtCore.Signal()
    open_project_requested: QtCore.Signal = QtCore.Signal(str)
    open_image_directory_requested: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.action_groups = {"none": [], "project_required": []}

        file_menu = self.addMenu("&File")

        create_project_action = QtGui.QAction("Create &project", self)
        create_project_action.triggered.connect(self.create_project_requested.emit)
        self.action_groups["none"].append(create_project_action)

        open_project_action = QtGui.QAction("Open p&roject", self)
        open_project_action.triggered.connect(self.show_project_picker)
        self.action_groups["none"].append(open_project_action)

        open_image_directory_action = QtGui.QAction("&Open image directory", self)
        open_image_directory_action.setEnabled(False)
        open_image_directory_action.setShortcut(QtGui.QKeySequence("Ctrl+o"))
        open_image_directory_action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        open_image_directory_action.triggered.connect(self.show_image_directory_picker)
        self.action_groups["project_required"].append(open_image_directory_action)

        file_menu.addAction(create_project_action)
        file_menu.addAction(open_project_action)
        file_menu.addSeparator()
        file_menu.addAction(open_image_directory_action)

    def opened_project(self) -> None:
        for action in self.action_groups["project_required"]:
            action.setEnabled(True)

    @QtCore.Slot()
    def show_project_picker(self) -> None:
        project_file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select a project file",
            os.getcwd(),
            "Project (project.json)",
            options=QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )

        if project_file != "":
            self.open_project_requested.emit(project_file)

    @QtCore.Slot()
    def show_image_directory_picker(self) -> None:
        image_directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select an image directory",
            os.getcwd(),
            options=QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )

        if image_directory != "":
            self.open_image_directory_requested.emit(image_directory)
