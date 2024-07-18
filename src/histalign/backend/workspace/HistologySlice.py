# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import contextlib
import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional

import h5py
import numpy as np
from PIL import Image
from skimage.transform import resize

DOWNSAMPLE_TARGET_SHAPE = (3000, 3000)

# NOTE: this is screen convention rather than matrix convention:
# (width, height) not (i, j)
THUMBNAIL_DIMENSIONS = (320, 180)
THUMBNAIL_ASPECT_RATIO = THUMBNAIL_DIMENSIONS[0] / THUMBNAIL_DIMENSIONS[1]


class HistologySlice:
    """Wrapper around histology images present on the file system.

    The class allows easier management of the images and record keeping by a `Workspace`
    by handling the loading from disk and thumbnail generation for the GUI.

    Attributes:
        hash (str): MD5 hash obtained from the image's file name.
        file_path (str): Absolute file path of the image.
        image_array (np.ndarray | None): Array of the image if it has been loaded or
                                         None otherwise.
        thumbnail_array (np.ndarray | None): Array of the thumbnail if it has been
                                             generated or None otherwise.
    """

    hash: str
    file_path: str
    image_array: Optional[np.ndarray] = None
    thumbnail_array: Optional[np.ndarray] = None
    image_downsampling_factor: Optional[int] = None

    def __init__(self, file_path: str) -> None:
        """Creates a new wrapper around the image located at `file_path`.

        Args:
            file_path (str): Path to the image to wrap.
        """
        self.hash = hashlib.md5(file_path.split(os.sep)[-1].encode("UTF-8")).hexdigest()
        self.file_path = os.path.abspath(file_path)

        self.image_array = None
        self.thumbnail_array = None

        self.logger = logging.getLogger(__name__)

    def load_image(self, working_directory: str, downsampling_factor: int = 0) -> None:
        """Loads wrapped image into memory.

        To avoid having to reload the image again for it, the thumbnail is also
        generated before returning.

        Note that the greater the downsampling factor and the smaller the image, the
        greater the discrepancy between the original aspect ratio and the downsampled
        one. Do not set a downsampling factor if you are unsure whether the discrepancy
        will impact your analysis.

        Args:
            working_directory (str): Working directory to use to find the cache
                                     location.
            downsampling_factor (int): Factor to downsample raw image by. If set to 0
                                       (the default), the image is automatically
                                       downsampled to a manageable size if necessary or
                                       kept as-is if it is already small enough.
        """
        self.image_array = self._load_image(downsampling_factor)

        self.generate_thumbnail(working_directory)

    # noinspection PyUnboundLocalVariable
    def generate_thumbnail(self, working_directory: Optional[str] = None) -> None:
        """Generates thumbnail for self.

        In order to avoid loading the wrapped image into memory unnecessarily, the
        thumbnail is not automatically generated during initialisation. Instead, call
        this method if a thumbnail is required. If the image was loaded at any point,
        a thumbnail will exist already.

        If a thumbnail was previously generated in the provided directory, the cached
        thumbnail will be loaded instead, meaning the image is not loaded into memory.

        Args:
            working_directory (str, optional): Working directory to use to find the
                                               cache location. If set to `None`, the
                                               thumbnail is not cached.
        """
        self.logger.debug(f"Generating thumbnail for {self.hash[:10]}.")

        if working_directory is not None:
            cache_root = Path(working_directory) / ".cache" / "thumbnails"
            os.makedirs(cache_root, exist_ok=True)

            # Try loading cached file
            cache_path = str(cache_root / f"{self.hash[:10]}.png")
            with contextlib.suppress(FileNotFoundError):
                self.thumbnail_array = np.array(Image.open(cache_path))
                self.logger.debug(f"Loaded thumbnail from cache ('{cache_path}').")
                return

        image_array = self.image_array
        if image_array is None:
            image_array = self._load_image(4)

        # Generate thumbnail from `self.image_array`
        aspect_ratio = image_array.shape[1] / image_array.shape[0]
        if aspect_ratio >= THUMBNAIL_ASPECT_RATIO:
            temporary_height = image_array.shape[0] / (
                image_array.shape[1] / THUMBNAIL_DIMENSIONS[0]
            )

            thumbnail_array = resize(
                image_array, (temporary_height, THUMBNAIL_DIMENSIONS[0])
            )

            padding = (THUMBNAIL_DIMENSIONS[1] - thumbnail_array.shape[0]) / 2
            off_by_one = padding - (padding // 1) == 0.5
            padding = int(padding)

            thumbnail_array = np.pad(
                thumbnail_array,
                ((padding, padding + off_by_one), (0, 0)),
            )
        else:
            temporary_width = image_array.shape[1] / (
                image_array.shape[0] / THUMBNAIL_DIMENSIONS[1]
            )

            thumbnail_array = resize(
                image_array, (THUMBNAIL_DIMENSIONS[1], temporary_width)
            )

            padding = (THUMBNAIL_DIMENSIONS[0] - thumbnail_array.shape[1]) / 2
            off_by_one = padding - (padding // 1) == 0.5
            padding = int(padding)

            thumbnail_array = np.pad(
                thumbnail_array,
                ((0, 0), (padding, padding + off_by_one)),
            )

        thumbnail_array = self.normalise_to_8_bit(thumbnail_array)

        if working_directory is not None:
            # Cache thumbnail
            Image.fromarray(thumbnail_array).save(cache_path)
            self.logger.debug(
                f"Finished generating thumbnail and cached it to '{cache_path}'."
            )

        self.thumbnail_array = thumbnail_array

    @staticmethod
    def downsample(array: np.ndarray, downsampling_factor: int) -> np.ndarray:
        """Returns `array` downsampled by `downsampling_factor`.

        Args:
            array (np.ndarray): Array to downsample.
            downsampling_factor (int): Factor to downsample `array` by.

        Returns:
            np.ndarray: Array after downsampling.
        """
        # NOTE: this is around 1.5 orders of magnitude faster than just using
        # skimage.transform.resize or rescale.
        size = np.round(np.array(array.shape) / downsampling_factor).astype(int)
        return np.array(Image.fromarray(array).resize(size[::-1].tolist()))

    @staticmethod
    def normalise_to_8_bit(array: np.ndarray) -> np.ndarray:
        """Returns `array` after normalisation and conversion to u8.

        Args:
            array (np.ndarray): Array to normalise and convert.

        Returns:
            np.ndarray: Array after normalisation and conversion.
        """
        return np.interp(
            array,
            (array.min(), array.max()),
            (0, 2**8 - 1),
        ).astype(np.uint8)

    # noinspection PyUnboundLocalVariable
    def _load_image(self, downsampling_factor: int) -> np.ndarray:
        start_time = time.perf_counter()

        match self.file_path.split(".")[-1]:
            case "h5" | "hdf5":
                with h5py.File(self.file_path, "r") as h5_handle:
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
                image_array = np.load(self.file_path)
            case "jpg" | "jpeg" | "png":
                image_array = np.array(Image.open(self.file_path))
            case other:
                raise ValueError(f"Unrecognised file extension '{other}'.")

        if downsampling_factor == 0:
            # If the image is smaller than DOWNSAMPLE_TARGET_SHAPE, don't downsample
            downsampling_factor = max(
                1.0,
                (np.array(image_array.shape) / DOWNSAMPLE_TARGET_SHAPE).max(),
            )
        self.image_downsampling_factor = downsampling_factor
        image_array = self.downsample(image_array, downsampling_factor)

        image_array = self.normalise_to_8_bit(image_array)

        self.logger.debug(
            f"Loaded and processed '{self.file_path.split(os.sep)[-1]}' "
            f"({self.hash[:10]}) in {time.perf_counter() - start_time:.2f} seconds."
        )

        return image_array
