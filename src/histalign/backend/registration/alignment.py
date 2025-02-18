# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import hashlib
import logging
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Optional

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


def build_aligned_volume(
    alignment_directory: str | Path,
    allow_cache_load: bool = True,
    allow_cache_save: bool = True,
    return_raw_array: bool = False,
    channel_index: Optional[int] = None,
    channel_regex: Optional[str] = None,
    projection_regex: Optional[str] = None,
    misc_regexes: Optional[str | list[str]] = None,
    misc_subs: Optional[str | list[str]] = None,
) -> tuple[np.ndarray | vedo.Volume, Path]:
    """Builds an aligned volume from alignment settings.

    Args:
        alignment_directory (str | Path):
        allow_cache_load (bool, optional):
            Whether to use the cache for loading. If `False`, the entire volume is
            guaranteed to be build from scratch. If `True`, the cache will be queried
            for an existing volume created with the same alignment paths. If one exists,
            it is returned. Otherwise, the volume is built as normal.
        allow_cache_save (bool, optional):
            Whether to save the built volume to the cache.
        return_raw_array (bool, optional):
            Whether to return a numpy array (`True`) or a vedo volume (`False`).
        channel_index (Optional[int], optional):
            Channel index to use when retrieving the original files.
        channel_regex (Optional[str], optional):
            Channel regex identifying the channel part of alignment paths' names found
            in `alignment_directory`.
        projection_regex (Optional[str], optional):
            Projection regex identifying the projection part of alignment paths' names
            found in `alignment_directory`.
        misc_regexes (Optional[list[str]], optional):
            Miscellaneous regexes identifying extra parts of alignment paths found in
            `alignment_directory`.
        misc_subs (Optional[list[str]], optional):
            Substitutions to replace `misc_regexes` with. This should have as many
            elements as `misc_regexes`.

    Returns:
        tuple[np.ndarray | vedo.Volume, Path]:
            The aligned volume or 3D array, and the path to the potential cache.
    """
    _module_logger.debug("Starting build of aligned volume.")

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

    if isinstance(alignment_directory, str):
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

    alignment_hash = generate_hash_from_targets(
        [settings.histology_path for settings in alignment_settings_list]
    )

    cache_path = ALIGNMENT_VOLUMES_CACHE_DIRECTORY / f"{alignment_hash}.npz"
    if cache_path.exists() and allow_cache_load:
        _module_logger.debug("Found cached aligned volume. Loading from file.")

        array = np.load(cache_path)["array"]
        if return_raw_array:
            return array, cache_path
        return vedo.Volume(array), cache_path

    reference_shape = alignment_settings_list[0].volume_settings.shape

    # Volume needs to be created before array as vedo makes a copy
    aligned_volume = vedo.Volume(np.zeros(shape=reference_shape, dtype=np.uint16))
    aligned_array = aligned_volume.tonumpy()

    planes = generate_aligned_planes(aligned_volume, alignment_settings_list)

    insert_aligned_planes_into_array(aligned_array, planes)
    aligned_volume.modified()  # Probably unnecessary but good practice

    if allow_cache_save:
        _module_logger.debug("Caching volume to file as a NumPy array.")
        os.makedirs(ALIGNMENT_VOLUMES_CACHE_DIRECTORY, exist_ok=True)
        np.savez_compressed(cache_path, array=aligned_array)

    if return_raw_array:
        return aligned_array, cache_path
    return aligned_volume, cache_path


def insert_aligned_planes_into_array(
    array: np.ndarray,
    planes: list[vedo.Mesh],
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
) -> list[vedo.Mesh]:
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
) -> vedo.Mesh:
    """Creates a plane mesh from an image and its alignment settings.

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
            The plane whose scalar point data has been filled with the values of `image.`
    """
    registrator = Registrator(True, True)
    registered_slice = registrator.get_forwarded_image(
        image, alignment_settings, origin
    )

    plane_mesh = slicer.slice(
        alignment_settings.volume_settings, origin=origin, return_mesh=True
    )

    registered_slice = undo_padding(registered_slice, plane_mesh)

    plane_mesh.pointdata["ImageScalars"] = registered_slice.flatten()

    return plane_mesh


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


def undo_padding(image: np.ndarray, mesh: vedo.Mesh) -> np.ndarray:
    """Undoes the padding added during registration.

    Args:
        image (np.ndarray): Registered image.
        mesh (vedo.Mesh):
            Mesh containing the padding information. This should be included in a
            metadata field. See `histalign.backend.registration.Registrator`.

    Returns:
        np.ndarray: The image without padding.
    """
    unpadded_image = image[
        mesh.metadata["i_padding"][0] : image.shape[0] - mesh.metadata["i_padding"][1],
        mesh.metadata["j_padding"][0] : image.shape[1] - mesh.metadata["j_padding"][1],
    ]

    return unpadded_image


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
    reference_mask: Optional[np.ndarray] = None,
    pre_masked: bool = False,
    kernel: str = "multiquadric",
    neighbours: int = 27,
    epsilon: int = 1,
    degree: Optional[int] = None,
    chunk_size: Optional[int] = 1_000_000,
    recursive: bool = False,
    use_cache: bool = False,
    aligned_volume_hash: str = "",
    mask_name: str = "",
) -> tuple[np.ndarray, Path]:
    start_time = time.perf_counter()

    if use_cache and not aligned_volume_hash:
        raise ValueError("Cannot use cache without a starting 'aligned_volume_hash'.")
    if use_cache and reference_mask is not None and not mask_name:
        raise ValueError(
            "Cannot use cache with reference mask but no 'mask_name' "
            "identifying information."
        )

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

    mask_name = "-".join(mask_name.split(" ")).lower()
    if mask_name:
        mask_name = "_" + mask_name

    cache_path = (
        INTERPOLATED_VOLUMES_CACHE_DIRECTORY / f"{aligned_volume_hash}{mask_name}"
        f"_{kernel}_{neighbours}_{epsilon}_{degree or 0}_{int(recursive)}.npz"
    )
    if cache_path.exists() and use_cache:
        _module_logger.debug("Found cached array. Loading from file.")

        return np.load(cache_path)["array"], cache_path

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

    if use_cache:
        _module_logger.debug("Caching interpolated array to file.")
        os.makedirs(INTERPOLATED_VOLUMES_CACHE_DIRECTORY, exist_ok=True)
        np.savez_compressed(cache_path, array=interpolated_array)

    return interpolated_array, cache_path


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
    channel_index: Optional[int] = None,
    channel_regex: Optional[str] = None,
    projection_regex: Optional[str] = None,
    misc_regexes: Optional[list[str]] = None,
    misc_subs: Optional[list[str]] = None,
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
    channel_index: Optional[int] = None,
    channel_regex: Optional[str] = None,
    projection_regex: Optional[str] = None,
    misc_regexes: Optional[list[str]] = None,
    misc_subs: Optional[list[str]] = None,
) -> Path:
    """Extracts the original file name given the channel, Z indices, and optional parts.

    Careful not to trust the output of this function blindly if obtained from external
    input as `misc_regexes` and `misc_subs` can potentially replace the whole path.

    Args:
        path (Path): Path to remove parts on.
        channel_index (Optional[int], optional):
            Channel index to use in the returned path.
        channel_regex (Optional[str], optional):
            Channel regex identifying the channel part of `path`'s name.
        projection_regex (Optional[str], optional):
            Projection regex identifying the projection part of `path`'s name.
        misc_regexes (Optional[list[str]], optional):
            Miscellaneous regex identifying an extra part of alignment paths found in
            `alignment_directory`.
        misc_subs (Optional[list[str]], optional):
            Substitutions to replace `misc_regexes` with. This should have as many
            elements as `misc_regexes`.

    Returns:
        Path: The path with the parts removed.

    Examples:
        >>> replace_path_parts(Path("/data/filename_C0_max.h5"), 1, r"_C\d_", "_max")
        Path('/data/filename_C0.h5')
    """
    # Replace the channel index
    if channel_regex is not None:
        if channel_index is not None:
            path = path.with_name(
                re.sub(
                    channel_regex,
                    channel_regex.replace(r"\d", str(channel_index)),
                    path.name,
                    count=1,
                )
            )

    # Remove part of the file name that indicates the projection
    if projection_regex is not None:
        path = path.with_name(
            re.sub(projection_regex, "", path.name, count=1),
        )

    # Replace the miscellaneous parts
    if misc_regexes is not None and misc_subs is not None:
        if (len1 := len(misc_regexes)) != (len2 := len(misc_subs)):
            _module_logger.error(
                f"Received different numbers of misc regex and subs "
                f"({len1} vs {len2}). Skipping miscellaneous replacement."
            )
        else:
            for i in range(len(misc_regexes)):
                path = Path(
                    re.sub(misc_regexes[i], misc_subs[i], str(path)),
                )

    return path


def generate_hash_from_targets(targets: list[Path]) -> str:
    return hashlib.md5("".join(map(str, targets)).encode("UTF-8")).hexdigest()


def generate_hash_from_aligned_volume_settings(settings: list[Any]) -> str:
    return hashlib.md5("".join(map(str, settings)).encode("UTF-8")).hexdigest()
