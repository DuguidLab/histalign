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
        cortex_structure_combo_box = QtWidgets.QComboBox()

        # TODO: Might be worth getting them programmatically from a
        #       `SelectedStructuresWidget`.
        cortex_structure_combo_box.addItems(
            ["Isocortex", "Olfactory areas", "Hippocampal formation"]
        )

        self.cortex_structure_combo_box = cortex_structure_combo_box

        #
        cortical_structures_widget = SelectedStructuresWidget()

        self.cortical_structures_widget = cortical_structures_widget

        #
        layout = QtWidgets.QFormLayout()

        layout.addRow("Cortical plate structure", cortex_structure_combo_box)
        layout.addRow("Cortical structures", cortical_structures_widget)

        self.setLayout(layout)

    @property
    def settings(self) -> CorticalDepthMeasureSettings:
        return CorticalDepthMeasureSettings(
            cortex_structure=self.cortex_structure_combo_box.currentText(),
            sub_cortical_structures=list(
                self.cortical_structures_widget.structure_tags_mapping.keys()
            ),
        )
