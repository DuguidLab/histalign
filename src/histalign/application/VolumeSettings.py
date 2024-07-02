# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

import pydantic


class VolumeSettings(pydantic.BaseModel):
    origin: typing.Optional[tuple[float, float, float]] = None
    leaning_angle: int = 0
    axes: tuple[int, int] = (0, 1)
    offset: int = 0
