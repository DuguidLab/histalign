# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

"""This module provides metadata helpers for file paths and IDs/names/acronyms."""

import os
from typing import Literal

from allensdk.core.structure_tree import StructureTree

from histalign.backend.ccf import (
    ANNOTATION_ROOT_DIRECTORY,
    ATLAS_ROOT_DIRECTORY,
    DATA_ROOT,
    MASK_ROOT_DIRECTORY,
)
from histalign.backend.models import Resolution


def get_atlas_path(
    resolution: Resolution,
    atlas_type: Literal["average_template", "ara_nissl"] = "average_template",
) -> str:
    """Returns the path where an atlas file with the given properties would be.

    Note the path only indicates where the file is if it is available. If the path
    does not exist, the file still needs to be downloaded.

    Args:
        resolution (Resolution): Resolution of the atlas.
        atlas_type (Literal["average_template", "ara_nissl"], optional):
            Type of the atlas.

    Returns:
        str: The path to the would-be file.
    """
    return str(ATLAS_ROOT_DIRECTORY / f"{atlas_type}_{resolution.value}.nrrd")


def get_annotation_path(resolution: Resolution) -> str:
    """Returns the path where an annotation file with the given properties would be.

    Note the path only indicates where the file is if it is available. If the path
    does not exist, the file still needs to be downloaded.

    Args:
        resolution (Resolution): Resolution of the annotation volume.

    Returns:
        str: The path to the would-be file.
    """
    return str(ANNOTATION_ROOT_DIRECTORY / f"annotation_{resolution}.nrrd")


def get_structure_id(structure_name: str, resolution: Resolution) -> int:
    """Returns the ID of the given structure.

    Args:
        structure_name (str): Name of the structure.
        resolution (Resolution): Resolution of the structure tree to use.

    Returns:
        int: The ID of the structure.
    """
    return get_structure_tree(resolution).get_structures_by_name([structure_name])[0][
        "id"
    ]


def get_structure_name_by_acronym(acronym: str, resolution: Resolution) -> str:
    """Returns the name of the structure with the given acronym.

    Args:
        acronym (str): Acronym to search for.
        resolution (Resolution): Resolution of the structure tree to use.

    Returns:
        str: Name of the structure with acronym `acronym`.
    """
    return get_structure_tree(resolution).get_structures_by_acronym([acronym.strip()])[
        0
    ]["name"]


def get_structure_mask_path(structure_name: str, resolution: Resolution) -> str:
    """Returns the path where a mask file with the given properties would be.

    Note the path only indicates where the file is if it is available. If the path
    does not exist, the file still needs to be downloaded.

    Args:
        structure_name (str): Name of the structure.
        resolution (Resolution): Resolution of the mask.

    Returns:
        str: The path to the would-be file.
    """
    structure_id = get_structure_id(structure_name, resolution)
    mask_directory = MASK_ROOT_DIRECTORY / f"structure_masks_{resolution.value}"

    return str(mask_directory / f"structure_{structure_id}.nrrd")


def get_structure_tree(resolution: Resolution) -> StructureTree:
    """Returns a StructureTree from the manifest.

    Args:
        resolution (Resolution): Resolution of the tree.

    Returns:
        StructureTree: The structure tree for the given resolution.
    """
    # This takes a long time to import (~4 seconds on my machine) so only "lazily"
    # import it.
    from allensdk.core.reference_space_cache import ReferenceSpaceCache

    return ReferenceSpaceCache(
        resolution=resolution.value,
        reference_space_key=os.path.join("annotation", "ccf_2017"),
        manifest=str(DATA_ROOT / f"manifest.json"),
    ).get_structure_tree()


def get_structures_hierarchy_path() -> str:
    """Returns the path to the structure hierarchy file.

    Note this automatically downloads the file if it doesn't exist.

    Returns:
        str: The path to the `structures.json` hierarchy file.
    """
    path = DATA_ROOT / f"structures.json"

    # Easiest option to have the Allen SDK do the work for us
    if not path.exists():
        get_structure_tree(Resolution.MICRONS_100)

    return str(path)
