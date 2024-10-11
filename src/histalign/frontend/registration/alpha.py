# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.frontend.registration.helpers import get_dummy_title_bar


class AlphaDockWidget(QtWidgets.QDockWidget):
    global_alpha_button: QtWidgets.QPushButton
    global_alpha_slider: QtWidgets.QSlider

    def __init__(
        self,
        parent: typing.Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        #
        self.setContentsMargins(10, 10, 10, 0)

        self.setTitleBarWidget(get_dummy_title_bar(self))
        self.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)

        #
        global_alpha_button = QtWidgets.QPushButton("X")
        global_alpha_button.setMaximumWidth(20)
        global_alpha_button.clicked.connect(self.toggle_alpha)

        self.global_alpha_button = global_alpha_button

        #
        global_alpha_slider = QtWidgets.QSlider(
            orientation=QtCore.Qt.Horizontal, minimum=0, maximum=255, value=255
        )

        self.global_alpha_slider = global_alpha_slider

        #
        global_layout = QtWidgets.QHBoxLayout()
        global_layout.addWidget(
            self.global_alpha_button, alignment=QtCore.Qt.AlignVCenter
        )
        global_layout.addWidget(
            self.global_alpha_slider, alignment=QtCore.Qt.AlignVCenter
        )

        #
        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(global_layout)

        #
        container_widget = QtWidgets.QWidget()
        container_widget.setLayout(layout)

        self.setWidget(container_widget)

    @QtCore.Slot()
    def toggle_alpha(self) -> None:
        value = self.global_alpha_slider.value()
        toggled_value = 255 - value
        if toggled_value > 255 // 2:
            self.global_alpha_slider.setValue(255)
        else:
            self.global_alpha_slider.setValue(0)
