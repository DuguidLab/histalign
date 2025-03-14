# SPDX-FileCopyrightText: 2025-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from PySide6 import QtWidgets

from histalign.backend.io import RESOURCES_ROOT
from histalign.frontend.common_widgets import HoverButton


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

        #
        dimension_picker_widget = DimensionPickerWidget()

        self.dimension_picker_widget = dimension_picker_widget

        #
        layout = QtWidgets.QHBoxLayout()

        layout.addWidget(dimension_picker_widget)

        self.setLayout(layout)


class DimensionPickerWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        #
        button_2d = HoverButton(
            icon_path=RESOURCES_ROOT / "icons" / "2d-label-icon.svg"
        )

        button_2d.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        self.button_2d = button_2d

        #
        button_3d = HoverButton(
            icon_path=RESOURCES_ROOT / "icons" / "3d-label-icon.svg"
        )

        button_3d.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        self.button_3d = button_3d

        #
        layout = QtWidgets.QVBoxLayout()

        layout.addWidget(button_2d)
        layout.addWidget(button_3d)

        self.setLayout(layout)


class FoldersWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)


class BrainsWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)


class BrainsHeader(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
