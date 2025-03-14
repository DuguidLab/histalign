# SPDX-FileCopyrightText: 2025-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from PySide6 import QtWidgets


class InformationWidget(QtWidgets.QTabWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        #
        tab1 = StructuresWidget()

        self.structures_widget = tab1

        #
        tab2 = QtWidgets.QWidget()

        self.tab2 = tab2

        #
        tab3 = QtWidgets.QWidget()

        self.tab3 = tab3

        #
        self.addTab(tab1, "Structures")
        self.addTab(tab2, "PLACEHOLDER")
        self.addTab(tab3, "PLACEHOLDER")


class StructuresWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
