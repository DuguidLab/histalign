# SPDX-FileCopyrightText: 2025-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from PySide6 import QtWidgets


class NavigationWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        #
        header = NavigationHeader()

        self.header = header

        #
        area = NavigationArea()

        self.area = area

        #
        layout = QtWidgets.QVBoxLayout()

        layout.addWidget(header)
        layout.addWidget(area)

        self.setLayout(layout)


class NavigationHeader(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)


class NavigationArea(QtWidgets.QScrollArea):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)


class DimensionPickerWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)


class FoldersWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)


class BrainsWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)


class BrainsHeader(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
