# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from collections.abc import Callable
from typing import Literal

import numpy as np
from skimage.transform import rescale

Transform = Literal["downscale"]


def get_appropriate_transform_function(transform: Transform) -> Callable:
    match transform:
        case "downscale":
            return downscaling_transform
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

    return rescale(
        image,
        1 / downscaling_factor,
        order=downscaling_order,
        preserve_range=True,
        anti_aliasing=True,
    )
