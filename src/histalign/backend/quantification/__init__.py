# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from abc import abstractmethod
import json
import logging
import os
from pathlib import Path
from typing import Optional

from PySide6 import QtCore
import pydantic

from histalign.backend.ccf.downloads import download_structure_mask
from histalign.backend.ccf.paths import get_structure_mask_path
from histalign.backend.io import (
    gather_alignment_paths,
    load_image,
    load_volume,
)
from histalign.backend.models import (
    AlignmentSettings,
    ProjectSettings,
    QuantificationMeasure,
    QuantificationResults,
    QuantificationSettings,
)
from histalign.backend.quantification.quantification_methods import (
    compute_average_fluorescence,
)
from histalign.backend.registration import Registrator
from histalign.backend.registration.alignment import (
    build_alignment_volume,
    interpolate_sparse_3d_array,
)


class Quantifier(QtCore.QObject):
    """A class meant to be an ABC for quantifiers.

    Unfortunately, getting ABCs to work with PySide is a pain so let's just assume this
    is an ABC for architectural reasons.

    Abstract methods are still decorated to help with IntelliSense but "abstractness" is
    enforced manually.
    """

    settings: QuantificationSettings

    progress_count_computed: QtCore.Signal = QtCore.Signal(int)
    progress_changed: QtCore.Signal = QtCore.Signal(int)
    results_computed: QtCore.Signal = QtCore.Signal()

    def __init__(
        self, settings: QuantificationSettings, parent: Optional[QtCore.QObject] = None
    ) -> None:
        # Attempt to make this an ABC
        for function_name in ["run"]:
            exec(
                f"""
if self.__class__.{function_name} is Quantifier.{function_name}:
    raise TypeError(
        f"Can't instantiate abstract class "
        f"{self.__class__.__qualname__} with abstract method "
        f"{function_name}"
    )
            """
            )

        super().__init__(parent)

        self.logger = logging.getLogger(
            f"{self.__module__}.{self.__class__.__qualname__}"
        )

        self.settings = settings

    @abstractmethod
    def run(self, save_to_disk: bool = True) -> QuantificationResults:
        raise NotImplementedError

    def save_results(self, results: QuantificationResults) -> None:
        project_directory = self.settings.alignment_directory.parent
        quantification_path = project_directory / "quantification"
        os.makedirs(quantification_path, exist_ok=True)

        with open(quantification_path / f"{results.hash}.json", "w") as handle:
            json.dump(results.model_dump(), handle)


class SliceQuantifier(Quantifier):
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


class BrainQuantifier(Quantifier):
    def run(self, save_to_disk: bool = True) -> QuantificationResults:
        self.progress_count_computed.emit(2 + len(self.settings.structures))
        self.progress_changed.emit(0)

        quantification_results = QuantificationResults(settings=self.settings)

        match self.settings.quantification_measure:
            case QuantificationMeasure.AVERAGE_FLUORESCENCE:
                quantification_method = compute_average_fluorescence
            case _:
                raise NotImplementedError(
                    f"Quantification method for enum variant '{self}' not implemented."
                )

        with open(self.settings.alignment_directory.parent / "project.json") as handle:
            project_settings = ProjectSettings(**json.load(handle)["project_settings"])

        alignment_array = build_alignment_volume(
            self.settings.alignment_directory, return_raw_array=True
        )
        self.progress_changed.emit(1)
        interpolated_array = interpolate_sparse_3d_array(alignment_array)
        self.progress_changed.emit(2)

        progress_index = 2
        for structure_name in self.settings.structures:
            mask_path = get_structure_mask_path(
                structure_name, project_settings.resolution
            )
            if not Path(mask_path).exists():
                download_structure_mask(structure_name, project_settings.resolution)
            mask_array = load_volume(mask_path, return_raw_array=True)

            quantification_results.data[structure_name] = quantification_method(
                interpolated_array, mask_array
            )

            progress_index += 1
            self.progress_changed.emit(progress_index)

        if save_to_disk:
            self.save_results(quantification_results)
        self.results_computed.emit()

        return quantification_results


class QuantificationThread(QtCore.QThread):
    quantifier: BrainQuantifier | SliceQuantifier

    progress_count_computed: QtCore.Signal = QtCore.Signal(int)
    progress_changed: QtCore.Signal = QtCore.Signal(int)
    results_computed: QtCore.Signal = QtCore.Signal()

    def __init__(
        self, settings: QuantificationSettings, parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)

        match settings.approach:
            case "Whole-brain":
                self.quantifier = BrainQuantifier(settings)
            case "Per-slice":
                self.quantifier = SliceQuantifier(settings)
            case other:
                raise ValueError("Unknown quantifier '{other}'.")

        self.quantifier.progress_count_computed.connect(
            self.progress_count_computed.emit
        )
        self.quantifier.progress_changed.connect(self.progress_changed.emit)
        self.quantifier.results_computed.connect(self.results_computed.emit)

    def run(self) -> None:
        self.quantifier.run()
