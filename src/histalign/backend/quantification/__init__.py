# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import json
import logging
import os
from pathlib import Path
import re
from typing import Optional

from PySide6 import QtCore
import pydantic

from histalign.backend.io import gather_alignment_paths, load_image
from histalign.backend.models import (
    AlignmentSettings,
    QuantificationMeasure,
    QuantificationResults,
    QuantificationSettings,
)
from histalign.backend.quantification.quantification_methods import (
    compute_average_fluorescence,
)
from histalign.backend.registration import Registrator


class SliceQuantifier(QtCore.QObject):
    settings: QuantificationSettings

    progress_count_computed: QtCore.Signal = QtCore.Signal(int)
    progress_changed: QtCore.Signal = QtCore.Signal(int)
    results_computed: QtCore.Signal = QtCore.Signal()

    def __init__(
        self, settings: QuantificationSettings, parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(
            f"{self.__module__}.{self.__class__.__qualname__}"
        )

        self.settings = settings

    def run(self, save_to_disk: bool = True) -> QuantificationResults:
        quantification_results = QuantificationResults(settings=self.settings)

        reverse_registrator = Registrator(
            self.settings.fast_rescale, self.settings.fast_transform, "bilinear"
        )

        match self.settings.quantification_measure:
            case QuantificationMeasure.AVERAGE_FLUORESCENCE:
                quantification_method = compute_average_fluorescence
            case _:
                raise NotImplementedError(
                    f"Quantification method for enum variant '{self}' not implemented."
                )

        targets = gather_alignment_paths(self.settings.alignment_directory)

        self.progress_count_computed.emit(len(self.settings.structures) * len(targets))
        self.progress_changed.emit(0)

        progress_index = 0
        for structure_name in self.settings.structures:
            for i, target in enumerate(targets):
                progress_index += 1

                try:
                    with open(target) as handle:
                        settings = AlignmentSettings(**json.load(handle))
                except (pydantic.ValidationError, json.JSONDecodeError) as error:
                    self.logger.error(
                        f"Failed to load alignment for file '{target.name}'. "
                        f"Skipping it."
                    )
                    self.logger.error(error)

                    self.progress_changed.emit(progress_index)

                    continue

                full_size_histology_image = load_image(settings.histology_path)

                try:
                    mask_image = reverse_registrator.get_reversed_image(
                        settings, structure_name, full_size_histology_image
                    )
                except FileNotFoundError:
                    self.logger.error(
                        f"Could not load mask volume for structure '{structure_name}'. "
                        f"File not found. Skipping structure."
                    )

                    for _ in range(i, len(targets)):
                        self.progress_changed.emit(progress_index)

                    break

                quantification_result = {
                    structure_name: quantification_method(
                        full_size_histology_image, mask_image
                    ),
                }

                if (
                    quantification_results.data.get(settings.histology_path.name)
                    is None
                ):
                    quantification_results.data[settings.histology_path.name] = (
                        quantification_result
                    )
                else:
                    quantification_results.data[settings.histology_path.name].update(
                        quantification_result
                    )

                self.progress_changed.emit(progress_index)

        if save_to_disk:
            self.save_results(quantification_results)
        self.results_computed.emit()

        return quantification_results

    def save_results(self, results: QuantificationResults) -> None:
        project_directory = self.settings.alignment_directory.parent
        quantification_path = project_directory / "quantification"
        os.makedirs(quantification_path, exist_ok=True)

        with open(quantification_path / f"{results.hash}.json", "w") as handle:
            json.dump(results.model_dump(), handle)
