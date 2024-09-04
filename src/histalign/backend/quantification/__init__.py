# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

import pydantic

import histalign.backend.io as io
from histalign.backend.models.AlignmentSettings import AlignmentSettings
from histalign.backend.quantification.quantification_methods import (
    get_average_fluorescence,
)
from histalign.backend.registration.ReverseRegistrator import ReverseRegistrator

RESULT_FILE_NAME_PATTERN = re.compile(r"[0-9a-f]{32}\.json")


class Quantifier:
    quantification_method: Callable
    fast_rescale: bool
    fast_transform: bool

    def __init__(
        self,
        quantification_method: str,
        fast_rescale: bool = True,
        fast_transform: bool = False,
    ) -> None:
        self.logger = logging.getLogger(__name__)

        match quantification_method:
            case "average_fluorescence":
                self.quantification_method = get_average_fluorescence
            case _:
                raise ValueError(
                    f"Unknown quantification method '{quantification_method}'."
                )

        self.fast_rescale = fast_rescale
        self.fast_transform = fast_transform

    def quantify(
        self,
        results_directory: str,
        structures: list[str],
    ) -> Any:
        quantification_results = {}
        reverse_registrator = ReverseRegistrator(
            self.fast_rescale, self.fast_transform, "bilinear"
        )
        for structure_name in structures:
            for results_file in Path(results_directory).iterdir():
                if (
                    re.fullmatch(RESULT_FILE_NAME_PATTERN, str(results_file.name))
                    is None
                ):
                    continue

                try:
                    with open(results_file) as handle:
                        settings = AlignmentSettings(**json.load(handle))
                except (pydantic.ValidationError, json.JSONDecodeError) as error:
                    self.logger.error(
                        f"Failed to load results for file '{results_file.name}'. "
                        f"Skipping it."
                    )
                    self.logger.error(error)
                    continue

                full_size_histology_image = io.load_image(settings.histology_file_path)

                try:
                    mask_image = reverse_registrator.get_reversed_image(
                        settings, structure_name, full_size_histology_image
                    )
                except FileNotFoundError:
                    self.logger.error(
                        f"Could not load mask volume for structure '{structure_name}'. "
                        f"File not found. Skipping structure."
                    )
                    break

                quantification_result = {
                    structure_name: self.quantification_method(
                        full_size_histology_image, mask_image
                    ),
                }

                if quantification_results.get(results_file.stem) is None:
                    quantification_results[results_file.stem] = quantification_result
                else:
                    quantification_results[results_file.stem].update(
                        quantification_result
                    )

        return quantification_results
