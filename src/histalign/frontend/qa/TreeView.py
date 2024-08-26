# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class TreeView(QtWidgets.QTreeView):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setHeaderHidden(True)
        self.setStyleSheet(
            f"""
            QTreeView {{
                padding-top: 15px;
                padding-bottom: 15px;
                background-color: {self.palette().color(QtGui.QPalette.Base).name()};
            }}
            """
        )
