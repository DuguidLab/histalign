# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class PopUpTreeView(QtWidgets.QTreeView):
    focus_lost: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)

        self.setHeaderHidden(True)

        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint)

        self.setStyleSheet(
            f"""
            QTreeView {{
                padding-top: 15px;
                padding-bottom: 15px;
                background-color: {self.palette().color(QtGui.QPalette.Base).name()};
            }}
            """
        )
