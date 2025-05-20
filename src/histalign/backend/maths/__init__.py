# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

"""This modules handles most of the math-centered operations of the package."""

from collections.abc import Sequence
import logging
import math
from typing import Optional

import numpy as np
from PySide6 import QtGui
from scipy.spatial.transform import Rotation
from skimage.transform import AffineTransform
import vedo

from histalign.backend.array_operations import get_dtype_maximum
from histalign.backend.models import (
    Orientation,
    VolumeSettings,
)
from histalign.backend.models.errors import InvalidOrientationError

_module_logger = logging.getLogger(__name__)


def apply_rotation(vector: np.ndarray, settings: VolumeSettings) -> np.ndarray:
    """Rotates a 3D vector by the recreating the rotation from alignment settings.

    Args:
        vector (np.ndarray): 3D vector to rotate.
        settings (VolumeSettings): Alignment settings to use.

    Returns:
        The rotated vector.
    """
    pitch = settings.pitch
    yaw = settings.yaw
    orientation = settings.orientation

    return apply_rotation_from_raw(vector, pitch, yaw, orientation)


def apply_rotation_from_raw(
    vector: np.ndarray, pitch: int, yaw: int, orientation: Orientation
) -> np.ndarray:
    """Rotates a 3D vector using the provided pitch, yaw, and orientation.

    Args:
        vector (np.ndarray): 3D vector to rotate.
        pitch (int): Pitch of the view.
        yaw (int): Yaw of the view.
        orientation (Orientation): Orientation of the view.

    Returns:
        The rotated vector.
    """
    match orientation:
        case Orientation.CORONAL:
            rotation = Rotation.from_euler("ZY", [pitch, yaw], degrees=True)
        case Orientation.HORIZONTAL:
            rotation = Rotation.from_euler("ZX", [pitch, yaw], degrees=True)
        case Orientation.SAGITTAL:
            rotation = Rotation.from_euler("XY", [pitch, yaw], degrees=True)
        case other:
            raise InvalidOrientationError(other)

    rotated: np.ndarray = rotation.apply(vector)
    return rotated


def compute_centre(shape: Sequence[int], floor: bool = True) -> tuple[int | float, ...]:
    """Computes the centre coordinate of a array given its shape.

    Args:
        shape (Sequence[int]): Shape of the array.
        floor (bool, optional): Whether to return an integer centre or keep it as float.

    Returns:
        The centre coordinate of the array.
    """
    centre = tuple((np.array(shape) - 1) / 2)
    if floor:
        return tuple(map(int, centre))

    return centre


def compute_mesh_centre(mesh: vedo.Mesh) -> np.ndarray:
    """Computes the centre of a mesh.

    Args:
        mesh (vedo.Mesh): Mesh to find the centre of.

    Returns:
        The centre coordinate of the mesh.
    """
    bounds = mesh.metadata["original_bounds"]

    return np.array(
        [
            (bounds[1] + bounds[0]) / 2,
            (bounds[3] + bounds[2]) / 2,
            (bounds[5] + bounds[4]) / 2,
        ]
    )


def compute_normal(settings: VolumeSettings) -> np.ndarray:
    """Computes the normal to the view plane from the alignment settings.

    Args:
        settings (VolumeSettings): Alignment settings to use.

    Returns:
        Normal to the view plane.
    """
    return compute_normal_from_raw(
        settings.pitch,
        settings.yaw,
        settings.orientation,
    )


def compute_normal_from_raw(
    pitch: int, yaw: int, orientation: Orientation
) -> np.ndarray:
    """Computes the normal to the view plane using the provided parameters.

    Args:
        pitch (int): Pitch of the view.
        yaw (int): Yaw of the view.
        orientation (Orientation): Orientation of the view.

    Returns:
        Normal to the view plane.
    """
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


def compute_origin(centre: Sequence[float], settings: VolumeSettings) -> np.ndarray:
    """Computes the view plane origin from the given centre and settings.

    Args:
        centre (Sequence[float]): Centre to work from.
        settings (VolumeSettings): Alignment settings to use.

    Returns:
        The origin computed from the centre and the alignment offset.
    """
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
    """Converts an skimage AffineTransform to a PySide QTransform.

    Args:
        transformation (AffineTransform): Transform object to convert.

    Returns:
        The equivalent QTransform to the input AffineTransform.
    """
    return QtGui.QTransform(*transformation.params.T.flatten().tolist())


def convert_q_transform_to_sk_transform(
    transformation: QtGui.QTransform,
) -> AffineTransform:
    """Converts a PySide QTransform to an skimage AffineTransform.

    Args:
        transformation (QtGui.QTransform): Transform object to convert.

    Returns:
        The equivalent AffineTransform to the input QTransform.
    """
    return AffineTransform(
        matrix=get_transformation_matrix_from_q_transform(transformation)
    )


def decompose_sk_transform(transform: AffineTransform) -> tuple[float, ...]:
    """Decomposes an `AffineTransform` into its components.

    Although `AffineTransform` has properties to decompose its matrix, the sign of the
    scaling is not extracted. This function essentially wraps property calls for its
    properties but manages to compute the sign of the scaling.

    Knowing the sign of the scaling is necessary when decomposing a matrix obtained from
    landmark registration as the GUI spin boxes need to be updated with values that the
    user can then further tweak.

    Args:
        transform (AffineTransform): Affine transform to decompose.

    Returns:
        The (scale_x, scale_y, shear_x, shear_y, rotation, translation_x, translation_y)
            components of the transformation matrix. Note that rotation is returned in
            degrees, shear_x is the factor, not the angle, and shear_y is always 0.

    References:
        Formulas for signed scaling decomposition: https://stackoverflow.com/a/45392997
    """
    mirrored = math.cos(transform.shear) < 0

    scale_x, scale_y = transform.scale
    scale_y *= -1 if mirrored else 1

    # Shear requires some more computation as scikit-image returns an angle and Qt
    # expects a coordinate shift.
    # See `maths.get_sk_transform_from_parameters` for more details.
    shear_x = transform.shear
    # This formula is obtained from rearranging CAH (SOHCAHTOA) to find A which
    # corresponds to the coordinate shift derived from the shearing angle.
    shear_x = math.sqrt((1 / math.cos(shear_x)) ** 2 - 1)
    shear_x *= -1 if transform.shear > 0 else 1
    shear_x *= -1 if mirrored else 1

    rotation = math.degrees(transform.rotation)

    translation_x, translation_y = transform.translation

    return scale_x, scale_y, shear_x, 0, rotation, translation_x, translation_y


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
        The corners of `plane_mesh`.
    """
    # vedo.Volume.slice_plane returns points in image coordinates, indexing into
    # the points works as-if indexing into the image.
    shape = plane_mesh.metadata["shape"]
    corners: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] = plane_mesh.points[
        [0, shape[1] - 1, -shape[1], -1]
    ]

    return corners


def get_transformation_matrix_from_q_transform(
    transformation: QtGui.QTransform,
    invert: bool = False,
) -> np.ndarray:
    """Retrieves the transformation matrix from a QTransform object.

    Args:
        transformation (QtGui.QTransform): Transform object to retrieve the matrix of.
        invert (bool): Whether to invert the matrix.

    Returns:
        The transformation matrix.
    """
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
        The 2D affine transform whose matrix is obtained from the given parameters.
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


def normalise_array(array: np.ndarray, dtype: Optional[np.dtype] = None) -> np.ndarray:
    """Normalise an array to the range between 0 and the dtype's maximum value.

    Args:
        array (np.ndarray): Array to normalise.
        dtype (np.dtype, optional):
            Target dtype. If `None`, the dtype will be inferred as the dtype of `array`.

    Returns:
        The normalised array.
    """
    dtype = dtype or array.dtype
    maximum = get_dtype_maximum(dtype)

    array = array.astype(np.float64)
    array -= array.min()
    array /= array.max()
    array *= maximum

    return array.astype(dtype)


def signed_vector_angle(
    vector1: np.ndarray, vector2: np.ndarray, axis: np.ndarray
) -> float:
    """Computes the signed vector angle between two vectors using the right-hand rule.

    Args:
        vector1 (np.ndarray): First vector.
        vector2 (np.ndarray): Second vector.
        axis (np.ndarray): Axis from which to determine the sign of the angle.

    Returns:
        The signed angle between the two vectors.
    """
    return math.degrees(
        math.atan2(np.dot((np.cross(vector1, vector2)), axis), np.dot(vector1, vector2))
    )


def simulate_auto_contrast_passes(
    image: np.ndarray, passes: int = 1, normalise: bool = True, inplace: bool = False
) -> tuple[np.ndarray, bool]:
    """Apply the ImageJ auto-contrast algorithm to an image.

    Args:
        image (np.ndarray): Image to apply the algorithm to.
        passes (int, optional): How many passes to simulate. This correspond to how
                                many presses of the "auto" button will be simulated.
        normalise (bool, optional): Whether to normalise the image values to the full
                                    range allowed by its dtype after applying the auto
                                    contrast.
        inplace (bool, optional): Whether to carry out the modification in place.

    Returns:
        A tuple of (`new_image`, `success`) where `new_image` is the result of applying
            `passes` number of passes on `image` using the auto-contrast algorithm and
            `success` is whether the algorithm was successful. Passing `passes=0` makes
            this always `False`. If `success` is `False`, `new_image == image`.

    References:
        ImageJ Java source code: https://github.com/imagej/ImageJ/blob/master/ij/plugin/frame/ContrastAdjuster.java#L815
    """
    if passes < 1:
        if passes < 0:
            _module_logger.warning(
                "Cannot simulate a negative number of auto-contrast passes. "
                "Returning the image as is."
            )

        return image, False

    if not inplace:
        image = image.copy()

    pixel_count = np.prod(image.shape)
    limit = pixel_count / 10

    auto_threshold = 0.0
    for i in range(1, passes + 1):
        if auto_threshold < 10.0:
            auto_threshold = 5_000.0
        else:
            auto_threshold /= 2.0
    threshold = pixel_count / auto_threshold

    histogram = np.histogram(image, bins=256, range=(0, get_dtype_maximum(image.dtype)))
    histogram = (histogram[0], np.round(histogram[1]).astype(np.uint64))

    i = 0  # Silence PyCharm warning
    for i in range(256):
        count = histogram[0][i]

        if count > limit:
            count = 0

        found = count > threshold
        if found:
            break
    histogram_minimum = i

    j = 0  # Silence PyCharm warning
    for j in range(255, -1, -1):
        count = histogram[0][j]

        if count > limit:
            count = 0

        found = count > threshold
        if found:
            break
    histogram_maximum = j

    # If algorithm was successful, clip the image. Otherwise, don't modify the image.
    successful = False
    if histogram_minimum < histogram_maximum:
        np.clip(
            image,
            histogram[1][histogram_minimum],
            histogram[1][histogram_maximum],
            out=image,
        )
        successful = True

    if normalise:
        image[:] = normalise_array(image)

    return image, successful
