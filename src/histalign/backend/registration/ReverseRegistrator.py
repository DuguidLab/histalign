# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image
from PySide6 import QtGui
from skimage.transform import AffineTransform, rescale, warp

import histalign.backend.io as io
from histalign.backend.ccf.allen_downloads import get_atlas_path, get_structure_path
from histalign.backend.models.AlignmentParameterAggregator import (
    AlignmentParameterAggregator,
)
from histalign.backend.models.VolumeSettings import VolumeSettings
from histalign.backend.workspace.VolumeManager import VolumeManager


class ReverseRegistrator:
    fast_rescale: bool
    fast_transform: bool
    interpolation: str

    def __init__(
        self,
        fast_rescale: bool = False,
        fast_transform: bool = False,
        interpolation: str = "bilinear",
    ) -> None:
        self.logger = logging.getLogger(__name__)

        self.fast_rescale = fast_rescale
        self.fast_transform = fast_transform
        self.interpolation = interpolation

        self._volume_file_path: Optional[str] = None
        self._volume_manager: Optional[VolumeManager] = None

    def get_reversed_image(
        self,
        parameters: AlignmentParameterAggregator,
        volume_name: str,
        histology_image: Optional[np.ndarray] = None,
    ) -> Optional[np.ndarray]:
        match volume_name.lower():
            case "atlas":
                volume_path = parameters.volume_file_path
                if not Path(volume_path).exists():
                    self.logger.warning(
                        "Atlas path included in the results does not exist on the "
                        "current filesystem. "
                        "Retrieving atlas manually (may incur download)."
                    )
                    volume_path = get_atlas_path(parameters.resolution)
            case _:
                try:
                    volume_path = get_structure_path(volume_name, parameters.resolution)
                except KeyError:
                    raise ValueError(
                        f"Could not resolve `volume_name` with value '{volume_name}' "
                        f"as a structure name."
                    )

        if volume_path != self._volume_file_path:
            self._volume_file_path = volume_path
            self._volume_manager = self._load_volume_manager(volume_path)

        if histology_image is None:
            histology_image = io.load_image(parameters.histology_file_path)

        volume_settings = VolumeSettings(**parameters.model_dump())
        volume_scaling_factor = self._get_volume_scaling_factor(
            parameters.histology_scaling_factor,
            parameters.volume_scaling_factor,
            parameters.downsampling_factor,
        )

        volume_image = self._volume_manager.slice_volume(
            volume_settings, interpolation="linear"
        )
        volume_image = self._rescale(
            volume_image,
            volume_scaling_factor,
            fast=self.fast_rescale,
            interpolation=self.interpolation,
        )
        volume_image = self._transform_image(
            volume_image,
            parameters,
            fast=self.fast_transform,
            interpolation=self.interpolation,
        )
        return self._crop_down(volume_image, histology_image.shape)

    @staticmethod
    def _rescale(
        image: np.ndarray, scaling_factor: float, fast: bool, interpolation: str
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
                    np.round(np.array(image.shape) * scaling_factor)
                    .astype(int)
                    .tolist(),
                    resample=resample,
                )
            ).T
        else:
            return rescale(
                image,
                scaling_factor,
                preserve_range=True,
                clip=True,
                order=order,
            ).astype(image.dtype)

    @staticmethod
    def _transform_image(
        image: np.ndarray,
        parameters: AlignmentParameterAggregator,
        fast: bool,
        interpolation: str,
    ) -> np.ndarray:
        initial_width = image.shape[1]
        initial_height = image.shape[0]

        effective_width = parameters.x_scale * initial_width
        effective_height = parameters.y_scale * initial_height

        x_displacement = parameters.x_shear * effective_height
        y_displacement = parameters.y_shear * effective_width

        q_transform = (
            QtGui.QTransform()
            .translate(  # Translation to apply rotation around the center of the image
                initial_width / 2,
                initial_height / 2,
            )
            .rotate(  # Regular rotation
                parameters.rotation_angle,
            )
            .translate(  # Translation to get back to position before rotation
                -initial_width / 2,
                -initial_height / 2,
            )
            .translate(  # Regular translation
                parameters.x_translation * parameters.downsampling_factor,
                parameters.y_translation * parameters.downsampling_factor,
            )
            .translate(  # Translation to apply scaling from the center of the image
                -(effective_width - initial_width) / 2,
                -(effective_height - initial_height) / 2,
            )
            .scale(  # Regular scaling
                parameters.x_scale,
                parameters.y_scale,
            )
            .translate(  # Translation to apply shearing from the center of the image
                -x_displacement / 2,
                -y_displacement / 2,
            )
            .shear(  # Regular shearing
                parameters.x_shear,
                parameters.y_shear,
            )
        )

        matrix = (
            str(q_transform).replace("PySide6.QtGui.QTransform(", "").replace(")", "")
        )
        matrix = (
            np.array([float(value) for value in matrix.split(", ")]).reshape(3, 3).T
        )

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

    @staticmethod
    def _crop_down(image: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
        top_left = ReverseRegistrator._get_top_left_point(image.shape, shape)

        return image[
            top_left[0] : top_left[0] + shape[0],
            top_left[1] : top_left[1] + shape[1],
        ]

    @staticmethod
    def _get_top_left_point(
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

    @staticmethod
    def _get_volume_scaling_factor(
        histology_scaling_factor: float,
        volume_scaling_factor: float,
        histology_downsampling_factor: float,
    ) -> float:
        return (
            volume_scaling_factor / histology_scaling_factor
        ) * histology_downsampling_factor

    @staticmethod
    def _load_volume_manager(file_path: str) -> VolumeManager:
        volume_manager = VolumeManager()
        volume_manager.load_volume(file_path)
        return volume_manager
