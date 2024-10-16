# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import math

import numpy as np

from histalign.backend.models import (
    AlignmentSettings,
    Orientation,
    VolumeSettings,
)
from histalign.backend.models.errors import InvalidOrientationError


def compute_normal(settings: VolumeSettings) -> list[float]:
    pitch_radians = math.radians(settings.pitch)
    yaw_radians = math.radians(settings.yaw)

    match settings.orientation:
        case Orientation.CORONAL:
            normal = [
                math.cos(yaw_radians) * math.cos(pitch_radians),
                -math.sin(pitch_radians),
                -math.sin(yaw_radians) * math.cos(pitch_radians),
            ]
        case Orientation.HORIZONTAL:
            normal = [
                math.sin(pitch_radians),
                math.cos(yaw_radians) * math.cos(pitch_radians),
                math.sin(yaw_radians) * math.cos(pitch_radians),
            ]
        case Orientation.SAGITTAL:
            normal = [
                math.sin(yaw_radians) * math.cos(pitch_radians),
                math.sin(pitch_radians),
                math.cos(yaw_radians) * math.cos(pitch_radians),
            ]
        case other:
            # Should be impossible thanks to pydantic
            raise InvalidOrientationError(other)

    return normal


def compute_origin_from_orientation(
    center: list[float] | tuple[float, ...], settings: VolumeSettings
) -> list[float]:
    if len(center) != 3:
        raise ValueError(f"Expected center with 3 coordinates, got {len(center)}.")

    # vedo computes the center with float precision but offset calculations assume
    # integer values.
    origin = list(map(math.ceil, center))

    match settings.orientation:
        case Orientation.CORONAL:
            # Increasing the offset should bring the user more anterior, hence take
            # away the offset to the center.
            # Also, just like the max value of int8 is 127, the center 0-value needs
            # to be shifted one back. (i.e., an axis with length 10 can have an
            # offset between (10 // 2 = 5) and (10 // 2 - 1 + int(10 % 2)).
            origin[0] -= 1
            origin[0] -= settings.offset
        case Orientation.HORIZONTAL:
            origin[1] += settings.offset
        case Orientation.SAGITTAL:
            origin[2] += settings.offset
        case other:
            # Should be impossible thanks to pydantic
            raise InvalidOrientationError(other)

    return origin
