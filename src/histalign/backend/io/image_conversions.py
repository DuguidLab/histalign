# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import numpy as np


def convert_to_rgb32(image: np.ndarray) -> np.ndarray:
    if image.dtype != np.uint8:
        scaling_to_8_bit = np.iinfo(image.dtype).max / 256
        image = image.astype(float)
        image /= scaling_to_8_bit
        image = image.astype(np.uint8)

    image = image.astype(np.uint32)
    image = np.array(
        list(map(lambda x: (x << 16) + (x << 8) + x, image)), dtype=np.uint32
    )

    image += (2**8 - 1) << 24

    return image


def mask_off_colour(image: np.ndarray, colour: str) -> np.ndarray:
    if image.dtype != np.uint32:
        raise ValueError("Masking of colour only available on 32-bit images.")

    match colour.lower():
        case "red":
            mask = (2**8 - 1) << 16
        case "green":
            mask = (2**8 - 1) << 8
        case "blue":
            mask = 2**8 - 1
        case _:
            raise ValueError("Invalid colour.")

    image = np.array(list(map(lambda x: x & ~np.uint32(mask), image)), dtype=np.uint32)

    return image
