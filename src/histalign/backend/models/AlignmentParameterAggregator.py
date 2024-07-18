# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import pydantic


class AlignmentParameterAggregator(pydantic.BaseModel):
    # Volume
    volume_file_path: str = ""
    leaning_angle: int = 0
    offset: int = 0
    volume_scaling_factor: float = 1.0
    volume_pixel_width: int = 0
    volume_pixel_height: int = 0

    # Histology
    histology_file_path: str = ""
    rotation_angle: int = 0
    x_translation: int = 0
    y_translation: int = 0
    x_scale: float = 1.0
    y_scale: float = 1.0
    x_shear: float = 0.0
    y_shear: float = 0.0
    histology_scaling_factor: float = 1.0
    histology_pixel_width: int = 0
    histology_pixel_height: int = 0
    downsampling_factor: float = 1.0
