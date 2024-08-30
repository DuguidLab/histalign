# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from enum import Enum, IntEnum
from pathlib import Path
from typing import Optional

from pydantic import (
    BaseModel,
    DirectoryPath,
    FilePath,
    ValidationInfo,
    field_serializer,
    field_validator,
)


class Orientation(str, Enum):
    CORONAL = "coronal"
    HORIZONTAL = "horizontal"
    SAGITTAL = "sagittal"


class Resolution(IntEnum):
    MICRONS_10 = 10
    MICRONS_25 = 25
    MICRONS_50 = 50
    MICRONS_100 = 100


class HistologySettings(BaseModel, validate_assignment=True):
    rotation: int = 0
    translation_x: int = 0
    translation_y: int = 0
    scale_x: float = 1.0
    scale_y: float = 1.0
    shear_x: float = 0.0
    shear_y: float = 0.0

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, value: int) -> int:
        if not -90 <= value <= 90:
            raise ValueError("rotation is limited to the range -90 to 90")
        return value

    @field_validator("translation_x", "translation_y")
    @classmethod
    def validate_translation(cls, value: int) -> int:
        if not -500 <= value <= 500:
            raise ValueError("translation is limited to the range -500 to 500")
        return value

    @field_validator("scale_x", "scale_y")
    @classmethod
    def validate_scale(cls, value: float) -> float:
        if not 0.01 <= value <= 3.0:
            raise ValueError("scale is limited to the range 0.01 to 3.0")
        return value

    @field_validator("shear_x", "shear_y")
    @classmethod
    def validate_shear(cls, value: float) -> float:
        if not -1.0 <= value <= 1.0:
            raise ValueError("shear is limited to the range -1.0 to 1.0")
        return value


class VolumeSettings(BaseModel, validate_assignment=True):
    orientation: Orientation
    resolution: Resolution
    shape: tuple[int, int, int] = (0, 0, 0)
    pitch: int = 0
    yaw: int = 0
    offset: int = 0

    @field_validator("shape")
    @classmethod
    def validate_shape(cls, value: tuple[int, int, int]) -> tuple[int, int, int]:
        for dimension in value:
            if dimension < 1:
                raise ValueError("shape axes should all be positive and non-zero")
        return value

    @field_validator("pitch", "yaw")
    @classmethod
    def validate_principle_axes(cls, value: int) -> int:
        if not -90 <= value <= 90:
            raise ValueError("principle axes are limited to the range -90 to 90")
        return value

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, value: int, info: ValidationInfo) -> int:
        match Orientation(info.data["orientation"]):
            case Orientation.CORONAL:
                axis_length = info.data["shape"][0]
            case Orientation.HORIZONTAL:
                axis_length = info.data["shape"][1]
            case Orientation.SAGITTAL:
                axis_length = info.data["shape"][2]
            case _:
                raise Exception("Panic: assert not reached")

        if not -axis_length // 2 <= value <= axis_length // 2 + (axis_length % 2 != 0):
            raise ValueError("offset should be <= half of orientation-relevant axis")
        return value


class AlignmentSettings(BaseModel, validate_assignment=True):
    volume_path: Path
    volume_scaling: float = 1.0
    volume_settings: VolumeSettings

    histology_path: Optional[FilePath] = None
    histology_scaling: float = 1.0
    histology_downsampling: int = 1
    histology_settings: HistologySettings = HistologySettings()

    @field_validator("volume_scaling", "histology_scaling")
    @classmethod
    def validate_scaling(cls, value: float) -> float:
        if not 0.01 <= value:
            raise ValueError("scaling should be positive and non-zero")
        return value

    @field_validator("histology_downsampling")
    @classmethod
    def validate_downsampling(cls, value: int) -> int:
        if not 1 <= value:
            raise ValueError("downsampling should be positive and non-zero")
        return value

    @field_serializer("volume_path", "histology_path")
    def serialise_path(self, value: Path) -> Optional[str]:
        if value is None:
            return value

        return str(value)


class ProjectSettings(BaseModel, validate_assignment=True):
    project_path: DirectoryPath
    orientation: Orientation
    resolution: Resolution

    @field_serializer("project_path")
    def serialise_path(self, value: Path) -> str:
        return str(value)
