# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from PySide6 import QtCore
import numpy as np
from scipy.spatial.transform import Rotation

from histalign.backend.models import (
    Orientation,
    VolumeSettings,
)
from histalign.backend.models.errors import InvalidOrientationError


def apply_rotation(
    vector: np.ndarray,
    settings: VolumeSettings,
) -> np.ndarray:
    vector = vector.copy()
    pitch = settings.pitch
    yaw = settings.yaw

    match settings.orientation:
        case Orientation.CORONAL:
            rotation = Rotation.from_euler("ZY", [pitch, yaw], degrees=True)
        case Orientation.HORIZONTAL:
            rotation = Rotation.from_euler("ZX", [pitch, yaw], degrees=True)
        case Orientation.SAGITTAL:
            rotation = Rotation.from_euler("XY", [pitch, yaw], degrees=True)
        case other:
            # Should be impossible thanks to pydantic
            raise InvalidOrientationError(other)

    rotated_vector = rotation.apply(vector)

    return np.floor(rotated_vector)


def apply_offset(vector: np.ndarray, settings: VolumeSettings) -> np.ndarray:
    vector = vector.copy()

    match settings.orientation:
        case Orientation.CORONAL:
            vector[0] += (settings.shape[0] % 2 == 0) - settings.offset
        case Orientation.HORIZONTAL:
            vector[1] += settings.offset
        case Orientation.SAGITTAL:
            vector[2] += settings.offset
        case other:
            # Should be impossible thanks to pydantic
            raise InvalidOrientationError(other)

    return vector


def compute_mesh_centre(mesh_bounds: list | np.ndarray) -> np.ndarray:
    if (isinstance(mesh_bounds, list) and len(list) != 6) or (
        isinstance(mesh_bounds, np.ndarray) and mesh_bounds.shape != (6,)
    ):
        raise ValueError(
            "Expected mesh bounds with 6 values in the form "
            "(xmin, xmax, ymin, ymax, zmin, zmax)."
        )

    return np.array(
        [
            (mesh_bounds[1] + mesh_bounds[0]) / 2,
            (mesh_bounds[3] + mesh_bounds[2]) / 2,
            (mesh_bounds[5] + mesh_bounds[4]) / 2,
        ]
    )


def compute_normal(settings: VolumeSettings) -> np.ndarray:
    pitch = settings.pitch
    yaw = settings.yaw

    match settings.orientation:
        case Orientation.CORONAL:
            normal = [-1, 0, 0]
            rotation = Rotation.from_euler("ZY", [pitch, yaw], degrees=True)
        case Orientation.HORIZONTAL:
            normal = [0, 1, 0]
            rotation = Rotation.from_euler("ZX", [pitch, yaw], degrees=True)
        case Orientation.SAGITTAL:
            normal = [0, 0, 1]
            rotation = Rotation.from_euler("XY", [pitch, yaw], degrees=True)
        case other:
            # Should be impossible thanks to pydantic
            raise InvalidOrientationError(other)

    return rotation.apply(normal)


def compute_origin_from_orientation(
    center: list[float] | tuple[float, ...], settings: VolumeSettings
) -> list[float]:
    if len(center) != 3:
        raise ValueError(f"Expected center with 3 coordinates, got {len(center)}.")

    # vedo computes the center with float precision but offset calculations assume
    # integer values.
    origin = list(map(int, center))

    match settings.orientation:
        case Orientation.CORONAL:
            # Because we want the left hemisphere on the left, we look against the
            # X-axis, so the offset has to be inverted.
            origin[0] += (settings.shape[0] % 2 == 0) - settings.offset
        case Orientation.HORIZONTAL:
            origin[1] += settings.offset
        case Orientation.SAGITTAL:
            origin[2] += settings.offset
        case other:
            # Should be impossible thanks to pydantic
            raise InvalidOrientationError(other)

    return origin


def convert_pixmap_position_to_coordinates(
    position: QtCore.QPoint | QtCore.QPointF,
    settings: VolumeSettings,
) -> np.ndarray:
    match settings.orientation:
        case Orientation.CORONAL:
            coordinates = [
                0,
                round(position.y()),
                round(position.x()),
            ]
        case Orientation.HORIZONTAL:
            coordinates = [
                round(position.y()),
                0,
                round(position.x()),
            ]
        case Orientation.SAGITTAL:
            coordinates = [
                round(position.x()),
                round(position.y()),
                0,
            ]
        case other:
            # Should be impossible thanks to pydantic
            raise InvalidOrientationError(other)

    return np.array(coordinates)


def convert_volume_coordinates_to_ccf(
    coordinates: np.ndarray, settings: VolumeSettings
) -> np.ndarray:
    volume_centre = (np.array(settings.shape) - 1) // 2

    return coordinates + volume_centre
