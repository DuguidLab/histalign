# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from collections.abc import Sequence
import json
import logging
import math
import os
from pathlib import Path
import re
import time
from typing import Literal, Optional

import h5py
import numpy as np
import pydantic
from scipy.interpolate import RBFInterpolator
from scipy.spatial.distance import euclidean
import vedo

from histalign.backend.ccf import get_structure_mask_path
from histalign.backend.maths import (
    apply_rotation,
    compute_centre,
    compute_normal,
    compute_normal_from_raw,
    compute_origin,
)
from histalign.backend.models import (
    AlignmentSettings,
    Orientation,
    Resolution,
    VolumeSettings,
)
from histalign.backend.registration import Registrator
from histalign.io import DATA_ROOT, gather_alignment_paths, load_image, load_volume

ALIGNMENT_VOLUMES_CACHE_DIRECTORY = DATA_ROOT / "alignment_volumes"
os.makedirs(ALIGNMENT_VOLUMES_CACHE_DIRECTORY, exist_ok=True)
INTERPOLATED_VOLUMES_CACHE_DIRECTORY = DATA_ROOT / "interpolated_volumes"
os.makedirs(INTERPOLATED_VOLUMES_CACHE_DIRECTORY, exist_ok=True)

Coordinates = np.ndarray  # Coordinates in NumPy form
CoordinatesTuple = tuple[
    float, ...
]  # Coordinates in tuple form (OK as dictionary keys)
Projection = np.ndarray

_module_logger = logging.getLogger(__name__)


def build_aligned_array(
    alignment_directory: str | Path,
    z_spacing: int = -1,
    channel_regex: str = "",
    channel_substitution: str = "",
    projection_regex: str = "",
    misc_regexes: Sequence[str] = (),
    misc_subs: Sequence[str] = (),
    force: bool = True,
) -> None:
    """Builds a 3D aligned array from alignment settings.

    In order to build the array, the following steps are followed:
    1. List all the alignment paths (settings file ending in .json).
    2. Loop over the paths.
        1. Load the alignment settings.
        2. Apply regex substitution to the histology path.
        3. Load the image array (can be 2D or 3D).
        4. Compute the origin and normal as described by the alignment settings.
        5. Check the dimensionality of the image array.
            1. If 3D, compute the origin of each slice.
        6. Generate a point cloud for each origin/image pair (only 1 when
           dimensionality is 2D, multiple when 3D).
        7. Insert images data into their respective point cloud.
        8. Interpolate the point clouds onto the regular grid of the CCF.
    3. Cache the result.

    Args:
        alignment_directory (str | Path):
            Path to the directory containing the alignment settings of the images to use
            to build the array.
        z_spacing (int):
            Spacing to use when building a volume from Z stacks.
        channel_regex (str, optional):
            Channel regex identifying the channel part of `path`'s name. Use in
            conjunction with `channel_index`.
        channel_substitution (str, optional):
            String to substitute `channel_regex` with. Leave empty to use alignment
            channel. Use in conjunction with `channel_regex`.
        projection_regex (str, optional):
            Projection regex identifying the projection part of `path`'s name.
        misc_regexes (Sequence[str], optional):
            Miscellaneous regex identifying extra parts of alignment paths found in
            `alignment_directory`. Use in conjunction with `misc_subs` to replace
            arbitrary parts of the path. The shortest of the two argument dictates how
            many elements are replaced. Unlike channel and projection arguments, this
            can replace any part of the path, not just the name.
        misc_subs (Sequence[str], optional):
            Miscellaneous substitutions to replace in `alignment_directory`. Use in
            conjunction with `misc_regexes` to replace arbitrary parts of the path.
            The shortest of the two argument dictates how many elements are replaced.
        force (bool, optional): Whether to force building if cache already exists.
    """
    _module_logger.debug(
        f"Building alignment volume for directory '{alignment_directory}'."
    )

    # Validate arguments
    alignment_directory = Path(alignment_directory)

    if z_spacing < 1 and projection_regex:
        _module_logger.warning(
            f"Received a projection regex but an invalid Z spacing ('{z_spacing}'). "
            f"Will default to volume resolution as spacing."
        )

    if channel_regex is not None and channel_substitution is None:
        _module_logger.warning(
            "Received channel regex but no channel index. Building alignment "
            "volume using the same channel as was used for alignment."
        )
    elif channel_regex is None and channel_substitution is not None:
        _module_logger.warning(
            "Received channel index but no channel regex. Building alignment "
            "volume using the same channel as was used for alignment."
        )

    # Gather all the alignment settings paths
    alignment_paths = gather_alignment_paths(alignment_directory)
    if not alignment_paths:
        _module_logger.error(
            f"No alignments found for directory '{alignment_directory}'."
        )
        return

    _module_logger.debug(f"Found {len(alignment_paths)} alignments.")

    # Inspect cache
    # TODO: Improve cache path so that it takes into account regexes
    cache_directory = alignment_directory / "volumes" / "aligned"
    os.makedirs(cache_directory, exist_ok=True)
    cache_path = cache_directory / f"{alignment_directory.name}.h5"
    if cache_path.exists() and not force:
        return
    # Array inside which to store interpolated data from alignment point clouds
    alignment_array = None
    # Dummy volume used to query the grid coordinates when interpolating
    query_volume = None
    for progress_index, alignment_path in enumerate(alignment_paths):
        if (progress := progress_index + 1) % 5 == 0:
            _module_logger.debug(
                f"Gathered {progress}/{len(alignment_paths)} slices "
                f"({progress / len(alignment_paths):.0%})."
            )

        # Load the alignment settings
        settings = AlignmentSettings(**json.load(alignment_path.open()))

        # Apply regex substitution to the histology path
        substituted_path = replace_path_parts(
            settings.histology_path,
            channel_regex,
            channel_substitution,
            projection_regex,
            misc_regexes,
            misc_subs,
        )
        try:
            settings.histology_path = substituted_path
        except pydantic.ValidationError:
            _module_logger.warning(
                f"Histology path after regex substitution does not exist for "
                f"'{settings.histology_path}' (substituted: '{substituted_path}'). "
                f"Using the same projected image as was used during registration."
            )

        # Load the image array (allowed to be 2D or 3D)
        array = load_image(settings.histology_path, allow_stack=True)
        if len(array.shape) not in [2, 3]:
            _module_logger.error(
                "Only image arrays with 2 and 3 dimensions (XY and XYZ) are allowed."
            )
            continue

        # Compute the origin and normal as described by the alignment
        alignment_origin = compute_origin(
            compute_centre(settings.volume_settings.shape, floor=False),
            settings.volume_settings,
        )
        alignment_normal = compute_normal(settings.volume_settings)

        # List all the 2D images along their origins
        images = []
        origins = []
        # If 2D, only one image and origin
        if len(array.shape) == 2:
            images = [array]
            origins = [alignment_origin]
        # If 3D, extract each image and compute its origin
        else:
            slice_: list[int | slice] = [slice(None)] * len(array.shape)
            # Assume the Z-dimension is the smallest one
            z_dimension_index = array.shape.index(min(array.shape))
            z_count = array.shape[z_dimension_index]

            # Loop over each Z-index to extract the images
            for index in range(z_count):
                slice_[z_dimension_index] = index
                images.append(array[tuple(slice_)])

            # Loop over multiple of the normal to get origins
            z_scaling = (
                z_spacing / settings.volume_settings.resolution if z_spacing > 0 else 1
            )
            for i in range(-int(z_count / 2) + (z_count % 2 == 0), z_count // 2 + 1):
                origins.append(alignment_origin + i * alignment_normal * z_scaling)

        # Register each image
        registrator = Registrator()
        for index, origin in enumerate(origins):
            image = registrator.get_forwarded_image(
                images[index], settings, origin.tolist()
            )
            images[index] = image

        # Loop over each image and generate its 3D point cloud
        point_clouds = []
        for image, origin in zip(images, origins):
            cloud = build_point_cloud(origin, image.shape, settings.volume_settings)

            # Insert point data from registered image
            if settings.volume_settings.orientation == Orientation.HORIZONTAL:
                image = np.flipud(image)
            elif settings.volume_settings.orientation == Orientation.SAGITTAL:
                image = np.fliplr(image)
            cloud.pointdata["ImageScalars"] = image.flatten()

            point_clouds.append(cloud)

        # Interpolate the point clouds
        if alignment_array is None:
            alignment_array = np.zeros(settings.volume_settings.shape, dtype=np.uint16)
            query_volume = vedo.Volume(alignment_array)

        for points in point_clouds:
            # Interpolate and store the result in a temporary array
            tmp_array = query_volume.interpolate_data_from(points, radius=1).tonumpy()
            tmp_array = np.round(tmp_array).astype(np.uint16)

            # TODO: Might be worth thinking of another way to merge. Using the maximum
            #       works fine when working with non-overlapping slices but a mean or
            #       something more robust might make more sense when tmp_array and
            #       alignment_array have common, non-zero points.
            # Merge the new plane into the master array
            alignment_array[:] = np.maximum(alignment_array, tmp_array)

    _module_logger.debug(
        f"Finished gathering slices. Caching result to '{cache_path}'."
    )
    with h5py.File(cache_path, "w") as handle:
        handle.create_dataset(name="array", data=alignment_array, compression="gzip")
    append_volume(alignment_directory, cache_path, "aligned")


def build_point_cloud(
    origin: Sequence[float], shape: Sequence[int], settings: VolumeSettings
) -> vedo.Points:
    # Build a plane assuming no rotations
    plane = vedo.Plane(
        normal=compute_normal_from_raw(0, 0, settings.orientation), s=shape
    )

    # Extract three of the four corners of the plane
    p0, p1, _, p3 = plane.points

    # Compute the normals of two orthogonal edges
    normal1 = (p0 - p1) / euclidean(p1, p0)
    normal2 = (p3 - p1) / euclidean(p1, p3)

    # Apply alignment rotation on normals
    normal1 = apply_rotation(normal1, settings)
    normal2 = apply_rotation(normal2, settings)

    # Generate a grid of coordinates the same size as the plane
    xs, ys = np.meshgrid(
        np.linspace(0, round(euclidean(p1, p0)), round(euclidean(p1, p0))),
        np.linspace(0, round(euclidean(p1, p3)), round(euclidean(p1, p3))),
    )
    points = np.vstack([xs.ravel(), ys.ravel()])

    # Apply alignment rotation on the points
    points = np.dot(np.vstack((normal1, normal2)).T, points).T

    # Translate the grid origin to the alignment origin
    points += -vedo.Points(points).center_of_mass() + origin

    return vedo.Points(points)


def interpolate_sparse_3d_array(
    array: np.ndarray,
    resolution: Resolution,
    alignment_directory: Path,
    mask_name: str = "root",
    only_mask: bool = True,
    kernel: str = "multiquadric",
    neighbours: int = 27,
    epsilon: int = 1,
    degree: Optional[int] = None,
    chunk_size: Optional[int] = 1_000_000,
    force: bool = False,
) -> np.ndarray:
    start_time = time.perf_counter()

    # Inspect cache and return if exists
    _mask_name = "_" + "-".join(mask_name.split(" ")).lower()
    cache_directory = alignment_directory / "volumes" / "interpolated"
    os.makedirs(cache_directory, exist_ok=True)
    cache_path = (
        cache_directory
        / f"{alignment_directory.name}{_mask_name}_{kernel}_{neighbours}_{epsilon}_"
        f"{degree or 0}.h5"
    )
    if cache_path.exists() and not force:
        _module_logger.debug("Found cached array. Loading from file.")
        with h5py.File(cache_path, "r") as handle:
            array = handle["array"][:]
        return array

    # Load the mask
    mask_path = get_structure_mask_path(mask_name, resolution, ensure_downloaded=True)
    mask_array = load_volume(mask_path, as_array=True)

    # Compute interpolation target coordinates
    if only_mask:
        # Interpolate only non-zero coordinates of mask
        target_coordinates = np.nonzero(mask_array)
    else:
        # Interpolate the whole grid
        ii = np.linspace(0, mask_array.shape[0] - 1, mask_array.shape[0], dtype=int)
        jj = np.linspace(0, mask_array.shape[1] - 1, mask_array.shape[1], dtype=int)
        kk = np.linspace(0, mask_array.shape[2] - 1, mask_array.shape[2], dtype=int)

        target_coordinates = tuple(
            coordinates_array.flatten()
            for coordinates_array in np.meshgrid(ii, jj, kk, indexing="ij")
        )
    target_points = np.array(target_coordinates).T

    # Start the interpolation
    _module_logger.debug(
        f"Starting interpolation with parameters "
        f"{{"
        f"kernel: {kernel}, "
        f"neighbours: {neighbours}, "
        f"epsilon: {epsilon}, "
        f"degree: {degree}, "
        f"chunk size: {chunk_size:,}"
        f"}}."
    )

    interpolated_array = np.zeros_like(array, dtype=np.float64)

    known_coordinates = np.nonzero(array)
    known_points = np.array(known_coordinates).T
    known_values = array[known_coordinates]  # Sparse input data

    interpolator = RBFInterpolator(
        known_points,
        known_values,
        kernel=kernel,
        neighbors=neighbours,
        epsilon=epsilon,
        degree=degree,
    )

    # Split the work into chunks to break down the computation to provide feedback of
    # the progress.
    chunk_start = 0
    chunk_end = chunk_size
    chunk_index = 1  # Used exclusively for logging, 1-based numbering
    chunk_count = math.ceil(target_points.shape[0] / chunk_size)
    while chunk_start < target_points.shape[0]:
        _module_logger.debug(
            f"Interpolating chunk {chunk_index}/{chunk_count} "
            f"({chunk_index / chunk_count:.0%})."
        )

        chunk_coordinates = tuple(
            coordinate[chunk_start:chunk_end] for coordinate in target_coordinates
        )
        chunk_points = target_points[chunk_start:chunk_end]

        interpolated_array[chunk_coordinates] = interpolator(chunk_points)

        chunk_start += chunk_size
        chunk_end += chunk_size
        chunk_index += 1

    # Report interpolation time
    total_time = time.perf_counter() - start_time
    total_hours, remaining_time = divmod(total_time, 3600)
    total_minutes, total_seconds = divmod(remaining_time, 60)
    time_string = (
        f"{f'{total_hours:.0f}h' if total_hours else ''}"
        f"{f'{total_minutes:>2.0f}m' if total_minutes else ''}"
        f"{total_seconds:>2.0f}s"
    )
    _module_logger.debug(f"Finished interpolation in {time_string}.")

    # Cache output
    _module_logger.debug(f"Caching interpolated array to '{cache_path}'.")
    os.makedirs(INTERPOLATED_VOLUMES_CACHE_DIRECTORY, exist_ok=True)
    with h5py.File(cache_path, "w") as handle:
        handle.create_dataset(name="array", data=interpolated_array, compression="gzip")
    append_volume(alignment_directory, cache_path, "interpolated")

    return interpolated_array


def replace_path_parts(
    path: Path,
    channel_regex: str,
    channel_substitution: str,
    projection_regex: str,
    misc_regexes: Sequence[str] = (),
    misc_subs: Sequence[str] = (),
) -> Path:
    r"""Extracts the original file name given the channel, Z indices, and optional parts.

    Careful not to trust the output of this function blindly if obtained from external
    input as `misc_regexes` and `misc_subs` can potentially replace any portion of the
    path.

    Args:
        path (Path): Path to remove parts on.
        channel_regex (str):
            Channel regex identifying the channel part of `path`'s name.
        channel_substitution (str):
            String to substitute `channel_regex` with.
        projection_regex (str):
            Projection regex identifying the projection part of `path`'s name.
        misc_regexes (Sequence[str], optional):
            Miscellaneous regex identifying extra parts of alignment paths found in
            `alignment_directory`. Use in conjunction with `misc_subs` to replace
            arbitrary parts of the path. The shortest of the two argument dictates how
            many elements are replaced. Unlike channel and projection arguments, this
            can replace any part of the path, now just the name.
        misc_subs (Sequence[str], optional):
            Miscellaneous substitutions to replace in `alignment_directory`. Use in
            conjunction with `misc_regexes` to replace arbitrary parts of the path.
            The shortest of the two argument dictates how many elements are replaced.

    Returns:
        Path: The path with the parts removed.

    Examples:
        >>> replace_path_parts(Path("/data/filename_C123_max.h5"), "C123", "C456", "_max")
        Path('/data/filename_C456.h5')
    """
    # Replace the channel name
    path = path.with_name(re.sub(channel_regex, channel_substitution, path.name))

    # Remove part of the file name that indicates the projection
    path = path.with_name(
        re.sub(projection_regex, "", path.name),
    )

    # Replace the miscellaneous parts
    for regex, sub in zip(misc_regexes, misc_subs):
        path = Path(re.sub(regex, sub, str(path)))

    return path


def append_volume(
    alignment_directory: Path,
    volume_path: Path,
    type_: Literal["aligned", "interpolated"],
) -> None:
    try:
        with open(alignment_directory.parent / "volumes.json") as handle:
            contents = json.load(handle)
    except FileNotFoundError:
        contents = {}
    except json.JSONDecodeError:
        _module_logger.error(
            f"Could not parse 'volumes.json' file for alignment directory "
            f"'{alignment_directory}'."
        )
        return

    contents[type_] = contents.get(type_, []) + [str(volume_path)]

    with open(alignment_directory.parent / "volumes.json", "w") as handle:
        json.dump(contents, handle)
