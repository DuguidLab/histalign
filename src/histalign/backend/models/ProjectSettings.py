# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierDelrée@protonmail.com>
#
# SPDX-License-Identifier: MIT

import pydantic


class ProjectSettings(pydantic.BaseModel):
    project_directory_path: pydantic.DirectoryPath
    atlas_resolution: int

    @pydantic.field_validator("atlas_resolution")
    @classmethod
    def validate_resolution(cls, value: int) -> int:
        if value not in (10, 25, 50, 100):
            raise ValueError("Atlas resolution is not valid.")
        return value
