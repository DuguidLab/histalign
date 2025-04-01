# SPDX-FileCopyrightText: 2025-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from enum import Enum

from PySide6 import QtCore


class UserEventType(Enum):
    AboutToCollapse = QtCore.QEvent.Type(QtCore.QEvent.registerEventType())
    Collapsed = QtCore.QEvent.Type(QtCore.QEvent.registerEventType())
    Expanded = QtCore.QEvent.Type(QtCore.QEvent.registerEventType())


class AboutToCollapseEvent(QtCore.QEvent):
    def __init__(self) -> None:
        super().__init__(UserEventType.AboutToCollapse.value)


class CollapsedEvent(QtCore.QEvent):
    def __init__(self) -> None:
        super().__init__(UserEventType.Collapsed.value)


class ExpandedEvent(QtCore.QEvent):
    def __init__(self) -> None:
        super().__init__(UserEventType.Expanded.value)
