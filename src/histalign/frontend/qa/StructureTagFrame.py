# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT


from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class StructureTagFrame(QtWidgets.QFrame):
    removal_requested: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        text: str,
        font_pixel_size: int = 12,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        button = QtWidgets.QPushButton("X")
        button.setFixedSize(font_pixel_size, font_pixel_size)
        font = QtGui.QFont()
        font.setPixelSize(font_pixel_size - 3)
        button.setFont(font)
        button.setFlat(True)
        button.clicked.connect(self.removal_requested)

        label = QtWidgets.QLabel(text)
        font = QtGui.QFont()
        font.setPixelSize(font_pixel_size)
        label.setFont(font)
        label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)

        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)

        layout.addWidget(button)
        layout.addWidget(label)

        self.setLayout(layout)

        self.removal_requested.connect(self.deleteLater)

        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
