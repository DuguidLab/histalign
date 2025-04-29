# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.frontend.common_widgets import CircularPushButton, DynamicThemeIcon
from histalign.resources import ICONS_ROOT


class AlphaWidget(QtWidgets.QWidget):
    global_alpha_button: QtWidgets.QPushButton
    global_alpha_slider: QtWidgets.QSlider

    def __init__(
        self,
        orientation: QtCore.Qt.Orientation = QtCore.Qt.Orientation.Vertical,
        parent: typing.Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        #
        global_alpha_button = CircularPushButton()

        if orientation == QtCore.Qt.Orientation.Vertical:
            global_alpha_button.setMaximumHeight(20)
        global_alpha_button.setMaximumWidth(20)
        global_alpha_button.setIcon(
            DynamicThemeIcon(ICONS_ROOT / "color-contrast-icon.png")
        )
        global_alpha_button.setToolTip("Toggle general transparency of current image.")
        global_alpha_button.setStatusTip(
            "Toggle general transparency of current image."
        )
        global_alpha_button.setShortcut(QtGui.QKeySequence("Ctrl+t"))

        global_alpha_button.clicked.connect(self.toggle_global_alpha)

        self.global_alpha_button = global_alpha_button

        #
        global_alpha_slider = QtWidgets.QSlider(
            orientation=orientation, minimum=0, maximum=255, value=255
        )

        global_alpha_slider.setToolTip("General image transparency slider.")
        global_alpha_slider.setStatusTip("General image transparency slider.")

        self.global_alpha_slider = global_alpha_slider

        #
        layout: QtWidgets.QLayout
        if orientation == QtCore.Qt.Orientation.Vertical:
            layout = QtWidgets.QVBoxLayout()
        else:
            layout = QtWidgets.QHBoxLayout()

        layout.setContentsMargins(0, 0, 0, 0)

        alignment = (
            QtCore.Qt.AlignmentFlag.AlignHCenter
            if orientation == QtCore.Qt.Orientation.Vertical
            else QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(global_alpha_button, alignment=alignment)
        layout.addWidget(global_alpha_slider, alignment=alignment)

        self.setLayout(layout)

    @QtCore.Slot()
    def toggle_global_alpha(self) -> None:
        value = self.global_alpha_slider.value()
        toggled_value = 255 - value
        if toggled_value > 255 // 2:
            self.global_alpha_slider.setValue(255)
        else:
            self.global_alpha_slider.setValue(0)
