# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import math

import numpy as np
from PySide6 import QtCore, QtGui
from scipy.spatial.transform import Rotation
from skimage.transform import AffineTransform

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
    return compute_normal_from_raw(
        settings.pitch,
        settings.yaw,
        settings.orientation,
    )


def compute_normal_from_raw(
    pitch: int, yaw: int, orientation: Orientation
) -> np.ndarray:
    match orientation:
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


def convert_sk_transform_to_q_transform(
    transformation: AffineTransform,
) -> QtGui.QTransform:
    return QtGui.QTransform(*transformation.params.T.flatten().tolist())


def convert_volume_coordinates_to_ccf(
    coordinates: np.ndarray, settings: VolumeSettings
) -> np.ndarray:
    volume_centre = (np.array(settings.shape) - 1) // 2

    return coordinates + volume_centre


def get_sk_transform_from_parameters(
    scale: tuple[float, float] = (1.0, 1.0),
    shear: tuple[float, float] = (0.0, 0.0),
    rotation: float = 0.0,
    translation: tuple[float, float] = (0.0, 0.0),
    extra_translation: tuple[float, float] = (0.0, 0.0),
) -> AffineTransform:
    """Builds a 2D `AffineTransform` from the given parameters.

    This is equivalent to creating an `AffineTransform` from the result of this matrix
    multiplication:
        T @ R @ Sh @ Sc @ Te
    where:
        T is a 3x3 affine transform matrix from `translation`,
        R is a 3x3 affine transform matrix from `rotation`,
        Sc is a 3x3 affine transform matrix from `shear`,
        Sh is a 3x3 affine transform matrix from `scale`,
        Te is a 3x3 affine transform matrix from `extra_translation`.

    Note that unlike `AffineTransform`s `shear` parameter, the `shear` here should
    be a coordinate shift rather than an angle.

    Args:
        scale (tuple[float, float], optional): X and Y scaling factors.
        shear (tuple[float, float], optional):
            X and Y shearing factors. This is a shift in coordinates and not an angle.
        rotation (float, optional): Clockwise rotation in degrees.
        translation (tuple[float, float], optional): X and Y translation factors.
        extra_translation (tuple[float, float], optional):
            Extra translation to apply before all of the other transformations. This
            allows translating the coordinate system before applying the affine
            transform.

    Returns:
        AffineTransform: The 2D affine transform whose matrix is obtained from the given
                         parameters.
    """
    # `AffineTransform` uses shearing angles instead of coordinate shift. We therefore
    # compute the equivalent angles on the trigonometric circle. Since the shearing is
    # clockwise, the angle also needs to be inverted for positive shearing.
    x_shear_correction = -1 if shear[0] > 0 else 1
    y_shear_correction = -1 if shear[1] > 0 else 1

    shear_angles = tuple(
        (
            math.acos(
                100 / math.sqrt(100**2 + (shear[0] * 100) ** 2) * x_shear_correction
            ),
            math.acos(
                100 / math.sqrt(100**2 + (shear[1] * 100) ** 2) * y_shear_correction
            ),
        )
    )

    matrix = (
        AffineTransform(
            scale=scale,
            shear=shear_angles,
            rotation=math.radians(rotation),
            translation=translation,
        ).params
        # Apply an extra translation to move the coordinate system
        @ AffineTransform(
            translation=(extra_translation[0], extra_translation[1])
        ).params
    )

    return AffineTransform(matrix=matrix)
