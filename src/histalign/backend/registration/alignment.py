# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from collections.abc import Sequence
import hashlib
import logging
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Optional

import h5py
import numpy as np
import pydantic
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
from histalign.backend.maths import (
    compute_centre,
    compute_normal,
    compute_normal_from_raw,
    compute_origin,
)
from histalign.backend.models import AlignmentSettings, Orientation, Resolution
from histalign.backend.registration import Registrator
from histalign.backend.workspace import Volume, VolumeSlicer

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
    channel_index: str,
    channel_regex: str,
    projection_regex: str,
    misc_regexes: Sequence[str] = (),
    misc_subs: Sequence[str] = (),
) -> None:
    """Builds a 3D aligned array from alignment settings.

    Args:
        alignment_directory (str | Path):
            Path to the directory containing the alignment settings of the images to use
            to build the array.
        channel_index (str):
            Channel index to use in the returned path.
        channel_regex (str):
            Channel regex identifying the channel part of `path`'s name.
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
    """
    _module_logger.debug("Starting build of aligned array.")

    if channel_regex is not None and channel_index is None:
        _module_logger.warning(
            "Received channel regex but no channel index. Building alignment "
            "volume using the same channel as was used for alignment."
        )
    elif channel_regex is None and channel_index is not None:
        _module_logger.warning(
            "Received channel index but no channel regex. Building alignment "
            "volume using the same channel as was used for alignment."
        )

    alignment_directory = Path(alignment_directory)

    alignment_paths = gather_alignment_paths(alignment_directory)
    if not alignment_paths:
        raise ValueError("Cannot build aligned volume from empty alignment directory.")

    alignment_settings_list = convert_alignment_histology_paths(
        alignment_paths,
        channel_index,
        channel_regex,
        projection_regex,
        misc_regexes,
        misc_subs,
    )

    cache_path = ALIGNMENT_VOLUMES_CACHE_DIRECTORY / f"{alignment_directory.name}.h5"
    if cache_path.exists():
        return

    reference_shape = alignment_settings_list[0].volume_settings.shape

    # Volume needs to be created before array as vedo makes a copy
    aligned_volume = vedo.Volume(np.zeros(shape=reference_shape, dtype=np.uint16))
    aligned_array = aligned_volume.tonumpy()

    planes = generate_aligned_planes(aligned_volume, alignment_settings_list)

    insert_aligned_planes_into_array(aligned_array, planes)
    aligned_volume.modified()  # Probably unnecessary but good practice

    _module_logger.debug("Caching volume to file as a NumPy array.")
    os.makedirs(ALIGNMENT_VOLUMES_CACHE_DIRECTORY, exist_ok=True)
    with h5py.File(cache_path, "w") as handle:
        handle.create_dataset(name="array", data=aligned_array, compression="gzip")


def insert_aligned_planes_into_array(
    array: np.ndarray,
    planes: list[vedo.Points],
    inplace: bool = True,
) -> np.ndarray:
    """Inserts aligned planes into a 3D numpy array.

    Args:
        array (np.ndarray): Array to insert into.
        planes (list[vedo.Mesh]): Planes to insert.
        inplace (bool, optional): Whether to modify `array` in-place.

    Returns:
        np.ndarray:
            `array` if `inplace` is `True`, else a copy, with the planes inserted.
    """
    _module_logger.debug(
        f"Starting insertion of {len(planes)} planes into alignment array."
    )

    if not inplace:
        array = array.copy()

    for index, plane in enumerate(planes):
        if index > 0 and index % 5 == 0:
            _module_logger.debug(f"Inserted {index} planes into alignment array...")

        temporary_volume = vedo.Volume(np.zeros_like(array))
        temporary_volume.interpolate_data_from(plane, radius=1)

        temporary_array = temporary_volume.tonumpy()
        temporary_array = np.round(temporary_array).astype(np.uint16)

        array[:] = np.maximum(array, temporary_array)

    _module_logger.debug(
        f"Finished inserting all {len(planes)} planes into alignment array."
    )

    return array


def generate_aligned_planes(
    alignment_volume: Volume | vedo.Volume,
    alignment_settings: list[AlignmentSettings],
) -> list[vedo.Points]:
    """Generates aligned planes for each image (2D or 3D) from the alignment paths.

    Args:
        alignment_volume (Volume | vedo.Volume): Volume to generate planes for.
        alignment_settings (list[AlignmentSettings):
            List of alignment settings to use to generate planes.

    Returns:
        list[vedo.Mesh]:
            A list of all the aligned planes obtained from the alignment paths.
    """
    _module_logger.debug(f"Starting generation of aligned planes.")

    planes = []
    slicer = VolumeSlicer(volume=alignment_volume)

    for index, alignment_settings in enumerate(alignment_settings):
        if index > 0 and index % 5 == 0:
            _module_logger.debug(
                f"Generating plane(s) for {alignment_settings.histology_path.name}..."
            )

        image_array = load_image(alignment_settings.histology_path, allow_stack=True)

        projections_map = snap_array_to_grid(image_array, alignment_settings)
        for origin, projection in projections_map.items():
            planes.append(
                get_plane_from_2d_image(
                    projection, alignment_settings, origin=list(origin), slicer=slicer
                )
            )

    _module_logger.debug(f"Finished generating all aligned planes.")
    return planes


def get_plane_from_2d_image(
    image: np.ndarray,
    alignment_settings: AlignmentSettings,
    slicer: VolumeSlicer,
    origin: Optional[list[float]] = None,
) -> vedo.Points:
    """Creates a plane-like points object from an image and its alignment settings.

    Args:
        image (np.ndarray): Scalar information for the plane.
        alignment_settings (AlignmentSettings): Settings used for the alignment.
        slicer (VolumeSlicer): Volume slicer from which to obtain the plane.
        origin (Optional[list[float]], optional):
            Origin to use when slicing the volume slicer. If not provided, the centre
            of the volume along the non-orientation axes is used (e.g., centre along YZ
            when working coronally).

    Returns:
        vedo.Mesh:
            The plane with scalar point data filled with the values of `image`.
    """
    registrator = Registrator(True, True)
    registered_slice = registrator.get_forwarded_image(
        image, alignment_settings, origin
    )

    display_plane = slicer.slice(
        alignment_settings.volume_settings, origin=origin, return_display_plane=True
    )
    data_points = generate_points_for_plane(display_plane, registered_slice.shape)

    data_points.pointdata["ImageScalars"] = registered_slice.flatten()

    return data_points


def generate_points_for_plane(plane: vedo.Plane, shape: tuple[int, ...]) -> vedo.Points:
    origin = plane.points[1]

    normal1 = (plane.points[0] - plane.points[1]) / shape[0]
    normal2 = (plane.points[3] - plane.points[1]) / shape[1]

    xi, yi = np.meshgrid(
        np.linspace(0, shape[0], shape[0]), np.linspace(0, shape[1], shape[1])
    )

    points = np.vstack([xi.ravel(), yi.ravel()])
    points = np.dot(np.vstack((normal1, normal2)).T, points).T

    points = origin + points

    return vedo.Points(points)


def snap_array_to_grid(
    image_array: np.ndarray, alignment_settings: AlignmentSettings
) -> dict[CoordinatesTuple, Projection]:
    """Snaps a 2D or 3D array to a grid.

    Args:
        image_array (np.ndarray): Array to snap. This can be a single image (2D) or a stack (3D).
        alignment_settings (AlignmentSettings): Settings used for the alignment.

    Returns:
        dict[CoordinatesTuple, Projection]:
            A dictionary mapping grid coordinates to a sub-projection. In the case of a 2D image,
            the dictionary has one key and one value. In the case of a stack, each image of the
            stack is snapped to the closest grid coordinate. When multiple images are snapped
            to the same grid point, their maximum intensity projection is taken.
    """
    dimension_count = len(image_array.shape)
    if dimension_count < 2 or dimension_count > 3:
        raise ValueError(
            f"Unexpected shape of image array. Expected 2 or 3 dimensions, "
            f"got {dimension_count}."
        )

    if dimension_count == 3:
        # Z-stacks require a lot more work
        return _snap_stack_to_grid(image_array, alignment_settings)

    alignment_origin = compute_origin(
        compute_centre(alignment_settings.volume_settings.shape),
        alignment_settings.volume_settings,
    )
    alignment_origin = tuple(map(float, alignment_origin))

    return {alignment_origin: image_array}


def _snap_stack_to_grid(
    image_stack: np.ndarray, alignment_settings: AlignmentSettings
) -> dict[CoordinatesTuple, Projection]:
    """Snaps a Z stack to a grid through sub-projections.

    Args:
        image_stack (np.ndarray):
            Image array of the stack. The first dimension should be the stack index.
        alignment_settings (AlignmentSettings): Settings used for the alignment.

    Returns:
        dict[CoordinatesTuple, Projection]:
            A dictionary mapping grid coordinates to a sub-projection.
    """
    match alignment_settings.volume_settings.orientation:
        case Orientation.CORONAL:
            orientation_axis_length = alignment_settings.volume_settings.shape[0]
        case Orientation.HORIZONTAL:
            orientation_axis_length = alignment_settings.volume_settings.shape[1]
        case Orientation.SAGITTAL:
            orientation_axis_length = alignment_settings.volume_settings.shape[2]
        case other:
            raise Exception(f"ASSERT NOT REACHED ({other})")

    # Normal as-if no pitch or yaw are applied
    flat_normal = compute_normal_from_raw(
        0, 0, alignment_settings.volume_settings.orientation
    )

    # Points describing the normal using the aligned pitch and yaw
    normal_line_points = get_normal_line_points(alignment_settings)
    # Origin of the aligned image based on the offset
    alignment_origin = compute_origin(
        compute_centre(alignment_settings.volume_settings.shape),
        alignment_settings.volume_settings,
    )
    # Normal of the plane used for alignment
    alignment_normal = compute_normal(alignment_settings.volume_settings)

    # Intersection of the normal line and every plane orthogonal to flat normal
    free_floating_intersections = [
        vedo.Plane(
            pos=i * np.abs(flat_normal),
            normal=flat_normal,
            s=(1_000_000, 1_000_000),
        ).intersect_with_line(
            np.squeeze(normal_line_points[0]),
            np.squeeze(normal_line_points[1]),
        )
        for i in range(orientation_axis_length)
    ]
    # Intersections snapped to the closest grid point of the volume
    snapped_intersections = [
        snap_coordinates(point) for point in free_floating_intersections
    ]

    # Mock up a plane for each snapped intersection
    snapped_planes = [
        vedo.Plane(
            pos=np.squeeze(point), normal=alignment_normal, s=(1_000_000, 1_000_000)
        )
        for point in snapped_intersections
    ]

    # Mock up a plane for each Z-index of the stack
    # TODO: Obtain the real spacing
    z_distance = alignment_settings.volume_settings.resolution.value
    stack_spacing = z_distance / alignment_settings.volume_settings.resolution.value
    stack_planes = [
        vedo.Plane(
            pos=alignment_origin + i * alignment_normal * stack_spacing,
            normal=alignment_normal,
            s=(1_000_000, 1_000_000),
        )
        for i in range(-image_stack.shape[0] // 2 + 1, image_stack.shape[0] // 2 + 1)
    ]

    # Group Z-indices based on closest snapped intersection
    groups = compute_closest_plane(stack_planes, snapped_planes)

    # Find the coordinates of the Z indices
    coordinates = np.array(snapped_intersections)
    sub_projection_coordinates = []
    previous_group = None
    for index, group in enumerate(groups):
        if group == previous_group:
            continue
        previous_group = group

        sub_projection_coordinates.append(coordinates[group])

    # Sub-project
    # TODO: Translate the sub-projections so that their centre is moved away from the
    #       snapped points, back to where the alignment normal predicted them.
    #       This could be done using the intersections of the snapped planes and the
    #       normal line.
    sub_projections = sub_project_image_stack(image_stack, groups)

    return {
        tuple(np.squeeze(sub_projection_coordinates[i])): sub_projections[i]
        for i in range(len(sub_projection_coordinates))
    }


def compute_closest_plane(
    target_planes: list[vedo.Plane], fixed_planes: list[vedo.Plane]
) -> list[int]:
    """Computes the index of the closest fixed plane for each target plane.

    Args:
        target_planes (list[vedo.Plane]): Planes to compute the distances for.
        fixed_planes (list[vedo.Plane]): Planes to compute the distances with.

    Returns:
        list[int]: Indices of the closest fixed plane for each target plane.
    """
    groups = []
    for plane in target_planes:
        distances = list(map(plane.distance_to, fixed_planes))
        distances = list(map(np.max, distances))
        groups.append(distances.index(min(distances)))

    return groups


def snap_coordinates(coordinates: Coordinates) -> Coordinates:
    """Snaps float coordinates to an integer grid by rounding.

    Args:
        coordinates (Coordinates): Float coordinates to snap.

    Returns:
        Coordinates: The coordinates snapped to the grid.
    """
    return np.round(coordinates)


def sub_project_image_stack(
    image_stack: np.ndarray, groups: list[int]
) -> list[np.ndarray]:
    """Projects arrays based on their group.

    Each group will have a projection of all the images than belong to that group.

    Args:
        image_stack (np.ndarray):
            Image array to sub-project. This must be a 3D array whose first dimension is
            the Z index.
        groups (list[int]): Groups each index in the stack belongs to.

    Returns:
        list[np.ndarray]:
            The list of sub-projections. Each unique group ID will have a single
            projection. The projections are returned in the order of encountered groups.
    """
    sub_projections = []

    previous_group = None
    for group in groups:
        if group == previous_group:
            continue
        previous_group = group

        sub_stack = image_stack[np.where(np.array(groups) == group)]
        # TODO: Get projection type from user
        sub_projection = np.max(sub_stack, axis=0)
        sub_projections.append(sub_projection)

    return sub_projections


def get_normal_line_points(
    alignment_settings: AlignmentSettings,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute points describing normal passing through volume centre.

    Args:
        alignment_settings (AlignmentSettings):
            Settings used for the alignment.

    Returns:

    """
    alignment_normal = compute_normal(alignment_settings.volume_settings)

    alignment_origin = compute_origin(
        compute_centre(alignment_settings.volume_settings.shape),
        alignment_settings.volume_settings,
    )
    intersection_line_coordinates = (
        alignment_origin - 1_000_000 * alignment_normal,
        alignment_origin + 1_000_000 * alignment_normal,
    )
    return intersection_line_coordinates


def interpolate_sparse_3d_array(
    array: np.ndarray,
    resolution: Resolution,
    base_hash: str,
    mask_name: str = "root",
    only_mask: bool = True,
    kernel: str = "multiquadric",
    neighbours: int = 27,
    epsilon: int = 1,
    degree: Optional[int] = None,
    chunk_size: Optional[int] = 1_000_000,
) -> np.ndarray:
    start_time = time.perf_counter()

    # Inspect cache and return if exists
    _mask_name = "_" + "-".join(mask_name.split(" ")).lower()
    cache_path = (
        INTERPOLATED_VOLUMES_CACHE_DIRECTORY
        / f"{base_hash}{_mask_name}_{kernel}_{neighbours}_{epsilon}_{degree or 0}.h5"
    )
    if cache_path.exists():
        _module_logger.debug("Found cached array. Loading from file.")
        with h5py.File(cache_path, "r") as handle:
            array = handle["array"][:]
        return array

    # Load the mask
    mask_path = get_structure_mask_path(mask_name, resolution)
    if not Path(mask_path).exists():
        download_structure_mask(mask_path, resolution=resolution)
    mask_array = load_volume(mask_path, return_raw_array=True)

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

    return interpolated_array


def mask_off_structure(
    volume: vedo.Volume, structure_name: str, resolution: Resolution
) -> vedo.Volume:
    mask_path = get_structure_mask_path(structure_name, Resolution(resolution))
    if not Path(mask_path).exists():
        download_structure_mask(structure_name, resolution)

    mask_volume = load_volume(mask_path)

    return vedo.Volume(np.where(mask_volume.tonumpy() > 0, volume.tonumpy(), 0))


def convert_alignment_histology_paths(
    alignment_paths: list[Path],
    channel_index: str,
    channel_regex: str,
    projection_regex: str,
    misc_regexes: Sequence[str] = (),
    misc_subs: Sequence[str] = (),
) -> list[AlignmentSettings]:
    alignment_settings_list = []
    for alignment_path in alignment_paths:
        alignment_settings = load_alignment_settings(alignment_path)

        histology_path = replace_path_parts(
            alignment_settings.histology_path,
            channel_index,
            channel_regex,
            projection_regex,
            misc_regexes,
            misc_subs,
        )

        try:
            alignment_settings.histology_path = histology_path
            alignment_settings_list.append(alignment_settings)
        except pydantic.ValidationError:
            _module_logger.warning(
                f"Converted path does not exist. "
                f"Original: '{alignment_settings.histology_path}'. "
                f"Converted: '{histology_path}'."
            )

    return alignment_settings_list


def replace_path_parts(
    path: Path,
    channel_index: str,
    channel_regex: str,
    projection_regex: str,
    misc_regexes: Sequence[str] = (),
    misc_subs: Sequence[str] = (),
) -> Path:
    """Extracts the original file name given the channel, Z indices, and optional parts.

    Careful not to trust the output of this function blindly if obtained from external
    input as `misc_regexes` and `misc_subs` can potentially replace any portion of the
    path.

    Args:
        path (Path): Path to remove parts on.
        channel_index (str):
            Channel index to use in the returned path.
        channel_regex (str):
            Channel regex identifying the channel part of `path`'s name.
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
        >>> replace_path_parts(Path("/data/filename_C0_max.h5"), 1, r"_C\d_", "_max")
        Path('/data/filename_C0.h5')
    """
    # Replace the channel index
    path = path.with_name(
        re.sub(
            channel_regex,
            channel_regex.replace(r"\d", str(channel_index)),
            path.name,
            count=1,
        )
    )

    # Remove part of the file name that indicates the projection
    path = path.with_name(
        re.sub(
            projection_regex,
            "",
            path.name,
            count=1,
        ),
    )

    # Replace the miscellaneous parts
    for regex, sub in zip(misc_regexes, misc_subs):
        path = Path(re.sub(regex, sub, str(path)))

    return path


def generate_hash_from_targets(targets: list[Path]) -> str:
    return hashlib.md5("".join(map(str, targets)).encode("UTF-8")).hexdigest()


def generate_hash_from_aligned_volume_settings(settings: list[Any]) -> str:
    return hashlib.md5("".join(map(str, settings)).encode("UTF-8")).hexdigest()
