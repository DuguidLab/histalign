# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import pydantic


class HistologySettings(pydantic.BaseModel):
    rotation_angle: int = 0
    x_translation: int = 0
    y_translation: int = 0
    x_scale: float = 1.0
    y_scale: float = 1.0
    x_shear: float = 0.0
    y_shear: float = 0.0
