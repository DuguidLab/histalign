# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.frontend.registration.helpers import get_dummy_title_bar


class AlignmentButtonDockWidget(QtWidgets.QDockWidget):
    save_button: QtWidgets.QPushButton
    load_button: QtWidgets.QPushButton
    reset_volume: QtWidgets.QPushButton
    reset_histology: QtWidgets.QPushButton

    def __init__(
        self,
        parent: typing.Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.setContentsMargins(10, 0, 10, 10)

        self.setTitleBarWidget(get_dummy_title_bar(self))
        self.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)

        self.save_button = QtWidgets.QPushButton("Save")
        self.load_button = QtWidgets.QPushButton("Load")

        self.reset_volume = QtWidgets.QPushButton("Reset atlas")
        self.reset_histology = QtWidgets.QPushButton("Reset histology")

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.save_button)
        layout.addWidget(self.load_button)
        layout.addWidget(self.reset_volume)
        layout.addWidget(self.reset_histology)

        container_widget = QtWidgets.QWidget()
        container_widget.setLayout(layout)

        self.setWidget(container_widget)
