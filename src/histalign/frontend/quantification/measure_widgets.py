# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT


from typing import Optional

from PySide6 import QtWidgets

from histalign.backend.models import (
    AverageFluorescenceMeasureSettings,
    CorticalDepthMeasureSettings,
)
from histalign.frontend.common_widgets import (
    AnimatedHeightWidget,
    SelectedStructuresWidget,
)


class AverageFluorescenceWidget(AnimatedHeightWidget):
    approach_widget = QtWidgets.QComboBox
    structures_widget = SelectedStructuresWidget

    def __init__(
        self,
        animated: bool = True,
        duration: int = 200,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(animated, duration, parent)

        #
        approach_widget = QtWidgets.QComboBox()

        approach_widget.addItems(["Whole-brain", "Per-slice"])

        self.approach_widget = approach_widget

        #
        structures_widget = SelectedStructuresWidget()

        self.structures_widget = structures_widget

        #
        layout = QtWidgets.QFormLayout()

        layout.addRow("Approach", approach_widget)
        layout.addRow("Structures", structures_widget)

        self.setLayout(layout)

    @property
    def settings(self) -> AverageFluorescenceMeasureSettings:
        return AverageFluorescenceMeasureSettings(
            approach=self.approach_widget.currentText(),
            structures=list(self.structures_widget.structure_tags_mapping.keys()),
        )


class CorticalDepthWidget(AnimatedHeightWidget):
    def __init__(
        self,
        animated: bool = True,
        duration: int = 200,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(animated, duration, parent)

        #
        cortex_structure_widget = SelectedStructuresWidget()

        self.cortex_structure_widget = cortex_structure_widget

        #
        sub_cortical_structures_widget = SelectedStructuresWidget()

        self.sub_cortical_structures_widget = sub_cortical_structures_widget

        #
        layout = QtWidgets.QFormLayout()

        layout.addRow("Cortex structure", cortex_structure_widget)
        layout.addRow("Sub-cortical structures", sub_cortical_structures_widget)

        self.setLayout(layout)

    @property
    def settings(self) -> CorticalDepthMeasureSettings:
        # TODO: Enforce only allowing a single checked structure for this widget.
        cortex_structure = list(
            self.cortex_structure_widget.structure_tags_mapping.keys()
        )
        if cortex_structure:
            cortex_structure = cortex_structure[0]
        else:
            cortex_structure = ""

        return CorticalDepthMeasureSettings(
            cortex_structure=cortex_structure,
            sub_cortical_structures=list(
                self.sub_cortical_structures_widget.structure_tags_mapping.keys()
            ),
        )
