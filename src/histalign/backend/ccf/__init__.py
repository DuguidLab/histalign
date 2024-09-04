# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import os
from pathlib import Path

from PySide6 import QtCore

BASE_ATLAS_URL = (
    "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf"
)
BASE_MASK_URL = (
    "https://download.alleninstitute.org/informatics-archive/"
    "current-release/mouse_ccf/annotation/ccf_2017/structure_masks"
)

data_directories = QtCore.QStandardPaths.standardLocations(
    QtCore.QStandardPaths.GenericDataLocation
)
if not data_directories:
    raise ValueError("Cannot find a data directory.")
DATA_ROOT = Path(data_directories[0]) / "histalign"
del data_directories

ATLAS_ROOT_DIRECTORY = DATA_ROOT / "atlases"
os.makedirs(ATLAS_ROOT_DIRECTORY, exist_ok=True)
MASK_ROOT_DIRECTORY = DATA_ROOT / "structure_masks"
os.makedirs(MASK_ROOT_DIRECTORY, exist_ok=True)
