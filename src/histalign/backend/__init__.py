# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from enum import IntEnum


# An enum to use for custom roles in Qt models
class UserRole(IntEnum):
    # CCF
    IS_DISPLAYABLE = 0x0100
    SHORTENED_NAME = 0x0101
    NAME_NO_ACRONYM = 0x0102
