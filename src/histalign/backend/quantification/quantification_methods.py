# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import cv2
import numpy as np
import vedo

from histalign.backend.models import AlignmentSettings
from histalign.backend.registration import get_transformation_matrix_from_alignment
from histalign.backend.workspace import Volume, VolumeSlicer


def compute_average_fluorescence(image: np.ndarray, mask: np.ndarray) -> float:
    # Avoid a RuntimeWarning when mask is empty
    if not mask.any():
        return 0.0

    return np.mean(image, where=mask > 0).astype(float)


def compute_cortical_depths(
    cortex_volume: Volume | vedo.Volume,
    structure_volume: Volume | vedo.Volume,
    settings: AlignmentSettings,
) -> list:
    cortex_slice = VolumeSlicer(volume=cortex_volume).slice(settings.volume_settings)
    cortex_contour = _compute_largest_contour(cortex_slice)
    cortex_points = np.flipud(np.squeeze(cortex_contour))

    structure_slice = VolumeSlicer(volume=structure_volume).slice(
        settings.volume_settings
    )
    structure_contour = _compute_largest_contour(structure_slice)

    if structure_contour.size == 0:
        return [[], []]

    structure_points = np.flipud(np.squeeze(structure_contour))

    closest_cortex_points = [
        _find_closest_point(point, cortex_points) for point in structure_points
    ]

    transformation_matrix = get_transformation_matrix_from_alignment(
        settings, invert=True
    )

    registered_structure_points = _apply_transformation_matrix_to_points(
        transformation_matrix, structure_points
    )
    registered_closest_cortex_points = _apply_transformation_matrix_to_points(
        transformation_matrix, closest_cortex_points
    )

    baseline_depths = [
        _compute_distance_nonisometric_grid(
            structure_point,
            closest_cortex_point,
            settings.volume_settings.resolution,
            settings.volume_settings.resolution,
        )
        for structure_point, closest_cortex_point in zip(
            structure_points, closest_cortex_points
        )
    ]
    registered_depths = [
        _compute_distance_nonisometric_grid(
            registered_structure_point,
            registered_closest_cortex_point,
            settings.volume_settings.resolution / settings.histology_settings.scale_x,
            settings.volume_settings.resolution / settings.histology_settings.scale_y,
        )
        for registered_structure_point, registered_closest_cortex_point in zip(
            registered_structure_points, registered_closest_cortex_points
        )
    ]

    return [
        baseline_depths,
        registered_depths,
    ]


def _apply_transformation_matrix_to_points(
    transformation_matrix: np.ndarray, points: np.ndarray
) -> np.ndarray:
    return np.array(
        [
            np.matmul(transformation_matrix, np.concatenate([point, [1]]))[:2]
            for point in points
        ]
    )


def _compute_distance_nonisometric_grid(
    point1: np.ndarray,
    point2: np.ndarray,
    x_size: float,
    y_size: float,
) -> float:
    return np.sqrt(
        ((point1[0] - point2[0]) * x_size) ** 2
        + ((point1[1] - point2[1]) * y_size) ** 2
    )


def _compute_largest_contour(image: np.ndarray) -> np.ndarray:
    contours = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]

    if contours:
        return max(
            contours,
            key=cv2.contourArea,
        )
    else:
        return np.array([])


def _find_closest_point(point: np.ndarray, points_pool: np.ndarray) -> np.ndarray:
    deltas = points_pool - point
    distances = np.einsum("ij,ij->i", deltas, deltas)
    return points_pool[np.argmin(distances)]
