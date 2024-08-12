# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import json
from typing import Optional

import cv2
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

import histalign.backend.io as io
from histalign.backend.models.AlignmentParameterAggregator import (
    AlignmentParameterAggregator,
)
from histalign.backend.registration.ReverseRegistrator import ReverseRegistrator


class QAViewerWidget(QtWidgets.QLabel):
    is_registered: bool = False
    registration_result: Optional[AlignmentParameterAggregator] = None
    contours_map: dict[str, np.ndarray]

    reverse_registrator: ReverseRegistrator

    histology_pixmap: QtGui.QPixmap
    histology_array: np.ndarray

    contour_mask_generated: QtCore.Signal = QtCore.Signal(str, np.ndarray)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.contours_map = {}

        self.reverse_registrator = ReverseRegistrator(True, True, "nearest")

        self.histology_pixmap = QtGui.QPixmap()
        self.histology_array = np.ndarray(shape=(0, 0))

    def load_histology(self, file_path: str, result_path: Optional[str] = None) -> None:
        self.clear()

        self.histology_array = io.load_image(file_path, normalise_dtype=np.uint8)
        match self.histology_array.dtype:
            case np.uint8:
                image_format = QtGui.QImage.Format.Format_Grayscale8
            case np.uint16:
                image_format = QtGui.QImage.Format.Format_Grayscale16
            case other:
                raise ValueError(f"Unknown image type '{other}'.")

        self.histology_pixmap = QtGui.QPixmap.fromImage(
            QtGui.QImage(
                self.histology_array.tobytes(),
                self.histology_array.shape[1],
                self.histology_array.shape[0],
                self.histology_array.shape[1],
                image_format,
            )
        )

        if result_path is not None:
            self.is_registered = True
            with open(result_path) as handle:
                self.registration_result = AlignmentParameterAggregator(
                    **json.load(handle)
                )

        # Recompute contours when changing slices
        structure_names = self.contours_map.keys()
        self.contours_map = {}
        for structure_name in structure_names:
            self.add_contour(structure_name)

        self.update_merged_pixmap()

    def update_merged_pixmap(self) -> None:
        if self.histology_pixmap.isNull():
            return
        if not self.is_registered:
            self.setPixmap(
                self.histology_pixmap.scaled(self.size(), QtCore.Qt.KeepAspectRatio)
            )
            return

        pixmap = self.histology_pixmap.copy()

        painter = QtGui.QPainter(pixmap)
        painter.setPen(QtGui.QPen(QtCore.Qt.white, 10))
        for point_coordinates in self.contours_map.values():
            for i in range(point_coordinates.shape[0]):
                painter.drawPoint(point_coordinates[i, 0], point_coordinates[i, 1])
        painter.end()

        self.setPixmap(
            pixmap.scaled(
                self.size(),
                QtCore.Qt.KeepAspectRatio,
                mode=QtCore.Qt.SmoothTransformation,
            )
        )

    def clear(self) -> None:
        self.registration_result = None
        self.is_registered = False
        self.histology_pixmap = QtGui.QPixmap()
        self.setPixmap(self.histology_pixmap)
        self.histology_array = np.ndarray(shape=(0, 0))

    @QtCore.Slot()
    def add_contour(self, structure_name: str) -> None:
        if not self.is_registered:
            print("Image not registered. Skipping adding contour.")
            return

        structure_slice = self.reverse_registrator.get_reversed_image(
            self.registration_result, volume_name=structure_name
        )
        self.contour_mask_generated.emit(structure_name, structure_slice)
        contours = cv2.findContours(
            structure_slice, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE
        )[0]

        if contours:
            self.contours_map[structure_name] = np.concatenate(contours).squeeze()
            self.update_merged_pixmap()

    @QtCore.Slot()
    def remove_contour(self, structure_name: str) -> None:
        self.contours_map.pop(structure_name, None)

        self.update_merged_pixmap()
