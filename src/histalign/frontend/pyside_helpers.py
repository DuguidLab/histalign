# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from PySide6 import QtCore, QtGui, QtWidgets


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
