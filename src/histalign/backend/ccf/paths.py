# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import os
from typing import Any
from typing import Literal

from histalign.backend.ccf import ATLAS_ROOT_DIRECTORY, DATA_ROOT, MASK_ROOT_DIRECTORY
from histalign.backend.models import Resolution


def get_atlas_path(
    resolution: Resolution,
    atlas_type: Literal["average_template", "ara_nissl"] = "average_template",
):
    return str(ATLAS_ROOT_DIRECTORY / f"{atlas_type}_{resolution.value}.nrrd")


def get_structure_id(structure_name: str, resolution: Resolution) -> int:
    return get_structure_tree(resolution).get_structures_by_name([structure_name])[0][
        "id"
    ]


def get_structure_mask_path(structure_name: str, resolution: Resolution) -> str:
    structure_id = get_structure_id(structure_name, resolution)
    mask_directory = MASK_ROOT_DIRECTORY / f"structure_masks_{resolution.value}"

    return str(mask_directory / f"structure_{structure_id}.nrrd")


def get_structure_tree(resolution: Resolution) -> Any:
    # This takes a long time to import (~4 seconds on my machine) so only "lazily"
    # import it.
    from allensdk.core.reference_space_cache import ReferenceSpaceCache

    return ReferenceSpaceCache(
        resolution=resolution.value,
        reference_space_key=os.path.join("annotation", "ccf_2017"),
        manifest=str(DATA_ROOT / f"manifest.json"),
    ).get_structure_tree()


def get_structures_hierarchy_path() -> str:
    path = DATA_ROOT / f"structures.json"

    # Easiest option to have the Allen SDK do the work for us
    if not path.exists():
        get_structure_tree(Resolution.MICRONS_100)

    return str(path)
