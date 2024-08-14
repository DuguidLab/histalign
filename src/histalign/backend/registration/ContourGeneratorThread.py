# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from typing import Optional

import cv2
import numpy as np
from PySide6 import QtCore

from histalign.backend.models.AlignmentParameterAggregator import (
    AlignmentParameterAggregator,
)
from histalign.backend.registration.ReverseRegistrator import ReverseRegistrator


class ContourGeneratorThread(QtCore.QThread):
    """Thread class for handling contour generation for the QA GUI.

    Since instances are throwaways, they can use their own ReverseRegistrator as we
    don't need to optimise keeping the loaded volume into memory.

    Attributes:
        should_emit (bool): Whether the thread should report its results or drop them.
                            It should drop them if its processing took too long and its
                            work is no longer required by the GUI (e.g., the contour
                            was removed from the list of selected contours before the
                            thread returned).

    Signals:
        mask_ready (np.ndarray): Emits the structure mask after reverse registration.
        contours_ready (np.ndarray): Emits the contour(s) of the mask as a single numpy
                                     array of shape (N, 2), representing N points' I and
                                     J coordinates (i.e., matrix coordinates). This
                                     array can be empty if no contour was found.
    """

    should_emit: bool = True

    mask_ready: QtCore.Signal = QtCore.Signal(np.ndarray)
    contours_ready: QtCore.Signal = QtCore.Signal(np.ndarray)

    def __init__(
        self,
        structure_name: str,
        registration_parameters: AlignmentParameterAggregator,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)

        self.structure_name = structure_name
        self.registration_parameters = registration_parameters

    def run(self) -> None:
        registrator = ReverseRegistrator(True, True)

        try:
            structure_mask = registrator.get_reversed_image(
                self.registration_parameters, volume_name=self.structure_name
            )
        except FileNotFoundError:
            self.logger.error(
                f"Could not find structure file ('{self.structure_name}')."
            )
            return

        contours = cv2.findContours(
            structure_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE
        )[0]

        if contours:
            contours = np.concatenate(contours).squeeze()
        else:
            contours = np.array([])

        if self.should_emit:
            self.mask_ready.emit(structure_mask)
            self.contours_ready.emit(contours)
