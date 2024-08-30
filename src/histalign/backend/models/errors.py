# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Any

from histalign.backend.models import Orientation, Resolution


class InvalidOrientationError(Exception):
    def __init__(self, invalid_object: Any) -> None:
        message = (
            f"Orientations must be of type '{Orientation}', "
            f"received type '{type(invalid_object)}'."
        )

        super().__init__(message)


class InvalidResolutionError(Exception):
    def __init__(self, invalid_object: Any) -> None:
        message = (
            f"Resolutions must be of type '{Resolution}', "
            f"received type '{type(invalid_object)}'."
        )

        super().__init__(message)
