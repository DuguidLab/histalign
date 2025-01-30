# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from contextlib import suppress

import numpy as np

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
