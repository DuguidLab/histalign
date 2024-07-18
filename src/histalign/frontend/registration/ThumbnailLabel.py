# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierDelrée@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class ThumbnailLabel(QtWidgets.QLabel):
    index: int
    thumbnail: Optional[QtGui.QPixmap]

    def __init__(self, index: int, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.index = index
        self.thumbnail = None

    def setPixmap(self, pixmap: QtGui.QPixmap) -> None:
        if self.thumbnail is None:
            self.thumbnail = pixmap
            pixmap = pixmap.scaled(pixmap.width() // 2, pixmap.height() // 2)
        super().setPixmap(pixmap)

    def heightForWidth(self, width: int) -> int:
        if self.thumbnail is None:
            return -1

        return round(width * (self.thumbnail.height() / self.thumbnail.width()))

    def resize(self, width: int) -> None:
        height = self.heightForWidth(width)
        if self.thumbnail is not None:
            self.setPixmap(self.thumbnail.scaled(width, height))

        self.setFixedSize(width, height)
