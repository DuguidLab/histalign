# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from collections.abc import Sequence
from enum import Enum
from typing import Any, get_args, Optional

import numpy as np
from pydantic import (
    BaseModel,
    field_serializer,
    field_validator,
    PositiveFloat,
    PositiveInt,
    ValidationInfo,
)
from pydantic_core import PydanticCustomError

from histalign.io.image import DimensionOrder


def prune_metadata(
    metadata: "OmeXml",
    to_order: DimensionOrder,
) -> "OmeXml":
    """Removes metadata attributes that are incompatible with `to_order`.

    Note that order is also automatically updated with `to_order`.

    Args:
        metadata (OmeXml): Metadata object to prune.
        to_order (DimensionOrder): Dimension order to prune for.

    Returns:
        OmeXml: The pruned metadata.
    """
    pruned_metadata = metadata.model_copy(deep=True)

    pruned_metadata.DimensionOrder = to_order

    if "C" not in to_order.value:
        pruned_metadata.SizeC = None
        pruned_metadata.Channel = []
    if "Z" not in to_order.value:
        pruned_metadata.SizeZ = None

    return pruned_metadata


@field_validator("*", mode="before")
def validate_none_as_default(cls, value: Any, info: ValidationInfo) -> Any:
    """Validates `value` as the default field value if `value` is `None`.

    Args:
        value (Any): Value to validate.
        info (ValidationInfo): Validation info for the current field.

    Returns:
        Any: The validated value. This is `None` if the field is a Union containing
             `None`, the field's default value if it does not, the input value if the
             input is not `None`.
    """
    if (
        value is None
        # If field is `typing.Optional`, allow `None` value as-is in case the default
        # is not `None`.
        and type(None) not in get_args(cls.model_fields[info.field_name].annotation)
        and (default := cls.model_fields[info.field_name].get_default()) is not None
    ):
        return default
    else:
        return value


class ChannelColor:
    value: np.int32

    def __init__(
        self,
        value: Optional[int | np.int32 | Sequence | dict] = None,
        *,
        red: int | np.uint8 = 255,
        green: int | np.uint8 = 255,
        blue: int | np.uint8 = 255,
        alpha: int | np.uint8 = 255,
    ) -> None:
        if value is not None:
            if isinstance(value, Sequence):
                if len(value) >= 3:
                    red = value[0]
                    green = value[1]
                    blue = value[2]

                    if len(value) == 4:
                        alpha = value[3]
                    elif len(value) > 4:
                        raise ValueError("Received too many channels for color.")
            elif isinstance(value, dict):
                red = value.get("red")
                green = value.get("green")
                blue = value.get("blue")
                alpha = value.get("alpha") or alpha

                if red is None or green is None or blue is None:
                    raise ValueError("Missing channel for color.")
            else:
                self.value = np.int32(value)

        if not hasattr(self, "value"):
            self.value = self._from_channels(red, green, blue, alpha)

    def to_channels(self) -> dict[str, int]:
        red = int(np.uint8(self.value >> 24))
        green = int(np.uint8(self.value >> 16 & 255))
        blue = int(np.uint8(self.value >> 8 & 255))
        alpha = int(np.uint8(self.value & 255))

        return {"red": red, "green": green, "blue": blue, "alpha": alpha}

    @staticmethod
    def _from_channels(
        red: int | np.uint8,
        blue: int | np.uint8,
        green: int | np.uint8,
        alpha: int | np.uint8 = 255,
    ) -> np.int32:
        # Validate channels are valid uint8
        if isinstance(red, int):
            red = np.uint8(red)
        if isinstance(green, int):
            green = np.uint8(green)
        if isinstance(blue, int):
            blue = np.uint8(blue)
        if isinstance(alpha, int):
            alpha = np.uint8(alpha)

        return np.int32(
            np.uint32(red) << 24
            | np.uint32(green) << 16
            | np.uint32(blue) << 8
            | np.uint32(alpha)
        )

    def __repr__(self):
        red, green, blue, alpha = self.to_channels().values()
        return f"Color(red={red}, green={green}, blue={blue}, alpha={alpha})"


class PixelType(Enum):
    int8 = "int8"
    int16 = "int16"
    int32 = "int32"
    uint8 = "uint8"
    uint16 = "uint16"
    uint32 = "uint32"
    float32 = "float32"
    float64 = "float64"
    bool = "bool"

    @classmethod
    def _missing_(cls, value: Any) -> "PixelType":
        try:
            return cls(np.dtype(value).name)
        except TypeError:
            return super()._missing_(value)


class UnitsLength(Enum):
    nano = "nm"
    micro = "µm"
    milli = "mm"
    centi = "cm"
    inches = "in"

    @classmethod
    def _missing_(cls, value: Any) -> "UnitsLength":
        if isinstance(value, str):
            match value:
                case "nano":
                    return cls("nm")
                case "micro":
                    return cls("µm")
                case "milli":
                    return cls("mm")
                case "centi":
                    return cls("cm")
                case "inches":
                    return cls("in")

        return super()._missing_(value)


class OmeXmlChannel(
    BaseModel,
    use_enum_values=True,
    arbitrary_types_allowed=True,
    validate_assignment=True,
):
    Name: str
    EmissionWavelength: PositiveInt = 1
    EmissionWavelengthUnit: UnitsLength = UnitsLength.nano
    Color: ChannelColor = ChannelColor()

    _validate_none_as_default = validate_none_as_default

    @field_validator("Color", mode="before")
    @classmethod
    def validate_color(cls, value: Any) -> Color:
        if isinstance(value, ChannelColor):
            return value

        try:
            return ChannelColor(value)
        except ValueError:
            raise PydanticCustomError(
                "value_error", f"The field Color could not be built from input."
            )

    @field_serializer("Color")
    def serialise_color(self, value: Color) -> int:
        return int(value.value)


class OmeXml(BaseModel, use_enum_values=True, validate_assignment=True):
    DimensionOrder: DimensionOrder
    SizeX: PositiveInt
    SizeY: PositiveInt
    SizeC: PositiveInt = 1
    SizeZ: PositiveInt = 1
    SizeT: PositiveInt = 1
    Type: PixelType
    PhysicalSizeX: PositiveFloat = 1.0
    PhysicalSizeY: PositiveFloat = 1.0
    PhysicalSizeZ: PositiveFloat = 1.0
    PhysicalSizeXUnit: UnitsLength = UnitsLength.micro
    PhysicalSizeYUnit: UnitsLength = UnitsLength.micro
    PhysicalSizeZUnit: UnitsLength = UnitsLength.micro
    Channel: list[OmeXmlChannel]

    _validate_none_as_default = validate_none_as_default
