# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from collections.abc import Sequence
import math

import numpy as np
from PySide6 import QtGui
from scipy.spatial.transform import Rotation
from skimage.transform import AffineTransform
import vedo

from histalign.backend.models import (
    Orientation,
    VolumeSettings,
)
from histalign.backend.models.errors import InvalidOrientationError


def apply_rotation(vector: np.ndarray, settings: VolumeSettings) -> np.ndarray:
    pitch = settings.pitch
    yaw = settings.yaw
    orientation = settings.orientation

    return apply_rotation_from_raw(vector, pitch, yaw, orientation)


def apply_rotation_from_raw(
    vector: np.ndarray, pitch: int, yaw: int, orientation: Orientation
) -> np.ndarray:
    match orientation:
        case Orientation.CORONAL:
            rotation = Rotation.from_euler("ZY", [pitch, yaw], degrees=True)
        case Orientation.HORIZONTAL:
            rotation = Rotation.from_euler("ZX", [pitch, yaw], degrees=True)
        case Orientation.SAGITTAL:
            rotation = Rotation.from_euler("XY", [pitch, yaw], degrees=True)
        case other:
            raise InvalidOrientationError(other)

    return rotation.apply(vector)


def compute_centre(shape: Sequence[int], floor: bool = True) -> tuple[int | float, ...]:
    centre = tuple((np.array(shape) - 1) / 2)
    if floor:
        return tuple(map(int, centre))

    return centre


def compute_mesh_centre(mesh: vedo.Mesh) -> np.ndarray:
    bounds = mesh.metadata["original_bounds"]

    return np.array(
        [
            (bounds[1] + bounds[0]) / 2,
            (bounds[3] + bounds[2]) / 2,
            (bounds[5] + bounds[4]) / 2,
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
            normal = [1, 0, 0]
        case Orientation.HORIZONTAL:
            normal = [0, 1, 0]
        case Orientation.SAGITTAL:
            normal = [0, 0, 1]
        case other:
            raise InvalidOrientationError(other)

    return apply_rotation_from_raw(np.array(normal), pitch, yaw, orientation).reshape(3)


def compute_origin(centre: Sequence[int], settings: VolumeSettings) -> np.ndarray:
    if len(centre) != 3:
        raise ValueError(f"Centre should be 3 coordinates. Got {len(centre)}.")

    orientation = settings.orientation
    offset = settings.offset

    match orientation:
        case Orientation.CORONAL:
            origin = [centre[0] + offset, centre[1], centre[2]]
        case Orientation.HORIZONTAL:
            origin = [centre[0], centre[1] + offset, centre[2]]
        case Orientation.SAGITTAL:
            origin = [centre[0], centre[1], centre[2] + offset]
        case other:
            raise InvalidOrientationError(other)

    return np.array(origin)


def convert_sk_transform_to_q_transform(
    transformation: AffineTransform,
) -> QtGui.QTransform:
    return QtGui.QTransform(*transformation.params.T.flatten().tolist())


def convert_q_transform_to_sk_transform(
    transformation: QtGui.QTransform,
) -> AffineTransform:
    return AffineTransform(
        matrix=get_transformation_matrix_from_q_transform(transformation)
    )


def find_plane_mesh_corners(
    plane_mesh: vedo.Mesh,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Finds the corners of a plane mesh as obtained from `vedo.Volume.slice_plane`.

    Note this is only guaranteed to work with plane meshes obtained through
    `vedo.Volume.slice_plane` as the corners are obtained by index rather than by
    distance to the centre of mass.

    Args:
        plane_mesh (vedo.Mesh): Plane mesh to find the corners of.

    Returns:
        tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
            The corners of `plane_mesh`.
    """
    # vedo.Volume.slice_plane returns points in image coordinates, indexing into
    # the points works as-if indexing into the image.
    shape = plane_mesh.metadata["shape"]
    corners = plane_mesh.points[[0, shape[1] - 1, -shape[1], -1]]

    return corners


def get_transformation_matrix_from_q_transform(
    transformation: QtGui.QTransform,
    invert: bool = False,
) -> np.ndarray:
    if invert:
        transformation, success = transformation.inverted()
        if not success:
            raise ValueError("Could not invert the affine matrix.")

    # Note that the matrix indices seem to follow an XY notation instead of a classic
    # IJ matrix notation.
    return np.array(
        [
            [transformation.m11(), transformation.m21(), transformation.m31()],
            [transformation.m12(), transformation.m22(), transformation.m32()],
            [transformation.m13(), transformation.m23(), transformation.m33()],
        ]
    )


def get_sk_transform_from_parameters(
    scale: tuple[float, float] = (1.0, 1.0),
    shear: tuple[float, float] = (0.0, 0.0),
    rotation: float = 0.0,
    translation: tuple[float, float] = (0.0, 0.0),
    extra_translation: tuple[float, float] = (0.0, 0.0),
    undo_extra: bool = False,
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
        undo_extra (bool, optional):
            Whether to undo the extra translation to return the coordinate system to
            normal.


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

    if undo_extra:
        # Move the coordinate system back
        matrix = (
            AffineTransform(
                translation=(
                    -extra_translation[0],
                    -extra_translation[1],
                )
            )
            @ matrix
        )

    return AffineTransform(matrix=matrix)


def signed_vector_angle(
    vector1: np.ndarray, vector2: np.ndarray, axis: np.ndarray
) -> float:
    return math.degrees(
        math.atan2(np.dot((np.cross(vector1, vector2)), axis), np.dot(vector1, vector2))
    )
