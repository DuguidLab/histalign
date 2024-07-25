# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import os
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class MainMenuBar(QtWidgets.QMenuBar):
    action_groups: dict[str, list[QtGui.QAction]]

    create_project_requested: QtCore.Signal = QtCore.Signal()
    open_project_requested: QtCore.Signal = QtCore.Signal()
    save_project_requested: QtCore.Signal = QtCore.Signal()
    close_project_requested: QtCore.Signal = QtCore.Signal()
    change_atlas_requested: QtCore.Signal = QtCore.Signal()
    open_image_directory_requested: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.action_groups = {"none": [], "project_required": []}

        file_menu = self.addMenu("&File")

        create_project_action = QtGui.QAction("Create &project", self)
        create_project_action.triggered.connect(self.create_project_requested.emit)
        self.action_groups["none"].append(create_project_action)

        open_project_action = QtGui.QAction("Open p&roject", self)
        open_project_action.triggered.connect(self.open_project_requested.emit)
        self.action_groups["none"].append(open_project_action)

        save_project_action = QtGui.QAction("&Save project", self)
        save_project_action.setEnabled(False)
        save_project_action.setShortcut(QtGui.QKeySequence("Ctrl+s"))
        save_project_action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        save_project_action.triggered.connect(self.save_project_requested.emit)
        self.action_groups["project_required"].append(save_project_action)

        close_project_action = QtGui.QAction("Close pro&ject", self)
        close_project_action.setEnabled(False)
        close_project_action.triggered.connect(self.close_project_requested.emit)
        self.action_groups["project_required"].append(close_project_action)

        change_atlas_action = QtGui.QAction("Change &atlas resolution", self)
        change_atlas_action.setEnabled(False)
        change_atlas_action.triggered.connect(self.change_atlas_requested.emit)
        self.action_groups["project_required"].append(change_atlas_action)

        open_image_directory_action = QtGui.QAction("&Open image directory", self)
        open_image_directory_action.setEnabled(False)
        open_image_directory_action.setShortcut(QtGui.QKeySequence("Ctrl+o"))
        open_image_directory_action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        open_image_directory_action.triggered.connect(
            self.open_image_directory_requested.emit
        )
        self.action_groups["project_required"].append(open_image_directory_action)

        file_menu.addAction(create_project_action)
        file_menu.addAction(open_project_action)
        file_menu.addAction(save_project_action)
        file_menu.addAction(close_project_action)
        file_menu.addSeparator()
        file_menu.addAction(change_atlas_action)
        file_menu.addSeparator()
        file_menu.addAction(open_image_directory_action)

    def opened_project(self) -> None:
        for action in self.action_groups["project_required"]:
            action.setEnabled(True)

    def closed_project(self) -> None:
        for action in self.action_groups["project_required"]:
            action.setEnabled(False)
