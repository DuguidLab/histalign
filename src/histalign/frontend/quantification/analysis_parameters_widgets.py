# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT
from abc import abstractmethod

from PySide6 import QtWidgets

from histalign.backend.models import (
    AverageFluorescenceMeasureSettings,
    CorticalDepthMeasureSettings,
    MeasureSettings,
)
from histalign.frontend.pyside_helpers import FakeQtABC


class AnalysisParametersWidget(QtWidgets.QWidget, FakeQtABC):
    """A widget containing different widgets relevant to its analysis pipeline.

    Attributes:
        includes_structures (bool):
            Whether this pipeline requires a structures finder widget to be active.
    """

    def __init__(
        self,
        includes_structures: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.includes_structures = includes_structures

    @property
    @abstractmethod
    def settings(self) -> MeasureSettings:
        pass

    def get_column_width(self) -> int:
        """Returns the minimum required column width for its labels.

        Returns:
            int: The column width.
        """
        width = 0
        for i in range(self.layout().rowCount()):
            widget = self.layout().itemAtPosition(i, 0).widget()
            if isinstance(widget, QtWidgets.QLabel):
                width = max(width, widget.sizeHint().width())

        return width


class AverageFluorescenceAnalysisParametersWidget(AnalysisParametersWidget):
    """An average fluorescence analysis parameters widget.

    This widget provides the user with a combo box to select the scale (whole-brain or
    per-slice) on which to carry out the analysis.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent=parent)

        #
        scale_widget = QtWidgets.QComboBox()

        scale_widget.addItems(["Whole-brain", "Per-slice"])

        self.scale_widget = scale_widget

        #
        layout = QtWidgets.QGridLayout()

        layout.addWidget(QtWidgets.QLabel("Scale"), 0, 0)
        layout.addWidget(scale_widget, 0, 1)

        self.setLayout(layout)

    @property
    def settings(self) -> MeasureSettings:
        return AverageFluorescenceMeasureSettings(
            approach=self.scale_widget.currentText(),
            structures=[],
        )


class CorticalDepthAnalysisParametersWidget(AnalysisParametersWidget):
    """A cortical depth analysis parameters widget.

    This widget provides the user with a combo box to select the cortical plate
    structure from which to determine the cortical depth.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent=parent)

        #
        cortex_structure_combo_box = QtWidgets.QComboBox()

        cortex_structure_combo_box.addItems(
            ["Isocortex", "Olfactory areas", "Hippocampal formation"]
        )

        self.cortex_structure_combo_box = cortex_structure_combo_box

        #
        layout = QtWidgets.QGridLayout()

        layout.addWidget(QtWidgets.QLabel("Cortical plate structure"), 0, 0)
        layout.addWidget(cortex_structure_combo_box, 0, 1)

        self.setLayout(layout)

    @property
    def settings(self) -> MeasureSettings:
        return CorticalDepthMeasureSettings(
            cortex_structure=self.cortex_structure_combo_box.currentText(),
            structures=[],
        )
