# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from contextlib import suppress
from typing import Optional, TypeVar

import numpy as np
from PySide6 import QtGui, QtWidgets

from histalign.frontend.themes import is_light_colour

_T = TypeVar("_T")

_available_colour_tables = ("grey", "red", "green", "blue", "cyan", "magenta", "yellow")

gray_colour_table = np.array(
    [255 << 24 | i << 16 | i << 8 | i for i in range(2**8)],
    dtype=np.uint32,
)


class FakeQtABC:
    """A fake ABC class to use with QObjects.

    It is fake since it does not directly inherit ABC. Instead, the class implements
    an algorithm inspired by ABCs to ensure there aren't any abstractmethod-decorated
    methods left in the class being instantiated.
    """

    def __init__(self) -> None:
        abstract_methods = []
        for attribute_name in dir(self):
            # Supress RuntimeError since Qt throws an error when trying to getattr
            # attributes from the QObject before __init__ completely finishes. We can
            # still detect abstract methods from custom classes.
            with suppress(RuntimeError):
                if (
                    (
                        hasattr(self.__class__, attribute_name)
                        and isinstance(
                            (method := getattr(self.__class__, attribute_name)),
                            property,
                        )
                    )
                    or callable((method := getattr(self, attribute_name)))
                ) and (
                    hasattr(method, "__isabstractmethod__")
                    and method.__isabstractmethod__
                ):
                    abstract_methods.append(attribute_name)

        if abstract_methods:
            raise TypeError(
                f"Can't instantiate abstract class "
                f"{self.__class__.__qualname__} with abstract "
                f"method{'s' if len(abstract_methods) > 1 else ''} "
                f"{', '.join(abstract_methods)}"
            )


def connect_single_shot_slot(signal: object, slot: object) -> None:
    """Set up a single-use signal.

    This function takes advantage of the fact signals will always call slots in the
    order the slots were connected.

    Taken from this[1] StackOverflow answer.

    Args:
        signal (object): Signal to connect to.
        slot (object): Slot to connect to `signal`.

    References:
        [1]: https://stackoverflow.com/a/14251406
    """

    def sever_connection() -> None:
        signal.disconnect(slot)
        signal.disconnect(sever_connection)

    signal.connect(slot)
    signal.connect(sever_connection)


def find_parent(widget: QtWidgets.QWidget, parent_type: type[_T]) -> Optional[_T]:
    parent = None
    while (parent_ := widget.parent()) is not None:
        if isinstance(parent_, parent_type):
            parent = parent_
        widget = parent_

    return parent


def get_colour_table(colour: str, alpha: int = 255, threshold: int = 1) -> np.ndarray:
    if colour not in _available_colour_tables:
        raise ValueError(
            f"Invalid colour for table. Allowed values are {_available_colour_tables}."
        )

    match colour:
        case "grey":
            mask = 255 << 16 | 255 << 8 | 255
        case "red":
            mask = 255 << 16
        case "green":
            mask = 255 << 8
        case "blue":
            mask = 255
        case "cyan":
            mask = 255 << 8 | 255
        case "magenta":
            mask = 255 << 16 | 255
        case "yellow":
            mask = 255 << 16 | 255 << 8
        case _:
            raise ValueError("Invalid stain.")

    mask = mask | alpha << 24

    colour_table = gray_colour_table & mask
    colour_table[:threshold] = 0

    return colour_table


def lua_aware_shift(
    colour: QtGui.QColor, shift: int, away: bool = True
) -> QtGui.QColor:
    """Shifts a colour darker or lighter.

    In the case of a light colour and `away=True`, the returned colour will be shifted
    to a darker colour by `shift`, and vice versa for a dark colour.
    In the case of a light colour and `away=False`, the returned colour will be shifted
    to a lighter colour by `shift`, and vice versa for a dark colour.

    Args:
        colour (QtGui.QColor): Colour to shift.
        shift (int): Positive shift value to modify the colour by.
        away (bool, optional):
            Whether the colour should be shifted towards the opposite lua category or
            towards its own.

    Returns:
        QtGui.QColor: The shifted colour.
    """
    shift = 100 + shift

    if (is_light_colour(colour) and away) or (not is_light_colour(colour) and not away):
        colour = colour.darker(shift)
    else:
        colour = colour.lighter(shift)

    return colour


def np_to_qimage(
    array: np.ndarray, format: Optional[QtGui.QImage.Format] = None
) -> QtGui.QImage:
    if format is None:
        match array.dtype:
            case np.uint8:
                format = QtGui.QImage.Format.Format_Grayscale8
            case np.uint16:
                format = QtGui.QImage.Format.Format_Grayscale16
            case np.uint32:
                format = QtGui.QImage.Format.Format_Grayscale32
            case other:
                raise ValueError(
                    f"Cannot infer QImage format from '{other}' numpy datatype."
                )

    return QtGui.QImage(
        array.tobytes(),
        array.shape[1],
        array.shape[0],
        array.shape[1] * array.itemsize,
        format,
    )


def np_to_qpixmap(
    array: np.ndarray, format: Optional[QtGui.QImage.Format] = None
) -> QtGui.QPixmap:
    return QtGui.QPixmap.fromImage(np_to_qimage(array, format))
