# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from datetime import datetime
import logging
import os
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd
from PySide6 import QtCore

from histalign.backend.ccf import get_structure_mask_path
from histalign.backend.models import (
    AlignmentSettings,
    Quantification,
    QuantificationSettings,
)
from histalign.backend.quantification.quantification_functions import (
    quantify_average_fluorescence,
    quantify_cell_count,
)
from histalign.backend.registration.alignment import replace_path_parts
from histalign.backend.workspace import VolumeSlicer
from histalign.io import (
    DimensionOrder,
    gather_alignment_paths,
    ImageFile,
    load_alignment_settings,
    load_volume,
    open_file,
)

_module_logger = logging.getLogger(__name__)


def get_appropriate_quantification_function(
    quantification: Quantification,
) -> Callable[[np.ndarray, np.ndarray], Any]:
    """Returns the quantification function for the given quantification.

    Args:
        quantification (Quantification): Quantification for which to find a function.

    Returns:
        Callable[[np.ndarray, np.ndarray], Any]: A function matching the quantification.

    Raises:
        ValueError: When the quantification does not have a matching function.
    """
    match quantification:
        case Quantification.AVERAGE_FLUORESCENCE:
            return quantify_average_fluorescence
        case Quantification.CELL_COUNTING:
            return quantify_cell_count
        case other:
            raise ValueError(f"Unknown quantification '{other}'.")


class QuantificationThread(QtCore.QThread):
    """Thread object used to handle QuantificationSettings requests.

    Args:
        settings (QuantificationSettings): Quantification settings to use.
        parent (Optional[QtCore.QObject]): Parent of this object.

    Attributes:
        settings (QuantificationSettings): Quantification settings to use.
    """

    def __init__(
        self, settings: QuantificationSettings, parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)

        self.settings = settings

    def run(self) -> None:
        _module_logger.debug("Starting quantification.")
        settings = self.settings

        # Ensure results directory exists
        results_directory = settings.alignment_directory.parent / "quantification"
        os.makedirs(results_directory, exist_ok=True)

        # Prepare handles to the relevant data
        input_handles: dict[Path, ImageFile] = {}
        alignment_settings_list: list[AlignmentSettings] = []
        if settings.on_volume:
            # Side-step `load_volume` since volumes should be using HDF5 by now and this
            # streamlines file handling with single slices.
            path = settings.alignment_directory / "volumes" / "interpolated"
            paths = list(path.iterdir())
            if len(paths) != 1:
                _module_logger.error(
                    f"Failed to find the interpolated volume for "
                    f"'{settings.alignment_directory}'. Aborting quantification."
                )
                return

            input_handles[paths[0]] = open_file(
                paths[0], dimension_order=DimensionOrder.XYZ
            )
        else:
            # Gather alignment paths
            paths = gather_alignment_paths(settings.alignment_directory)
            # Loop over slices and get a handle
            for path in paths:
                alignment_settings = load_alignment_settings(path)
                alignment_settings_list.append(alignment_settings)
                image_path = replace_path_parts(
                    alignment_settings.histology_path,  # type: ignore[arg-type]
                    settings.channel_regex,
                    settings.channel_substitution,
                    "",
                )

                input_handles[image_path] = open_file(image_path)

        # Load structure masks
        # TODO: Decide whether to keep all loaded into memory or load/drop/load/...
        #       every loop. On higher resolutions, keeping a lot in memory will be bad.
        masks: dict[str, VolumeSlicer] = {}
        for structure in settings.structures:
            structure_path = get_structure_mask_path(
                structure, settings.resolution, ensure_downloaded=True
            )

            volume = load_volume(structure_path)
            slicer = VolumeSlicer(volume=volume)

            masks[structure] = slicer

        # Determine the quantification being run
        quantification_function = get_appropriate_quantification_function(
            settings.quantification
        )

        # Run the quantification on the data
        results = pd.DataFrame(
            columns=[
                "quantification",
                "alignment_directory",
                "array_path",
                "structure",
                "number_points",
                "processing_time",
                "timestamp",
                "data",
            ]
        )
        for i, (path, handle) in enumerate(input_handles.items()):
            array = handle.load()

            for structure in settings.structures:
                if settings.on_volume:
                    mask = masks[structure].volume.tonumpy()
                else:
                    mask = masks[structure].slice(
                        alignment_settings_list[i].volume_settings
                    )

                start_time = perf_counter()
                results.loc[len(results)] = dict(
                    quantification=settings.quantification.value,
                    alignment_directory=settings.alignment_directory,
                    array_path=str(path),
                    structure=structure,
                    number_points=np.sum(mask),
                    data=quantification_function(array, mask),
                    processing_time=perf_counter() - start_time,
                    timestamp=datetime.now().astimezone().isoformat(),
                )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M")  # YYYYMMDD_HHMM
        results.to_csv(
            results_directory
            / (
                f"{settings.source_directory.name}_"
                f"{settings.quantification.value}_"
                f"{timestamp}.csv"
            )
        )

        _module_logger.debug("Finished quantification.")
