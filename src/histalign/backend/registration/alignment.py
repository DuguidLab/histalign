# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import hashlib
import json
import logging
import os
from pathlib import Path

import numpy as np
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
    alignment_directory: str | Path, use_cache: bool = True
) -> vedo.Volume:
    if isinstance(alignment_directory, str):
        alignment_directory = Path(alignment_directory)

    targets = gather_alignment_paths(alignment_directory)

    targets_hash = generate_hash_from_targets(targets)
    cache_path = ALIGNMENT_VOLUMES_CACHE_DIRECTORY / f"{targets_hash}.npz"
    if cache_path.exists() and use_cache:
        _module_logger.debug("Found cached volume. Loading from file.")
        return vedo.Volume(np.load(cache_path)["array"])

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
    return alignment_volume


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
