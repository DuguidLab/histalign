# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from abc import abstractmethod
import json
import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
import pydantic
from PySide6 import QtCore

from histalign.backend.ccf.downloads import download_structure_mask
from histalign.backend.ccf.paths import get_structure_mask_path
from histalign.backend.models import (
    AlignmentSettings,
    ProjectSettings,
    QuantificationResults,
    QuantificationSettings,
)
from histalign.backend.quantification.quantification_methods import (
    compute_average_fluorescence,
    compute_cortical_depths,
)
from histalign.backend.registration import Registrator
from histalign.backend.registration.alignment import (
    build_aligned_array,
    interpolate_sparse_3d_array,
)
from histalign.frontend.pyside_helpers import FakeQtABC
from histalign.io import gather_alignment_paths, load_image, load_volume


class Quantifier(QtCore.QObject, FakeQtABC):
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

        self.quantification_settings = settings
        self.measure_settings = settings.measure_settings

    @abstractmethod
    def run(self, save_to_disk: bool = True) -> QuantificationResults:
        raise NotImplementedError

    def save_results(
        self, results: QuantificationResults, volume_hash: str = ""
    ) -> None:
        project_directory = self.quantification_settings.alignment_directory.parent
        quantification_path = project_directory / "quantification"
        os.makedirs(quantification_path, exist_ok=True)

        if volume_hash:
            volume_hash = "_" + volume_hash[:4]
        out_path = quantification_path / f"{results.hash}{volume_hash}.json"
        if out_path.exists():  # Running an already-run quantification
            return
        with open(out_path, "w") as handle:
            json.dump(results.model_dump(serialize_as_any=True), handle)


class AverageFluorescenceSliceQuantifier(Quantifier):
    def run(self, save_to_disk: bool = True) -> QuantificationResults:
        targets = gather_alignment_paths(
            self.quantification_settings.alignment_directory
        )

        self.progress_count_computed.emit(
            len(self.measure_settings.structures) * len(targets)
        )
        self.progress_changed.emit(0)

        quantification_results = QuantificationResults(
            settings=self.quantification_settings
        )

        registrator = Registrator(
            self.quantification_settings.fast_rescale,
            self.quantification_settings.fast_transform,
            "bilinear",
        )

        progress_index = 0
        for structure_name in self.measure_settings.structures:
            for i, target in enumerate(targets):
                progress_index += 1

                try:
                    with open(target) as handle:
                        alignment_settings = AlignmentSettings(**json.load(handle))
                except (pydantic.ValidationError, json.JSONDecodeError) as error:
                    self.logger.error(
                        f"Failed to load alignment for file '{target.name}'. "
                        f"Skipping it."
                    )
                    self.logger.error(error)

                    self.progress_changed.emit(progress_index)

                    continue

                full_size_histology_image = load_image(
                    alignment_settings.histology_path
                )

                try:
                    mask_image = registrator.get_reversed_image(
                        alignment_settings, structure_name, full_size_histology_image
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
                    structure_name: compute_average_fluorescence(
                        full_size_histology_image, mask_image
                    ),
                }

                if (
                    quantification_results.data.get(
                        alignment_settings.histology_path.name
                    )
                    is None
                ):
                    quantification_results.data[
                        alignment_settings.histology_path.name
                    ] = quantification_result
                else:
                    quantification_results.data[
                        alignment_settings.histology_path.name
                    ].update(quantification_result)

                self.progress_changed.emit(progress_index)

        if save_to_disk:
            self.save_results(quantification_results)
        self.results_computed.emit()

        return quantification_results


class AverageFluorescenceBrainQuantifier(Quantifier):
    def run(self, save_to_disk: bool = True) -> QuantificationResults:
        self.progress_count_computed.emit(2 + len(self.measure_settings.structures))
        self.progress_changed.emit(0)

        quantification_results = QuantificationResults(
            settings=self.quantification_settings
        )

        with open(
            self.quantification_settings.alignment_directory.parent / "project.json"
        ) as handle:
            project_settings = ProjectSettings(**json.load(handle)["project_settings"])

        alignment_array, cache_path = build_aligned_array(
            self.quantification_settings.alignment_directory,
            return_raw_array=True,
            channel_index=self.quantification_settings.channel_index,
            channel_regex=self.quantification_settings.channel_regex,
            projection_regex=self.quantification_settings.projection_regex,
        )

        if np.sum(alignment_array) == 0:
            self.logger.error(
                "Could not build an alignment volume from the given parameters. Ensure "
                "the given parameters are correct (e.g., ensure the channel corresponds"
                " to a valid file name)."
            )
            self.results_computed.emit()
            return quantification_results

        self.progress_changed.emit(1)
        interpolated_array, cache_path = interpolate_sparse_3d_array(
            alignment_array, use_cache=True, aligned_volume_hash=cache_path.stem
        )
        self.progress_changed.emit(2)

        progress_index = 2
        for structure_name in self.measure_settings.structures:
            mask_path = get_structure_mask_path(
                structure_name, project_settings.resolution
            )
            if not Path(mask_path).exists():
                download_structure_mask(structure_name, project_settings.resolution)
            mask_array = load_volume(mask_path, return_raw_array=True)

            quantification_results.data[structure_name] = compute_average_fluorescence(
                interpolated_array, mask_array
            )

            progress_index += 1
            self.progress_changed.emit(progress_index)

        if save_to_disk:
            self.save_results(quantification_results, cache_path.stem.split("_")[0])
        self.results_computed.emit()

        return quantification_results


class CorticalDepthQuantifier(Quantifier):
    def run(self, save_to_disk: bool = True) -> QuantificationResults:
        targets = gather_alignment_paths(
            self.quantification_settings.alignment_directory
        )

        self.progress_count_computed.emit(
            len(self.measure_settings.structures) * len(targets)
        )
        self.progress_changed.emit(0)

        quantification_results = QuantificationResults(
            settings=self.quantification_settings
        )

        cortex_volume = None

        progress_index = 0
        for structure_name in self.measure_settings.structures:
            structure_volume = None

            for i, target in enumerate(targets):
                progress_index += 1

                try:
                    with open(target) as handle:
                        alignment_settings = AlignmentSettings(**json.load(handle))
                except (pydantic.ValidationError, json.JSONDecodeError) as error:
                    self.logger.error(
                        f"Failed to load alignment for file '{target.name}'. "
                        f"Skipping it."
                    )
                    self.logger.error(error)

                    self.progress_changed.emit(progress_index)

                    continue

                if cortex_volume is None:
                    cortex_path = get_structure_mask_path(
                        self.measure_settings.cortex_structure,
                        alignment_settings.volume_settings.resolution,
                    )
                    if not os.path.exists(cortex_path):
                        download_structure_mask(
                            self.measure_settings.cortex_structure,
                            alignment_settings.volume_settings.resolution,
                        )
                    cortex_volume = load_volume(cortex_path)
                if structure_volume is None:
                    structure_path = get_structure_mask_path(
                        structure_name,
                        alignment_settings.volume_settings.resolution,
                    )
                    if not os.path.exists(structure_path):
                        download_structure_mask(
                            structure_name,
                            alignment_settings.volume_settings.resolution,
                        )
                    structure_volume = load_volume(structure_path)

                quantification_result = {
                    structure_name: compute_cortical_depths(
                        cortex_volume, structure_volume, alignment_settings
                    )
                }

                if (
                    quantification_results.data.get(
                        alignment_settings.histology_path.name
                    )
                    is None
                ):
                    quantification_results.data[
                        alignment_settings.histology_path.name
                    ] = quantification_result
                else:
                    quantification_results.data[
                        alignment_settings.histology_path.name
                    ].update(quantification_result)

                self.progress_changed.emit(progress_index)

        if save_to_disk:
            self.save_results(quantification_results)
        self.results_computed.emit()

        return quantification_results
