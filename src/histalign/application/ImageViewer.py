# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtGui, QtWidgets


class ImageViewer(QtWidgets.QWidget):
    scene: QtWidgets.QGraphicsScene
    view: QtWidgets.QGraphicsView

    pixmap: QtWidgets.QGraphicsPixmapItem

    def __init__(
        self, image_file_path: str, parent: typing.Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)

        self.scene = QtWidgets.QGraphicsScene()
        self.load_pixmap(image_file_path)

        self.view = QtWidgets.QGraphicsView(self.scene)
        self.view.setGeometry(
            0, 0, self.pixmap.pixmap().width(), self.pixmap.pixmap().height()
        )
        self.view.setSceneRect(
            0, 0, self.pixmap.pixmap().width(), self.pixmap.pixmap().height()
        )
        self.view.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 255)))

        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(QtCore.Qt.AlignCenter)

        layout.addWidget(self.view)

        self.setLayout(layout)

    def load_pixmap(self, file_path) -> None:
        image = QtGui.QImage()
        image.load(file_path)
        self.pixmap = self.scene.addPixmap(QtGui.QPixmap.fromImage(image))

    @QtCore.Slot()
    def transform_pixmap(self, settings: dict) -> None:
        try:
            angle = settings["dv_angle"]
            x_translation = settings["x_translation"]
            y_translation = settings["y_translation"]
            x_scale = settings["x_scale"]
            y_scale = settings["y_scale"]
            x_shear = settings["x_shear"]
            y_shear = settings["y_shear"]
        except KeyError:
            return

        # Scaling variables
        initial_width = self.pixmap.pixmap().width()
        initial_height = self.pixmap.pixmap().height()
        effective_width = x_scale * initial_width
        effective_height = y_scale * initial_height

        # Shearing variables
        x_displacement = x_shear * effective_height
        y_displacement = y_shear * effective_width

        transform = (
            QtGui.QTransform()
            .translate(  # Regular translation
                x_translation,
                y_translation,
            )
            .translate(  # Translation so that rotation happens around center
                initial_width / 2,
                initial_height / 2,
            )
            .rotate(  # Regular rotation
                angle,
            )
            .translate(  # Translation to get back to normal
                -initial_width / 2,
                -initial_height / 2,
            )
            .translate(  # Translation to make scaling "happen around center"
                -(effective_width - initial_width) / 2,
                -(effective_height - initial_height) / 2,
            )
            .scale(  # Regular scaling
                x_scale,
                y_scale,
            )
            .translate(  # Translation to make shearing "happen around center"
                -x_displacement / 2,
                -y_displacement / 2,
            )
            .shear(  # Regular shearing
                x_shear,
                y_shear,
            )
        )
        self.pixmap.setTransform(transform)
