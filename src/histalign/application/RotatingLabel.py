# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtGui, QtWidgets


class RotatingLabel(QtWidgets.QLabel):
    image: QtGui.QImage

    def __init__(
        self, parent: typing.Optional[QtWidgets.QWidget] = None, **kwargs
    ) -> None:
        super().__init__(parent, **kwargs)

    @QtCore.Slot()
    def rotate_image(self, settings: dict) -> None:
        angle = settings.get("dv_angle")
        if angle is None:
            return
        if not isinstance(self.image, QtGui.QImage):
            return
        self.setPixmap(
            QtGui.QPixmap.fromImage(
                self.image.transformed(
                    QtGui.QTransform().rotate(float(angle), QtCore.Qt.ZAxis, 0)
                )
            )
        )
