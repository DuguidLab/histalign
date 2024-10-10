# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from contextlib import suppress


class FakeQtABC:
    """A fake ABC class to use with QObjects.

    It is fake since it does not directly inherit ABC. Instead, the class implements
    an algorithm inspired by ABCs to ensure there aren't any abstractmethod-decorated
    methods left in the class being instantiated.
    """

    def __init__(self) -> None:
        for attribute_name in dir(self):
            # Supress RuntimeError since Qt throws an error when trying to getattr
            # attributes from the QObject before __init__ completely finishes. We can
            # still detect abstract methods from custom classes.
            with suppress(RuntimeError):
                if callable((method := getattr(self, attribute_name))) and hasattr(
                    method, "__isabstractmethod__"
                ):
                    raise TypeError(
                        f"Can't instantiate abstract class "
                        f"{self.__class__.__qualname__} with abstract method "
                        f"{attribute_name}"
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
