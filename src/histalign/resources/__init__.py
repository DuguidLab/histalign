# SPDX-FileCopyrightText: 2025-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

"""This sub-package is used to store the resources required by the application."""

import importlib.resources
from pathlib import Path

# noinspection PyTypeChecker
RESOURCES_ROOT = Path(
    importlib.resources.files("histalign.resources").joinpath(".")  # type: ignore[arg-type]
).resolve()
ICONS_ROOT = RESOURCES_ROOT / "icons"
