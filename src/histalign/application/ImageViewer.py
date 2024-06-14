# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtGui, QtWidgets


class ImageViewer(QtWidgets.QLabel):
    image: QtGui.QImage

    def __init__(
        self, parent: typing.Optional[QtWidgets.QWidget] = None, **kwargs
    ) -> None:
        super().__init__(parent, **kwargs)

    @QtCore.Slot()
    def transform_image(self, settings: dict) -> None:
        try:
            angle = settings["dv_angle"]
            x_translation = settings["x_translation"]
            y_translation = settings["y_translation"]
        except KeyError:
            return

        if not isinstance(self.image, QtGui.QImage):
            return

        transformed_image = self.image.transformed(
            QtGui.QTransform().rotate(float(angle), QtCore.Qt.ZAxis, 0)
        )
        transformed_image = transformed_image.transformed(
            QtGui.QTransform().translate(float(x_translation), float(y_translation))
        )

        self.setPixmap(QtGui.QPixmap.fromImage(transformed_image))
