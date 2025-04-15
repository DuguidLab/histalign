# SPDX-FileCopyrightText: 2025-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import importlib.resources
from pathlib import Path

# noinspection PyTypeChecker
RESOURCES_ROOT = Path(
    importlib.resources.files("histalign.resources").joinpath(".")
).resolve()
ICONS_ROOT = RESOURCES_ROOT / "icons"
