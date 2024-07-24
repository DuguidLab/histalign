# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import h5py
import json
import logging
import os
from pathlib import Path
import ssl
from typing import Any, Callable
from urllib.request import urlopen

from allensdk.core.reference_space_cache import ReferenceSpaceCache
import cv2
import numpy as np
from PIL import Image
import pydantic
from PySide6 import QtCore, QtGui
from skimage.transform import AffineTransform, rescale, warp

from histalign.backend.ccf.allen_downloads import get_structure_path
from histalign.backend.models.AlignmentParameterAggregator import (
    AlignmentParameterAggregator,
)
from histalign.backend.models.VolumeSettings import VolumeSettings
from histalign.backend.quantification.quantification_methods import (
    get_average_fluorescence,
)
from histalign.backend.workspace.VolumeManager import VolumeManager


class Quantifier:
    quantification_method: Callable
    fast_rescale: bool
    fast_transform: bool

    def __init__(
        self,
        quantification_method: str,
        fast_rescale: bool = True,
        fast_transform: bool = False,
    ) -> None:
        self.logger = logging.getLogger(__name__)

        match quantification_method:
            case "average_fluorescence":
                self.quantification_method = get_average_fluorescence
            case _:
                raise ValueError(
                    f"Unknown quantification method '{quantification_method}'."
                )

        self.fast_rescale = fast_rescale
        self.fast_transform = fast_transform

    def quantify(
        self,
        results_directory: str,
        structures: list[str],
        allow_different_atlases: bool = False,
    ) -> Any:
        quantification_results = {}
        for structure_name in structures:
            mask_volume = None
            resolution = None
            for results_file in Path(results_directory).iterdir():
                if results_file.suffix != ".json" or results_file.stem == "metadata":
                    continue

                try:
                    with open(results_file) as handle:
                        parameters = AlignmentParameterAggregator(**json.load(handle))
                except (pydantic.ValidationError, json.JSONDecodeError) as error:
                    self.logger.error(
                        f"Failed to load results for file '{results_file.name}'. "
                        f"Skipping it."
                    )
                    self.logger.error(error)
                    continue

                if (
                    mask_volume is not None
                    and resolution != parameters.resolution
                    and not allow_different_atlases
                ):
                    raise ValueError(
                        "Not all results require the same atlas. "
                        "If this is on purpose, use `allow_different_atlases`."
                    )

                if mask_volume is None or resolution != parameters.resolution:
                    resolution = parameters.resolution
                    mask_volume = self._load_structure_mask(structure_name, resolution)

                full_size_histology_image = self._load_image(
                    parameters.histology_file_path
                )

                mask_settings = VolumeSettings(**parameters.model_dump())
                mask_scaling_factor = self._get_mask_scaling_factor(
                    parameters.histology_scaling_factor,
                    parameters.volume_scaling_factor,
                    parameters.downsampling_factor,
                )
                mask_image = mask_volume.slice_volume(mask_settings)
                mask_image = self._rescale(
                    mask_image, mask_scaling_factor, fast=self.fast_rescale
                )
                mask_image = self._transform_image(
                    mask_image, parameters, inverse=True, fast=self.fast_transform
                )
                mask_image = self._crop_down(
                    mask_image, full_size_histology_image.shape
                )

                quantification_result = {
                    structure_name: self.quantification_method(
                        full_size_histology_image, mask_image
                    ),
                }

                if quantification_results.get(results_file.stem) is None:
                    quantification_results[results_file.stem] = quantification_result
                else:
                    quantification_results[results_file.stem].update(
                        quantification_result
                    )

        return quantification_results

    @staticmethod
    def _rescale(
        image: np.ndarray, scaling_factor: float, fast: bool = False
    ) -> np.ndarray:
        # NOTE: PIL's resize is much faster but less accurate.
        #       However, it is appropriate for masks.
        if fast:
            return np.array(
                Image.fromarray(image.T).resize(
                    np.round(np.array(image.shape) * scaling_factor)
                    .astype(int)
                    .tolist(),
                    resample=Image.Resampling.BILINEAR,
                )
            ).T
        else:
            return rescale(image, scaling_factor, preserve_range=True).astype(
                image.dtype
            )

    @staticmethod
    def _transform_image(
        image: np.ndarray,
        registration_parameters: AlignmentParameterAggregator,
        inverse: bool = False,
        fast: bool = False,
    ):
        initial_width = image.shape[1]
        initial_height = image.shape[0]

        effective_width = registration_parameters.x_scale * initial_width
        effective_height = registration_parameters.y_scale * initial_height

        x_displacement = registration_parameters.x_shear * effective_height
        y_displacement = registration_parameters.y_shear * effective_width

        q_transform = (
            QtGui.QTransform()
            .translate(  # Translation to apply rotation around the center of the image
                initial_width / 2,
                initial_height / 2,
            )
            .rotate(  # Regular rotation
                registration_parameters.rotation_angle,
            )
            .translate(  # Translation to get back to position before rotation
                -initial_width / 2,
                -initial_height / 2,
            )
            .translate(  # Regular translation
                registration_parameters.x_translation
                * registration_parameters.downsampling_factor,
                registration_parameters.y_translation
                * registration_parameters.downsampling_factor,
            )
            .translate(  # Translation to apply scaling from the center of the image
                -(effective_width - initial_width) / 2,
                -(effective_height - initial_height) / 2,
            )
            .scale(  # Regular scaling
                registration_parameters.x_scale,
                registration_parameters.y_scale,
            )
            .translate(  # Translation to apply shearing from the center of the image
                -x_displacement / 2,
                -y_displacement / 2,
            )
            .shear(  # Regular shearing
                registration_parameters.x_shear,
                registration_parameters.y_shear,
            )
        )

        # Counterintuitive but AffineTransform takes the inverse matrix.
        # If the user is asking to apply the inverse transform on an image, we need to
        # not invert the QTransform and let skimage do it. And when we want to apply the
        # transform as it was during the registration, we need to invert the matrix so
        # skimage inverts it again and we get the normal transform.
        if not inverse:
            q_transform, successful = q_transform.inverted()
            if not successful:
                raise Exception("Panic: couldn't invert the transform matrix.")

        matrix = (
            str(q_transform).replace("PySide6.QtGui.QTransform(", "").replace(")", "")
        )
        matrix = (
            np.array([float(value) for value in matrix.split(", ")]).reshape(3, 3).T
        )

        # NOTE: OpenCV's warp is much faster but seemingly less accurate
        if fast:
            return cv2.warpPerspective(
                image,
                matrix,
                image.shape[::-1],
                flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
            )
        else:
            sk_transform = AffineTransform(matrix=matrix)
            return warp(image, sk_transform, preserve_range=True)

    @staticmethod
    def _crop_down(
        image_to_crop: np.ndarray, crop_to_shape: tuple[int, ...]
    ) -> np.ndarray:
        top_left = Quantifier._get_top_left_point(image_to_crop.shape, crop_to_shape)

        return image_to_crop[
            top_left[0] : top_left[0] + crop_to_shape[0],
            top_left[1] : top_left[1] + crop_to_shape[1],
        ]

    @staticmethod
    def _get_top_left_point(
        larger_image_shape: tuple[int, ...], smaller_image_shape: tuple[int, ...]
    ) -> tuple[int, int]:
        if len(larger_image_shape) != 2 or len(smaller_image_shape) != 2:
            raise ValueError(
                f"Invalid shapes, should be 2-dimensional. "
                f"Got {len(larger_image_shape)}D and {len(smaller_image_shape)}D."
            )

        ratios = np.array(larger_image_shape) / np.array(smaller_image_shape)
        if np.min(ratios) < 1.0:
            raise ValueError(
                f"Large image has at least one dimension that is smaller than smaller "
                f"image (larger: {larger_image_shape} vs "
                f"smaller: {smaller_image_shape})."
            )

        maximum = np.max(ratios)

        if ratios[0] == maximum:
            top_left = ((larger_image_shape[0] - smaller_image_shape[0]) // 2, 0)
        else:
            top_left = (0, (larger_image_shape[1] - smaller_image_shape[1]) // 2)

        return top_left

    @staticmethod
    def _get_mask_scaling_factor(
        registration_histology_scaling_factor: float,
        registration_volume_scaling_factor: float,
        histology_downsampling_factor: float,
    ) -> float:
        return (
            registration_volume_scaling_factor / registration_histology_scaling_factor
        ) * histology_downsampling_factor

    # noinspection PyUnboundLocalVariable
    @staticmethod
    def _load_image(file_path: str) -> np.ndarray:
        match file_path.split(".")[-1]:
            case "h5" | "hdf5":
                with h5py.File(file_path, "r") as h5_handle:
                    dataset_name = list(h5_handle.keys())

                    if len(dataset_name) != 1:
                        raise ValueError(
                            f"Unexpected number of datasets found. "
                            f"Expected 1, found {len(dataset_name)}. "
                            f"Make sure the file only contains a single image."
                        )

                    image_array = h5_handle[dataset_name[0]][:]

                    if len(image_array.shape) != 2:
                        raise ValueError(
                            f"Unexpected number of dataset dimensions. "
                            f"Expected 2, found {len(image_array.shape)}. "
                            f"Make sure the image has been project to only contain "
                            f"XY data."
                        )
            case "npy":
                image_array = np.load(file_path)
            case "jpg" | "jpeg" | "png":
                image_array = np.array(Image.open(file_path))
            case other:
                raise ValueError(f"Unrecognised file extension '{other}'.")

        return image_array

    @staticmethod
    def _load_structure_mask(structure_name: str, resolution: int) -> VolumeManager:
        mask_volume = VolumeManager()
        mask_volume.load_volume(get_structure_path(structure_name, resolution))
        return mask_volume
