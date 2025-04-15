# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import os

from histalign.io import DATA_ROOT

BASE_ANNOTATION_URL = (
    "https://download.alleninstitute.org/informatics-archive/"
    "current-release/mouse_ccf/annotation/ccf_2017"
)
BASE_ATLAS_URL = (
    "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf"
)
BASE_MASK_URL = (
    "https://download.alleninstitute.org/informatics-archive/"
    "current-release/mouse_ccf/annotation/ccf_2017/structure_masks"
)

ANNOTATION_ROOT_DIRECTORY = DATA_ROOT / "annotations"
os.makedirs(ANNOTATION_ROOT_DIRECTORY, exist_ok=True)
ATLAS_ROOT_DIRECTORY = DATA_ROOT / "atlases"
os.makedirs(ATLAS_ROOT_DIRECTORY, exist_ok=True)
MASK_ROOT_DIRECTORY = DATA_ROOT / "structure_masks"
os.makedirs(MASK_ROOT_DIRECTORY, exist_ok=True)
