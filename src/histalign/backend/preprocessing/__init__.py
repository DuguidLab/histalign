# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT
"""A module for preprocessing of fluorescence images.

The current functionality covers operations such as removing bright spots on an image,
automatically adjusting its contrast, and masking.
"""

import logging
from typing import Optional

import numpy as np

from histalign.backend.array_operations import get_dtype_maximum

_module_logger = logging.getLogger(__name__)


def normalise_array(array: np.ndarray, dtype: Optional[np.dtype] = None) -> np.ndarray:
    """Normalise an array to the range between 0 and the dtype's maximum value.

    Args:
        array (np.ndarray): Array to normalise.
        dtype (np.dtype, optional): Target dtype. If `None`, the dtype will be inferred
                                    as the dtype of `array`.

    Returns:
        np.ndarray: The normalised array.
    """
    if dtype is None:
        dtype = array.dtype

    maximum = get_dtype_maximum(dtype)

    array = array.astype(float)
    return (maximum * (array - np.min(array)) / np.ptp(array)).astype(dtype)


def remove_bright_spots(
    image: np.ndarray, threshold: Optional[int] = None, inplace: bool = False
) -> np.ndarray:
    """Zero out the brightest pixels of an image.

    Note: the default threshold value is subject to change in the future. It is only
          currently provided for convenience.

    Args:
        image (np.ndarray)=): Image to remove bright spots from.
        threshold (Optional[int], optional): Value to use as threshold. If `None`, this
                                             will be computed as 60% of the maximum
                                             value of the image's dtype. The threshold
                                             is non-inclusive, meaning a threshold of
                                             N will keep pixels with intensities of N
                                             in the image.
        inplace (bool, optional): Whether to carry out the modification in place.

    Returns:
        np.ndarray: `image` with zeros in place of values above `threshold`.
    """
    if not inplace:
        image = image.copy()

    if threshold is None:
        threshold = get_dtype_maximum(image.dtype) * (3 / 5)

    image[image > threshold] = 0
    return image


def extract_mask(
    image: np.ndarray, mask: np.ndarray, invert: bool = False, inplace: bool = False
) -> np.ndarray:
    """Extract values from an image based on a mask.

    Args:
        image (np.ndarray): Image to mask.
        mask (np.ndarray): Mask comprising of zero values (unmasked) and non-zero values
                           (masked).
        invert (bool, optional): Whether to invert the mask.
        inplace (bool, optional): Whether to carry out the modification in place.

    Returns:
        np.ndarray: Result of masking image. This has the same shape as `image` with
                    masked values replaced with 0.
    """
    if (image_shape := image.shape) != (mask_shape := mask.shape):
        raise ValueError(
            f"Image and mask have different shapes ({image_shape} vs {mask_shape})."
        )

    if not inplace:
        image = image.copy()

    mask = mask.astype(bool)
    if invert:
        mask = ~mask
    image[~mask] = 0
    return image


def compute_mean(
    array: np.ndarray, subset_bounds: Optional[tuple[int, int]] = None
) -> float:
    """Compute the mean of an array, optionally limiting the subset range.

    Args:
        array (np.ndarray): Array whose mean to compute.
        subset_bounds (Optional[tuple[int, int]], optional): An optional tuple of bounds
                                                             to compute the mean on. If
                                                             provided, this should be a
                                                             tuple of two values,
                                                             signifying the lower and
                                                             upper bounds. The bounds
                                                             are both inclusive.

    Returns:
        float: The computed mean.
    """
    lower_bound = 0
    upper_bound = array.max()
    if subset_bounds is not None:
        subset_bounds_length = len(subset_bounds)
        if subset_bounds_length < 2:
            raise ValueError(
                f"'subset_bounds' should be `None` or contain at least two values. "
                f"Got {subset_bounds_length}."
            )
        else:
            if subset_bounds_length > 2:
                _module_logger.warning(
                    "'compute_mean' called with more than two bounds. "
                    "Only the smallest and largest values will be used."
                )
            lower_bound = min(subset_bounds)
            upper_bound = max(subset_bounds)

            if lower_bound == upper_bound:
                _module_logger.warning(
                    "'compute_mean' called with a subset describing the same upper and"
                    "lower bounds, the result will be `np.nan`."
                )

    return float(np.mean(array[(lower_bound <= array) & (array <= upper_bound)]))


def apply_auto_contrast(
    image: np.ndarray, passes: int = 1, normalise: bool = True, inplace: bool = False
) -> np.ndarray:
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
        np.ndarray: The result of applying `passes` number of passes on `image` using
                    the auto-contrast algorithm.

    References:
        https://github.com/imagej/ImageJ/blob/master/ij/plugin/frame/ContrastAdjuster.java#L815
    """
    if passes < 1:
        if passes < 0:
            _module_logger.warning(
                "Cannot simulate a negative number of auto-contrast passes. "
                "Returning the image as is."
            )

        return image

    if not inplace:
        image = image.copy()

    pixel_count = np.prod(image.shape)
    limit = pixel_count / 10

    auto_threshold = 0
    for i in range(1, passes + 1):
        if auto_threshold < 10:
            auto_threshold = 5_000
        else:
            auto_threshold /= 2
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
    if histogram_minimum < histogram_maximum:
        np.clip(
            image,
            histogram[1][histogram_minimum],
            histogram[1][histogram_maximum],
            out=image,
        )

    if normalise:
        image[:] = normalise_array(image)

    return image
