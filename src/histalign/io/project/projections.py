# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from collections.abc import Callable, Iterable
import logging
from typing import Literal

import numpy as np
import psutil

from histalign.io.image import ImageFile
from histalign.language_helpers import unwrap

ProjectionKind = Literal["max", "min", "mean", "std"]

_module_logger = logging.getLogger(__name__)


def get_appropriate_projection_function(kind: ProjectionKind) -> Callable:
    match kind:
        case "max":
            return maximum_intensity_projection
        case "min":
            return minimum_intensity_projection
        case "mean":
            return mean_intensity_projection
        case "std":
            return standard_deviation_intensity_projection
        case _:
            raise ValueError(f"Unknown projection type '{kind}'.")


def maximum_intensity_projection(
    source_file: ImageFile, iteration_indices: Iterable[tuple[slice, ...]]
) -> np.ndarray:
    projection = None
    for index in iteration_indices:
        image = source_file.read_image(index)
        if projection is None:
            projection = image
        else:
            projection = np.max([projection, image], axis=0)

    if projection is None:
        return source_file.read_image(source_file.index)

    return projection


def minimum_intensity_projection(
    source_file: ImageFile, iteration_indices: Iterable[tuple[slice, ...]]
) -> np.ndarray:
    projection = None
    for index in iteration_indices:
        image = source_file.read_image(index)
        if projection is None:
            projection = image
        else:
            projection = np.min([projection, image], axis=0)

    if projection is None:
        return source_file.read_image(source_file.index)

    return projection


def mean_intensity_projection(
    source_file: ImageFile, iteration_indices: Iterable[tuple[slice, ...]]
) -> np.ndarray:
    return chunked_projection(source_file, iteration_indices, np.mean)


def standard_deviation_intensity_projection(
    source_file: ImageFile, iteration_indices: Iterable[tuple[slice, ...]]
) -> np.ndarray:
    return chunked_projection(source_file, iteration_indices, np.std)


def chunked_projection(
    source_file: ImageFile,
    iteration_indices: Iterable[tuple[slice, ...]],
    function: Callable,
) -> np.ndarray:
    x_position = source_file.dimension_order.value.index("X")
    x_size = source_file.shape[x_position]
    y_position = source_file.dimension_order.value.index("Y")
    y_size = source_file.shape[y_position]
    z_size = source_file.shape[source_file.dimension_order.value.index("Z")]

    # budget = 8 * 1024**3  # 8 GiB
    budget = psutil.virtual_memory().total * 3 // 4
    step_size = int(
        np.ceil(
            np.sqrt(
                budget
                / z_size
                / (
                    # Account for `array` item size
                    np.dtype(source_file.dtype).itemsize
                    # Account for `np.std` computation memory use
                    + np.dtype(np.float64).itemsize
                )
            )
        )
    )
    _module_logger.debug(
        f"Chunked projection: budget = {budget / 1024 ** 3:.2f} GB, {step_size = }"
    )

    shape = (x_size, y_size) if x_position < y_position else (y_size, x_size)
    projection = np.zeros(shape=shape, dtype=source_file.dtype)

    for i in range(0, x_size, step_size):
        for j in range(0, y_size, step_size):
            array = None

            x_index = slice(i, i + step_size)
            y_index = slice(j, j + step_size)

            cropped_index = (
                (x_index, y_index) if x_position < y_position else (y_index, x_index)
            )

            for index in iteration_indices:
                cropped_image = np.squeeze(source_file.read_image(index))[
                    cropped_index
                ][np.newaxis]
                if array is None:
                    array = cropped_image
                else:
                    array = np.vstack([array, cropped_image])

            array = unwrap(array, "No iteration indices provided.")

            projection[cropped_index] = np.round(function(array, axis=0)).astype(
                array.dtype
            )

    return projection
