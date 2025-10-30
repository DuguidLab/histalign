# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from collections.abc import Callable
from typing import Any, Literal

import numpy as np
from skimage.transform import rescale

Transform = Literal["downscale", "rgb2gray"]


def get_appropriate_transform_function(transform: Transform) -> Callable:
    match transform:
        case "downscale":
            return downscaling_transform
        case "rgb2gray":
            return rgb_to_gray_transform
        case _:
            raise ValueError(f"Unknown transform '{transform}'.")


def downscaling_transform(
    image: np.ndarray,
    downscaling_factor: int = 4,
    downscaling_order: int = 3,
    naive: bool = False,
    **kwargs,
) -> np.ndarray:
    if naive:
        return image[::downscaling_factor, ::downscaling_factor]

    array: np.ndarray = rescale(
        image,
        1 / downscaling_factor,
        order=downscaling_order,
        preserve_range=True,
        anti_aliasing=True,
    )
    return array


def rgb_to_gray_transform(
    series: np.ndarray, channel_index: int, **kwargs: Any
) -> np.ndarray:
    """Convert an RGB image to grayscale using Luma conversion.

    Note this is not perfect and does not reflect the transformation done by, e.g.,
    ImageJ (they seem to do some fancier scaling).

    Args:
        image: Series containing images with RGB channels.
        channel_index: Index of the channels.

    Returns:
        The image as grayscale. This will have a shape similar to the input image
        without the channel.

    References:
        Factors: https://en.wikipedia.org/wiki/Grayscale#Luma_coding_in_video_systems
    """
    minimum = series.min()
    maximum = series.max()
    range_ = maximum - minimum

    transformed = (
        series.take(0, channel_index) * 0.299
        + series.take(1, channel_index) * 0.587
        + series.take(2, channel_index) * 0.114
    )

    transformed -= transformed.min()
    transformed /= transformed.max()
    transformed *= range_
    transformed += minimum

    return transformed.astype(series.dtype)
