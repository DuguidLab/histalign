# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtCore

from histalign.backend.models import QuantificationSettings
from histalign.backend.quantification.quantifiers import (
    AverageFluorescenceBrainQuantifier,
    AverageFluorescenceSliceQuantifier,
    CorticalDepthQuantifier,
    Quantifier,
)


def get_appropriate_quantifier(
    settings: QuantificationSettings,
) -> type[Quantifier]:
    match settings.quantification_measure:
        case "average_fluorescence":
            match settings.measure_settings.approach:
                case "Whole-brain":
                    return AverageFluorescenceBrainQuantifier
                case "Per-slice":
                    return AverageFluorescenceSliceQuantifier
        case "cortical_depth":
            return CorticalDepthQuantifier

    raise ValueError(
        f"Unknown quantification measure '{settings.quantification_measure}'."
    )


class QuantificationThread(QtCore.QThread):
    quantifier: Quantifier

    progress_count_computed: QtCore.Signal = QtCore.Signal(int)
    progress_changed: QtCore.Signal = QtCore.Signal(int)
    results_computed: QtCore.Signal = QtCore.Signal()

    def __init__(
        self, settings: QuantificationSettings, parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)

        self.quantifier = get_appropriate_quantifier(settings)(settings)

        self.quantifier.progress_count_computed.connect(
            self.progress_count_computed.emit
        )
        self.quantifier.progress_changed.connect(self.progress_changed.emit)
        self.quantifier.results_computed.connect(self.results_computed.emit)

    def run(self) -> None:
        self.quantifier.run()
