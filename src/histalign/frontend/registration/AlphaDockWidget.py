# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtGui, QtWidgets


class AlphaDockWidget(QtWidgets.QDockWidget):
    alpha_toggle_push_button: QtWidgets.QPushButton
    alpha_slider: QtWidgets.QSlider

    def __init__(
        self,
        parent: typing.Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)

        self.alpha_toggle_push_button = QtWidgets.QPushButton("X")
        self.alpha_toggle_push_button.setMaximumWidth(20)
        self.alpha_toggle_push_button.clicked.connect(self.toggle_alpha)

        self.alpha_slider = QtWidgets.QSlider(
            orientation=QtCore.Qt.Horizontal, minimum=0, maximum=255, value=255
        )

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(
            self.alpha_toggle_push_button, alignment=QtCore.Qt.AlignVCenter
        )
        layout.addWidget(self.alpha_slider, alignment=QtCore.Qt.AlignVCenter)

        container_widget = QtWidgets.QWidget()
        container_widget.setLayout(layout)

        self.setWidget(container_widget)

    @QtCore.Slot()
    def toggle_alpha(self) -> None:
        value = self.alpha_slider.value()
        toggled_value = 255 - value
        if toggled_value > 255 // 2:
            self.alpha_slider.setValue(255)
        else:
            self.alpha_slider.setValue(0)
