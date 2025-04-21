# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from abc import ABC
from datetime import datetime
from enum import Enum, IntEnum
from functools import lru_cache
import hashlib
from pathlib import Path
from typing import Any, Optional

from pydantic import (
    BaseModel,
    computed_field,
    DirectoryPath,
    Field,
    field_serializer,
    field_validator,
    FilePath,
    model_validator,
    ValidationInfo,
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


class QuantificationMeasure(str, Enum):
    AVERAGE_FLUORESCENCE = "average_fluorescence"
    CORTICAL_DEPTH = "cortical_depth"


class Quantification(Enum):
    """Enum of supported quantification measures."""

    AVERAGE_FLUORESCENCE = "averagefluorescence"
    CELL_COUNTING = "cellcounting"

    @classmethod
    @lru_cache
    def values(cls) -> list[str]:
        """Returns the values of the enum's variants.

        Returns:
            list[str]: The list of values of the enum's variants.
        """
        return [key.value for key in cls]

    @classmethod
    def _missing_(cls, value: Any) -> Quantification:
        # Transform most common forms of representing the names. Remove " ", "_",
        # and "-" and check if that is valid. This makes for cleaner code at the call
        # site.
        if isinstance(value, str):
            value = "".join(value.lower().replace("_", "").replace("-", "").split(" "))
            if value in cls.values():
                return Quantification(value)

        return super()._missing_(value)


class HistologySettings(BaseModel, validate_assignment=True):
    rotation: float = 0.0
    translation_x: int = 0
    translation_y: int = 0
    scale_x: float = 1.0
    scale_y: float = 1.0
    shear_x: float = 0.0
    shear_y: float = 0.0

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, value: float) -> float:
        if not -90.0 <= value <= 90.0:
            raise ValueError("rotation is limited to the range -90 to 90")
        return value

    @field_validator("translation_x", "translation_y")
    @classmethod
    def validate_translation(cls, value: int) -> int:
        if not -5000 <= value <= 5000:
            raise ValueError("translation is limited to the range -5000 to 5000")
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

        if (
            not -axis_length // 2 + (axis_length % 2 == 0) <= value <= axis_length // 2
            and axis_length != value != 0
        ):
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


class MeasureSettings(BaseModel, ABC):
    pass


class AverageFluorescenceMeasureSettings(MeasureSettings, validate_assignment=True):
    approach: str
    structures: list[str]


class CorticalDepthMeasureSettings(MeasureSettings, validate_assignment=True):
    cortex_structure: str
    structures: list[str]


class QuantificationSettings(BaseModel, validate_assignment=True):
    """Model used to store quantification settings to run in a QuantifierThread."""

    source_directory: DirectoryPath
    """
    User-friendly path to the source image directory used in the alignment. For slice
    quantification, this is where the images will be loaded from. For volume
    quantification, this is not relevant as the volume is stored in the alignment
    directory.
    """
    alignment_directory: DirectoryPath
    """Directory under the current project where the alignment settings are stored."""
    resolution: Resolution
    """Resolution of the project."""
    quantification: Quantification
    """Quantification measure to use."""
    on_volume: bool
    """Whether to run the quantification on a volume or individual slices."""
    structures: list[str]
    """List of the structures to quantify."""
    channel_index: str
    """Optional, alternative index to run the quantification on."""
    channel_regex: str
    """Regex identifying the part of the path to replace with the new index."""

    @field_validator("channel_index")
    @classmethod
    def validate_regex(cls, value: str) -> str:
        """Validates the channel index is a valid string representation of an integer.

        Args:
            value (str): String representation of an integer.

        Returns:
            str: The string as-is.

        Raises:
            ValueError: When the value cannot be interpreted as an integer.
        """
        try:
            int(value)
        except ValueError:
            if value != "":
                raise ValueError("could not interpret input as an integer") from None

        return value

    @model_validator(mode="after")
    def clear_unused(self) -> QuantificationSettings:
        """Clears channel index and regex when `on_volume` is set.

        Returns:
            QuantificationSettings: Self with fields cleared.
        """
        # Avoid potential errors down the line by clearing fields that should not be
        # used.
        if self.on_volume:
            # Avoid RecursionError by only clearing non-cleared values
            if self.channel_index:
                self.channel_index = ""
            if self.channel_regex:
                self.channel_regex = ""

        return self

    @model_validator(mode="after")
    def sanitise_channel_values(self) -> QuantificationSettings:
        """Ensures both channel index and regex are set.

        If not, they are both cleared.

        Returns:
            QuantificationSettings: Self with sanitised fields.
        """
        if self.channel_regex and not self.channel_index:
            _module_logger.warning(
                "Model initialised with a channel regex but not a channel index. "
                "Considering both as blank."
            )
            self.channel_regex = ""
        elif not self.channel_regex and self.channel_index:
            _module_logger.warning(
                "Model initialised with a channel index but not a channel regex. "
                "Considering both as blank."
            )
            self.channel_index = ""

        return self


class QuantificationResults(BaseModel, validate_assignment=True):
    settings: QuantificationSettings
    data: dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=datetime.now, frozen=True)

    @computed_field
    @property
    def hash(self) -> str:
        hash_string = f"{self.settings.model_dump_json(serialize_as_any=True)}"
        hash_string += "".join(self.data.keys())
        return hashlib.md5(hash_string.encode("UTF-8")).hexdigest()

    @field_serializer("timestamp")
    def serialise_timestamp(self, value: datetime) -> str:
        return value.isoformat()


class VolumeBuildingSettings(BaseModel, validate_assignment=True):
    alignment_directory: DirectoryPath
    original_directory: DirectoryPath
    resolution: Resolution
    z_stack_regex: str
    channel_regex: str
    channel_index: str

    @field_validator("channel_index")
    @classmethod
    def validate_regex(cls, value: str | int) -> str:
        try:
            value = int(value)
        except ValueError:
            if value != "":
                raise ValueError("could not interpret input as an integer") from None

        return str(value)
