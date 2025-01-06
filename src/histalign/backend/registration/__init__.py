# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path
from typing import Optional, Sequence

import cv2
import numpy as np
from PIL import Image
from PySide6 import QtCore, QtGui
from skimage.transform import AffineTransform, rescale as sk_rescale, warp
import vedo

from histalign.backend.ccf.downloads import download_atlas, download_structure_mask
from histalign.backend.ccf.paths import get_atlas_path, get_structure_mask_path
from histalign.backend.io import load_image
from histalign.backend.maths import (
    convert_sk_transform_to_q_transform,
    get_sk_transform_from_parameters,
    get_transformation_matrix_from_q_transform,
)
from histalign.backend.models import (
    AlignmentSettings,
)
import histalign.backend.workspace as workspace  # Avoid circular import


class Registrator:
    fast_rescale: bool
    fast_transform: bool
    interpolation: str

    def __init__(
        self,
        fast_rescale: bool = False,
        fast_transform: bool = False,
        interpolation: str = "bilinear",
    ) -> None:
        self.logger = logging.getLogger(
            f"{self.__module__}.{self.__class__.__qualname__}"
        )

        self.fast_rescale = fast_rescale
        self.fast_transform = fast_transform
        self.interpolation = interpolation

        self._volume_path: Optional[str] = None
        self._volume_slicer: Optional[workspace.VolumeSlicer] = None

    def get_forwarded_image(
        self,
        image: np.ndarray,
        settings: AlignmentSettings,
        origin: Optional[list[float]] = None,
    ) -> np.ndarray:
        scaling = get_histology_scaling(settings)

        image = rescale(image, scaling, fast=self.fast_rescale, interpolation="nearest")

        volume = vedo.Volume(np.zeros(shape=settings.volume_settings.shape))
        slicer = workspace.VolumeSlicer(volume=volume)
        target_shape = slicer.slice(settings.volume_settings, origin=origin).shape

        # TODO: Find why the shape can be off by one sometimes when working on Z-stacks
        image = image[: target_shape[0], : target_shape[1]]

        image = pad(image, (target_shape[0], target_shape[1]))

        image = transform_image(
            image, settings, fast=self.fast_transform, interpolation=self.interpolation
        )

        return image

    def get_reversed_image(
        self,
        settings: AlignmentSettings,
        volume_name: str,
        histology_image: Optional[np.ndarray] = None,
    ) -> Optional[np.ndarray]:
        match volume_name.lower():
            case "atlas":
                volume_path = settings.volume_path
                if not Path(volume_path).exists():
                    self.logger.warning(
                        "Atlas path included in the results does not exist on the "
                        "current filesystem. "
                        "Retrieving atlas manually (may incur download)."
                    )
                    volume_path = get_atlas_path(settings.volume_settings.resolution)
                    if not Path(volume_path).exists():
                        download_atlas()
            case _:
                try:
                    volume_path = get_structure_mask_path(
                        volume_name, settings.volume_settings.resolution
                    )
                    if not Path(volume_path).exists():
                        download_structure_mask(
                            volume_name, resolution=settings.volume_settings.resolution
                        )
                except KeyError:
                    raise ValueError(
                        f"Could not resolve `volume_name` with value '{volume_name}' "
                        f"as a structure name."
                    )

        if volume_path != self._volume_path:
            self._volume_path = volume_path
            self._volume_slicer = workspace.VolumeSlicer(
                path=volume_path,
                resolution=settings.volume_settings.resolution,
                lazy=False,
            )

        if histology_image is None:
            histology_image = load_image(settings.histology_path)

        volume_final_scaling = get_volume_scaling_factor(settings)

        volume_image = self._volume_slicer.slice(
            settings.volume_settings, interpolation="linear"
        )
        volume_image = rescale(
            volume_image,
            volume_final_scaling,
            fast=self.fast_rescale,
            interpolation=self.interpolation,
        )
        volume_image = transform_image(
            volume_image,
            settings,
            fast=self.fast_transform,
            interpolation=self.interpolation,
            forward=False,
        )
        return crop_down(
            volume_image,
            histology_image.shape,
            get_top_left_point(volume_image.shape, histology_image.shape),
        )


class ContourGeneratorThread(QtCore.QThread):
    """Thread class for handling contour generation for the QA GUI.

    Since instances are throwaways, they can use their own ReverseRegistrator as we
    don't need to optimise keeping the loaded volume into memory.

    Attributes:
        should_emit (bool): Whether the thread should report its results or drop them.
                            It should drop them if its processing took too long and its
                            work is no longer required by the GUI (e.g., the contour
                            was removed from the list of selected contours before the
                            thread returned).

    Signals:
        mask_ready (np.ndarray): Emits the structure mask after reverse registration.
        contours_ready (np.ndarray): Emits the contour(s) of the mask as a single numpy
                                     array of shape (N, 2), representing N points' I and
                                     J coordinates (i.e., matrix coordinates). This
                                     array can be empty if no contour was found.
    """

    structure_name: str
    alignment_settings: AlignmentSettings

    should_emit: bool = True

    mask_ready: QtCore.Signal = QtCore.Signal(np.ndarray)
    contours_ready: QtCore.Signal = QtCore.Signal(np.ndarray)

    def __init__(
        self,
        structure_name: str,
        alignment_settings: AlignmentSettings,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(
            f"{self.__module__}.{self.__class__.__qualname__}"
        )

        self.structure_name = structure_name
        self.alignment_settings = alignment_settings

    def run(self) -> None:
        registrator = Registrator(True, True)

        try:
            structure_mask = registrator.get_reversed_image(
                self.alignment_settings, volume_name=self.structure_name
            )
        except FileNotFoundError:
            self.logger.error(
                f"Could not find structure file ('{self.structure_name}')."
            )
            return

        contours = cv2.findContours(
            structure_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE
        )[0]

        if contours:
            contours = np.concatenate(contours).squeeze()
        else:
            contours = np.array([])

        if self.should_emit:
            self.mask_ready.emit(structure_mask)
            self.contours_ready.emit(contours)


def crop_down(
    image: np.ndarray,
    shape: tuple[int, ...],
    top_left: Optional[tuple[int, ...]] = (0, 0),
) -> np.ndarray:
    return image[
        top_left[0] : top_left[0] + shape[0],
        top_left[1] : top_left[1] + shape[1],
    ]


def get_histology_scaling(settings: AlignmentSettings) -> float:
    return settings.histology_scaling / (
        settings.volume_scaling * settings.histology_downsampling
    )


def get_top_left_point(
    larger_shape: tuple[int, ...], smaller_shape: tuple[int, ...]
) -> tuple[int, int]:
    if len(larger_shape) != 2 or len(smaller_shape) != 2:
        raise ValueError(
            f"Invalid shapes, should be 2-dimensional. "
            f"Got {len(larger_shape)}D and {len(smaller_shape)}D."
        )

    ratios = np.array(larger_shape) / np.array(smaller_shape)
    if np.min(ratios) < 1.0:
        raise ValueError(
            f"Large image has at least one dimension that is smaller than smaller "
            f"image (larger: {larger_shape} vs "
            f"smaller: {smaller_shape})."
        )

    maximum = np.max(ratios)

    if ratios[0] == maximum:
        top_left = ((larger_shape[0] - smaller_shape[0]) // 2, 0)
    else:
        top_left = (0, (larger_shape[1] - smaller_shape[1]) // 2)

    return top_left


def get_volume_scaling_factor(settings: AlignmentSettings) -> float:
    return (
        settings.volume_scaling / settings.histology_scaling
    ) * settings.histology_downsampling


def pad(image: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
    vertical_padding = max(0, target_shape[0] - image.shape[0])
    horizontal_padding = max(0, target_shape[1] - image.shape[1])

    return np.pad(
        image,
        (
            (
                vertical_padding // 2,
                vertical_padding // 2 + bool(vertical_padding % 2),
            ),
            (
                horizontal_padding // 2,
                horizontal_padding // 2 + bool(horizontal_padding % 2),
            ),
        ),
        "constant",
        constant_values=(0,),
    )


def recreate_q_transform_from_alignment(
    image_shape: Sequence[int],
    settings: AlignmentSettings,
    invert: bool = False,
) -> QtGui.QTransform:
    histology_settings = settings.histology_settings

    translation_factor = 1
    if not invert:
        # When doing a reverse registration (invert is False), the translation needs to
        # be scaled up to the coordinate space of the full-size image.
        translation_factor = (
            settings.volume_scaling * settings.histology_downsampling
        ) / settings.histology_scaling

    sk_transform = get_sk_transform_from_parameters(
        scale=(
            histology_settings.scale_x,
            histology_settings.scale_y,
        ),
        shear=(
            histology_settings.shear_x,
            histology_settings.shear_y,
        ),
        rotation=histology_settings.rotation,
        translation=(
            histology_settings.translation_x * translation_factor,
            histology_settings.translation_y * translation_factor,
        ),
        extra_translation=(
            -image_shape[1] / 2,
            -image_shape[0] / 2,
        ),
        undo_extra=True,
    )
    return convert_sk_transform_to_q_transform(sk_transform)


def rescale(
    image: np.ndarray, scaling: float, fast: bool, interpolation: str
) -> np.ndarray:
    # NOTE: PIL's resize is much faster but less accurate.
    #       However, it is appropriate for masks.
    match interpolation:
        case "nearest":
            resample = Image.Resampling.NEAREST
            order = 0
        case "bilinear":
            resample = Image.Resampling.BILINEAR
            order = 1
        case _:
            raise ValueError(f"Unknown interpolation '{interpolation}'")

    if fast:
        return np.array(
            Image.fromarray(image.T).resize(
                np.round(np.array(image.shape) * scaling).astype(int).tolist(),
                resample=resample,
            )
        ).T
    else:
        return sk_rescale(
            image,
            scaling,
            preserve_range=True,
            clip=True,
            order=order,
        ).astype(image.dtype)


def transform_image(
    image: np.ndarray,
    alignment_settings: AlignmentSettings,
    fast: bool,
    interpolation: str,
    forward: bool = True,
) -> np.ndarray:
    q_transform = recreate_q_transform_from_alignment(
        image.shape, alignment_settings, forward
    )
    matrix = get_transformation_matrix_from_q_transform(q_transform, forward)

    match interpolation:
        case "nearest":
            flag = cv2.INTER_NEAREST
            order = 0
        case "bilinear":
            flag = cv2.INTER_LINEAR
            order = 1
        case _:
            raise ValueError(f"Unknown interpolation '{interpolation}'")

    # NOTE: OpenCV's warp is much faster but seemingly less accurate
    if fast:
        return cv2.warpPerspective(
            image,
            matrix,
            image.shape[::-1],
            flags=flag | cv2.WARP_INVERSE_MAP,
        )
    else:
        sk_transform = AffineTransform(matrix=matrix)
        return warp(
            image, sk_transform, order=order, preserve_range=True, clip=True
        ).astype(image.dtype)
