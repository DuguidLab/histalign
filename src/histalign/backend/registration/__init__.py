# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path
from typing import Literal, Optional, Sequence

import cv2
import numpy as np
from PIL import Image, ImageTransform
from PySide6 import QtCore
from skimage.transform import rescale as sk_rescale, warp
import vedo

from histalign.backend.ccf import get_atlas_path, get_structure_mask_path
from histalign.backend.maths import (
    get_sk_transform_from_parameters,
)
from histalign.backend.models import (
    AlignmentSettings,
)
from histalign.backend.workspace import VolumeSlicer
import histalign.backend.workspace as workspace  # Avoid circular import
from histalign.io import load_image

_module_logger = logging.getLogger(__name__)


class Registrator:
    fast_rescale: bool
    fast_transform: bool
    interpolation: str

    def __init__(
        self,
        fast_rescale: bool = True,
        fast_transform: bool = True,
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
        slicer: Optional[VolumeSlicer] = None,
    ) -> np.ndarray:
        scaling = get_histology_scaling(settings)

        image = rescale(image, scaling, fast=self.fast_rescale, interpolation="nearest")

        if slicer is None:
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
    ) -> np.ndarray:
        self._load_volume(volume_name, settings)

        if histology_image is None and settings.histology_path is not None:
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
        return crop_down(volume_image, histology_image.shape)

    def get_reversed_contours(
        self,
        settings: AlignmentSettings,
        volume_name: str,
        histology_image: Optional[np.ndarray] = None,
        interpolation: Literal["nearest", "linear", "cubic"] = "nearest",
    ) -> list[np.ndarray]:
        self._load_volume(volume_name, settings)

        # TODO: Avoid loading the whole image just for its shape
        # Retrieve the histology image for its shape
        if histology_image is None and settings.histology_path is not None:
            histology_image = load_image(settings.histology_path)

        # Compute relative volume scaling needed to the same scale as histology
        volume_scaling = get_volume_scaling_factor(settings)

        # Get the alignment slice
        volume_image = self._volume_slicer.slice(
            settings.volume_settings, interpolation=interpolation
        )

        # Compute the contours on the small slice and convert them to a single array
        # while keeping track of where they each are. This simplifies applying
        # transformations to all of them at once.
        contours = cv2.findContours(volume_image, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)[
            0
        ]
        if len(contours) < 1:
            return []

        contour_lengths = [contour.shape[0] for contour in contours]
        contours = np.concatenate(contours, axis=0)

        # Rescale the contours
        contours = contours.astype(np.float64) * volume_scaling
        # Keep track of what the volume shape would be at this point
        scaled_volume_shape = tuple(
            np.round(np.array(volume_image.shape) * volume_scaling).astype(int)
        )

        # Apply reverse registration on the contours
        matrix = get_transformation_matrix_from_alignment(
            settings, np.array(scaled_volume_shape) // 2, True
        )

        contours = contours.T[:, 0]  # Go from (N, 1, 2) to (2, N)
        contours = np.vstack([contours, [1] * contours.shape[1]])  # Go to (3, N)

        contours = matrix @ contours

        contours = contours[:2]

        # Adjust for cropping
        # Contours work with XY while the top left if taken from shapes, hence is in IJ
        top_left = get_top_left_point(scaled_volume_shape, histology_image.shape)[::-1]

        contours = contours - np.array(top_left).reshape(-1, 1)

        # Fix up the contours to a format OpenCV understands
        contours = contours.T.reshape(-1, 1, 2)
        contours = np.round(contours).astype(np.int32)

        # Convert the contours back to a list of individual contours
        i = 0
        contour_list = []
        for index in contour_lengths:
            contour = contours[i : i + index]
            i += index

            contour_list.append(contour)

        return contour_list

    def _load_volume(self, volume_name: str, settings: AlignmentSettings) -> None:
        match volume_name.lower():
            case "atlas":
                volume_path = settings.volume_path
                if not Path(volume_path).exists():
                    self.logger.warning(
                        "Atlas path included in the results does not exist on the "
                        "current filesystem. "
                        "Retrieving atlas manually (may incur download)."
                    )
                    volume_path = get_atlas_path(
                        settings.volume_settings.resolution, ensure_downloaded=True
                    )
            case _:
                try:
                    volume_path = get_structure_mask_path(
                        volume_name,
                        settings.volume_settings.resolution,
                        ensure_downloaded=True,
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

    contours_ready: QtCore.Signal = QtCore.Signal(list)  # Really list[np.ndarray]

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
            contours = registrator.get_reversed_contours(
                self.alignment_settings, volume_name=self.structure_name
            )
        except FileNotFoundError:
            self.logger.error(
                f"Could not find structure file ('{self.structure_name}')."
            )
            return

        if self.should_emit:
            self.contours_ready.emit(contours)


def crop_down(
    image: np.ndarray,
    reference_shape: tuple[int, ...],
) -> np.ndarray:
    top_left = get_top_left_point(image.shape, reference_shape)

    return image[
        top_left[0] : top_left[0] + reference_shape[0],
        top_left[1] : top_left[1] + reference_shape[1],
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

    centre = np.array(larger_shape) // 2
    top_left = centre - (np.array(smaller_shape) // 2)

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


def get_transformation_matrix_from_alignment(
    settings: AlignmentSettings,
    transformation_origin: Sequence[int] = (0, 0),
    invert: bool = False,
) -> np.ndarray:
    histology_settings = settings.histology_settings

    # When inverting, the translation obtained during registration needs to be rescaled
    # to the unit vectors of the histology.
    translation_factor = 1
    if invert:
        translation_factor = (
            settings.volume_scaling
            * settings.histology_downsampling
            / settings.histology_scaling
        )

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
            -transformation_origin[0],
            -transformation_origin[1],
        ),
        undo_extra=True,
    )

    matrix = sk_transform.params
    if invert:
        matrix = np.linalg.inv(matrix)

    return matrix


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
        target_shape = (
            np.round(np.array(image.shape[::-1]) * scaling).astype(int).tolist()
        )

        image_pil = Image.fromarray(image)
        image_pil = image_pil.resize(target_shape, resample=Image.Resampling.BILINEAR)

        return np.array(image_pil)
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
    matrix = get_transformation_matrix_from_alignment(
        alignment_settings, np.array(image.shape) // 2, not forward
    )

    match interpolation:
        case "nearest":
            flags = cv2.INTER_NEAREST
            order = 0
        case "bilinear":
            flags = cv2.INTER_LINEAR
            order = 1
        case _:
            raise ValueError(f"Unknown interpolation '{interpolation}'")

    # NOTE: OpenCV's warp is much faster but seemingly less accurate at interpolating.
    if fast:
        # OpenCV cannot handle images with dimensions larger than 2**15 - 1
        if max(image.shape) < 2**15 - 1:
            cv2.warpAffine(
                image,
                matrix[:2],
                image.shape[::-1],
                image,
                flags=flags,
            )
        else:
            _module_logger.debug(
                "Falling back to PIL warping as image has at least one dimension "
                "larger than 2**15 - 1."
            )

            # PIL needs the inverse map
            matrix = np.linalg.inv(matrix)

            # Fallback to PIL. ~10x slower than OpenCV. Still much faster than skimage.
            image_pil = Image.fromarray(image)  # Does not copy the data
            image_pil.readonly = False  # Avoid a copy-on-write

            transform = ImageTransform.AffineTransform(matrix.flatten()[:6])
            # Paste the output onto the image to modify the NumPy array directly
            image_pil.paste(image_pil.transform(image_pil.size, transform))
    else:
        # `warp` needs the inverse map
        matrix = np.linalg.inv(matrix)

        image = warp(image, matrix, order=order, preserve_range=True, clip=True).astype(
            image.dtype
        )

    return image
