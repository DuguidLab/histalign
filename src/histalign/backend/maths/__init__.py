# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import math

from PySide6 import QtCore
import numpy as np
from scipy.spatial.transform import Rotation

from histalign.backend.models import (
    Orientation,
    VolumeSettings,
)
from histalign.backend.models.errors import InvalidOrientationError


def apply_rotation_vector(
    rotation_vector: np.ndarray,
    vector: np.ndarray,
    settings: VolumeSettings,
) -> np.ndarray:
    rotation = Rotation.from_rotvec(rotation_vector)

    offset = settings.offset
    offset_vector = vector.copy()

    # Make sure `rotation_vector` and `vector` share the same origin
    match settings.orientation:
        case Orientation.CORONAL:
            # Note that the offset doesn't need to be shifted here as the input vector
            # should have done that calculation already.
            offset_vector[0] += offset
        case Orientation.HORIZONTAL:
            offset_vector[1] -= offset
        case Orientation.SAGITTAL:
            offset_vector[2] -= offset
        case other:
            # Should be impossible thanks to pydantic
            raise InvalidOrientationError(other)

    rotated_offset_vector = rotation.apply(offset_vector)

    # Restore the offset
    match settings.orientation:
        case Orientation.CORONAL:
            rotated_offset_vector[0] -= offset
        case Orientation.HORIZONTAL:
            rotated_offset_vector[1] += offset
        case Orientation.SAGITTAL:
            rotated_offset_vector[2] += offset
        case other:
            # Should be impossible thanks to pydantic
            raise InvalidOrientationError(other)

    return rotated_offset_vector


def compute_normal(settings: VolumeSettings) -> list[float]:
    pitch_radians = math.radians(settings.pitch)
    yaw_radians = math.radians(settings.yaw)

    match settings.orientation:
        case Orientation.CORONAL:
            normal = [
                math.cos(yaw_radians) * math.cos(pitch_radians),
                -math.sin(pitch_radians),
                -math.sin(yaw_radians) * math.cos(pitch_radians),
            ]
        case Orientation.HORIZONTAL:
            normal = [
                math.sin(pitch_radians),
                math.cos(yaw_radians) * math.cos(pitch_radians),
                math.sin(yaw_radians) * math.cos(pitch_radians),
            ]
        case Orientation.SAGITTAL:
            normal = [
                math.sin(yaw_radians) * math.cos(pitch_radians),
                math.sin(pitch_radians),
                math.cos(yaw_radians) * math.cos(pitch_radians),
            ]
        case other:
            # Should be impossible thanks to pydantic
            raise InvalidOrientationError(other)

    return normal


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


def compute_rotation_vector_from_volume_settings(
    settings: VolumeSettings,
) -> np.ndarray:
    pitch_radians = math.radians(settings.pitch)
    yaw_radians = math.radians(settings.yaw)

    match settings.orientation:
        case Orientation.CORONAL:
            rotation_vector = np.array(
                [
                    0,
                    -yaw_radians,
                    pitch_radians,
                ]
            )
        case Orientation.HORIZONTAL:
            rotation_vector = np.array(
                [
                    yaw_radians,
                    0,
                    -pitch_radians,
                ]
            )
        case Orientation.SAGITTAL:
            rotation_vector = np.array(
                [
                    -pitch_radians,
                    yaw_radians,
                    0,
                ]
            )
        case other:
            # Should be impossible thanks to pydantic
            raise InvalidOrientationError(other)

    return rotation_vector


def convert_volume_coordinates_to_ccf(
    coordinates: np.ndarray, settings: VolumeSettings
) -> np.ndarray:
    # See `compute_origin_from_orientation` for explanation of why we subtract from
    # the coronal coordinate.
    match settings.orientation:
        case Orientation.CORONAL:
            converted_coordinates = np.array(
                [
                    int(settings.shape[0] // 2 - 1)
                    - coordinates[0]
                    + (settings.shape[0] % 2 == 0),
                    int(settings.shape[1] // 2 - 1) + coordinates[1],
                    int(settings.shape[2] // 2 - 1) + coordinates[2],
                ]
            )
        case Orientation.HORIZONTAL | Orientation.SAGITTAL:
            converted_coordinates = np.array(
                [
                    int(settings.shape[0] // 2 - 1)
                    + coordinates[0]
                    - (settings.shape[0] % 2 == 0),
                    int(settings.shape[1] // 2 - 1) + coordinates[1],
                    int(settings.shape[2] // 2 - 1) + coordinates[2],
                ]
            )
        case other:
            # Should be impossible thanks to pydantic
            raise InvalidOrientationError(other)

    return converted_coordinates


def convert_volume_position_to_coordinates(
    position: QtCore.QPoint | QtCore.QPointF,
    settings: VolumeSettings,
) -> np.ndarray:
    offset = settings.offset

    match settings.orientation:
        case Orientation.CORONAL:
            coordinates = [
                offset,
                round(position.y()),
                round(position.x()),
            ]
        case Orientation.HORIZONTAL:
            coordinates = [
                round(position.y()),
                offset,
                round(position.x()),
            ]
        case Orientation.SAGITTAL:
            coordinates = [
                round(position.x()),
                round(position.y()),
                offset,
            ]
        case other:
            # Should be impossible thanks to pydantic
            raise InvalidOrientationError(other)

    return np.array(coordinates)
