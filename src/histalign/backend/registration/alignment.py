# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import hashlib
import json
import logging
import math
import os
from pathlib import Path
import time
from typing import Optional

import numpy as np
from scipy.interpolate import RBFInterpolator
import vedo

from histalign.backend.ccf.downloads import download_structure_mask
from histalign.backend.ccf.paths import get_structure_mask_path
from histalign.backend.io import (
    DATA_ROOT,
    gather_alignment_paths,
    load_alignment_settings,
    load_image,
    load_volume,
)
from histalign.backend.models import (
    AlignmentSettings,
    Resolution,
)
from histalign.backend.registration import Registrator
from histalign.backend.workspace import VolumeSlicer

ALIGNMENT_VOLUMES_CACHE_DIRECTORY = DATA_ROOT / "alignment_volumes"
os.makedirs(ALIGNMENT_VOLUMES_CACHE_DIRECTORY, exist_ok=True)

_module_logger = logging.getLogger(__name__)


def build_alignment_volume(
    alignment_directory: str | Path,
    use_cache: bool = True,
    return_raw_array: bool = False,
) -> np.ndarray | vedo.Volume:
    if isinstance(alignment_directory, str):
        alignment_directory = Path(alignment_directory)

    targets = gather_alignment_paths(alignment_directory)

    targets_hash = generate_hash_from_targets(targets)
    cache_path = ALIGNMENT_VOLUMES_CACHE_DIRECTORY / f"{targets_hash}.npz"
    if cache_path.exists() and use_cache:
        _module_logger.debug("Found cached volume. Loading from file.")

        volume = vedo.Volume(np.load(cache_path)["array"])
        if return_raw_array:
            return volume.tonumpy()
        return volume

    with open(targets[0]) as handle:
        temp_settings = AlignmentSettings(**json.load(handle))
    reference_shape = temp_settings.volume_settings.shape

    alignment_volume = vedo.Volume(np.zeros(shape=reference_shape, dtype=np.uint16))
    alignment_array = alignment_volume.tonumpy()
    slicer = VolumeSlicer(volume=alignment_volume)

    _module_logger.debug(f"Generating {len(targets)} meshes.")
    plane_meshes = []
    for index, target in enumerate(targets):
        if index > 0 and index % 5 == 0:
            _module_logger.debug(f"Generated {index} meshes.")

        alignment_settings = load_alignment_settings(target)

        histology_slice = load_image(alignment_settings.histology_path)

        registrator = Registrator(True, True)
        registered_slice = registrator.get_forwarded_image(
            histology_slice, alignment_settings
        )

        plane_mesh = slicer.slice(alignment_settings.volume_settings, return_mesh=True)
        plane_mesh.pointdata["ImageScalars"] = registered_slice.flatten()

        plane_meshes.append(plane_mesh)
    _module_logger.debug(f"Generated all {len(targets)} meshes.")

    _module_logger.debug(f"Gathering {len(targets)} meshes into alignment volume.")
    for index, mesh in enumerate(plane_meshes):
        if index > 0 and index % 5 == 0:
            _module_logger.debug(f"Gathered {index} meshes.")

        temp_volume = vedo.Volume(np.zeros_like(alignment_array))
        temp_volume.interpolate_data_from(mesh, radius=1)

        temp_array = temp_volume.tonumpy()
        temp_array = np.round(temp_array).astype(np.uint16)

        alignment_array[:] = np.maximum(alignment_array, temp_array)
    alignment_volume.modified()
    _module_logger.debug(f"Gathered all {len(plane_meshes)} meshes.")

    if use_cache:
        _module_logger.debug("Caching volume to file.")
        os.makedirs(ALIGNMENT_VOLUMES_CACHE_DIRECTORY, exist_ok=True)
        np.savez_compressed(cache_path, array=alignment_volume.tonumpy())

    if return_raw_array:
        return alignment_volume.tonumpy()

    return alignment_volume


def interpolate_sparse_3d_array(
    array: np.ndarray,
    reference_mask: Optional[np.ndarray] = None,
    pre_masked: bool = False,
    kernel: str = "multiquadric",
    neighbours: int = 27,
    epsilon: int = 1,
    degree: Optional[int] = None,
    chunk_size: Optional[int] = 1_000_000,
    recursive: bool = False,
) -> np.ndarray:
    start_time = time.perf_counter()

    if reference_mask is not None and (array_shape := array.shape) != (
        reference_shape := reference_mask.shape
    ):
        raise ValueError(
            f"Array and reference mask have different shapes "
            f"({array_shape} vs {reference_shape})."
        )

    # Mask the array if necessary
    if reference_mask is not None and not pre_masked:
        array = np.where(reference_mask, array, 0)

    interpolated_array = array.copy()
    interpolated_array = interpolated_array.astype(np.float64)

    if reference_mask is None:
        # Interpolate the whole grid
        target_coordinates = tuple(
            array.flatten().astype(int)
            for array in np.meshgrid(
                np.linspace(
                    0, interpolated_array.shape[0] - 1, interpolated_array.shape[0]
                ),
                np.linspace(
                    0, interpolated_array.shape[1] - 1, interpolated_array.shape[1]
                ),
                np.linspace(
                    0, interpolated_array.shape[2] - 1, interpolated_array.shape[2]
                ),
                indexing="ij",
            )
        )
    else:
        # Interpolate only non-zero coordinates of mask
        target_coordinates = np.nonzero(reference_mask)
    target_points = np.array(target_coordinates).T

    if chunk_size is None:
        chunk_size = target_points.shape[0]

    _module_logger.info(
        f"Starting interpolation with parameters "
        f"{{"
        f"kernel: {kernel}, "
        f"neighbours: {neighbours}, "
        f"epsilon: {epsilon}, "
        f"degree: {degree}, "
        f"chunk size: {chunk_size:,}, "
        f"recursive: {recursive}"
        f"}}."
    )

    failed_chunks = []
    previous_target_size = target_points.shape[0]
    while True:
        known_coordinates = np.nonzero(interpolated_array)
        known_points = np.array(known_coordinates).T

        known_values = array[known_coordinates]

        interpolator = RBFInterpolator(
            known_points,
            known_values,
            kernel=kernel,
            neighbors=neighbours,
            epsilon=epsilon,
            degree=degree,
        )

        chunk_start = 0
        chunk_end = chunk_size
        chunk_index = 1
        chunk_count = math.ceil(target_points.shape[0] / chunk_size)
        while chunk_start < target_points.shape[0]:
            _module_logger.info(
                f"Interpolating chunk {chunk_index}/{chunk_count} "
                f"({chunk_index / chunk_count:.0%})."
            )

            chunk_coordinates = tuple(
                coordinate[chunk_start:chunk_end] for coordinate in target_coordinates
            )
            chunk_points = target_points[chunk_start:chunk_end]

            try:
                interpolated_array[chunk_coordinates] = interpolator(chunk_points)
            except np.linalg.LinAlgError:
                failed_chunks.append([chunk_start, chunk_end])
                _module_logger.info(f"Failed to interpolate chunk {chunk_index}.")

            chunk_start += chunk_size
            chunk_end += chunk_size
            chunk_index += 1

        if not recursive or len(failed_chunks) == 0:
            break

        # Prepare the next loop
        target_coordinates = tuple(
            np.concatenate(
                [target_coordinate[start:end] for start, end in failed_chunks]
            )
            for target_coordinate in target_coordinates
        )
        target_points = np.array(target_coordinates).T
        failed_chunks = []

        # Avoid infinitely looping
        if previous_target_size == target_points.shape[0]:
            _module_logger.error(
                f"Interpolation is not fully solvable with current combination of "
                f"kernel, neighbours parameter and chunk size. "
                f"Returning current result."
            )
            break
        previous_target_size = target_points.shape[0]

        _module_logger.info(
            f"There were {len(failed_chunks)} failed chunks of size {chunk_size}. "
            f"Recursing with newly interpolated data."
        )

    total_time = time.perf_counter() - start_time
    total_hours, remaining_time = divmod(total_time, 3600)
    total_minutes, total_seconds = divmod(remaining_time, 60)
    time_string = (
        f"{f'{total_hours:.0f}h' if total_hours else ''}"
        f"{f'{total_minutes:>2.0f}m' if total_minutes else ''}"
        f"{total_seconds:>2.0f}s"
    )
    _module_logger.info(f"Finished interpolation in {time_string}.")

    return interpolated_array


def mask_off_structure(
    volume: vedo.Volume, structure_name: str, resolution: Resolution
) -> vedo.Volume:
    mask_path = get_structure_mask_path(structure_name, Resolution(resolution))
    if not Path(mask_path).exists():
        download_structure_mask(structure_name, resolution)

    mask_volume = load_volume(mask_path)

    return vedo.Volume(np.where(mask_volume.tonumpy() > 0, volume.tonumpy(), 0))


def generate_hash_from_targets(targets: list[Path]) -> str:
    return hashlib.md5("".join(map(str, targets)).encode("UTF-8")).hexdigest()
