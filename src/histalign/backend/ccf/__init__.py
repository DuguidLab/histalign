# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

"""This sub-package handles interactions with the Allen Institute's APIs."""

import logging
import os
from pathlib import Path
import shutil
import ssl
from typing import Literal
import urllib.error
from urllib.request import urlopen

from allensdk.core.structure_tree import StructureTree

from histalign.backend.models import Resolution
from histalign.io import DATA_ROOT

BASE_ANNOTATION_URL = "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/ccf_2017"
BASE_ATLAS_URL = (
    "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf"
)
BASE_MASK_URL = "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/ccf_2017/structure_masks"

ANNOTATION_ROOT_DIRECTORY = DATA_ROOT / "annotations"
os.makedirs(ANNOTATION_ROOT_DIRECTORY, exist_ok=True)
ATLAS_ROOT_DIRECTORY = DATA_ROOT / "atlases"
os.makedirs(ATLAS_ROOT_DIRECTORY, exist_ok=True)
MASK_ROOT_DIRECTORY = DATA_ROOT / "structure_masks"
os.makedirs(MASK_ROOT_DIRECTORY, exist_ok=True)

_module_logger = logging.getLogger(__name__)


def download_atlas(
    resolution: Resolution,
    atlas_type: Literal["average_template", "ara_nissl"] = "average_template",
) -> None:
    """Downloads the atlas file for the given type and resolution.

    Args:
        resolution (Resolution): Resolution of the atlas.
        atlas_type (Literal["average_template", "ara_nissl"], optional):
            Type of the atlas.
    """
    atlas_file_name = f"{atlas_type}_{resolution.value}.nrrd"
    url = "/".join([BASE_ATLAS_URL, atlas_type, atlas_file_name])
    atlas_path = ATLAS_ROOT_DIRECTORY / atlas_file_name

    download(url, atlas_path)


def download_annotation_volume(resolution: Resolution) -> None:
    """Downloads the annotation volume file for the given resolution.

    Args:
        resolution (Resolution): Resolution of the atlas.
    """
    volume_file_name = f"annotation_{resolution}.nrrd"
    url = "/".join([BASE_ANNOTATION_URL, volume_file_name])
    volume_path = ANNOTATION_ROOT_DIRECTORY / volume_file_name

    download(url, volume_path)


def download_structure_mask(structure_name: str, resolution: Resolution) -> None:
    """Downloads the structure mask file for the given name and resolution.

    Args:
        structure_name (str): Name of the structure.
        resolution (Resolution): Resolution of the atlas.
    """
    structure_id = get_structure_id(structure_name, resolution)
    structure_file_name = f"structure_{structure_id}.nrrd"
    url = "/".join(
        [BASE_MASK_URL, f"structure_masks_{resolution.value}", structure_file_name]
    )
    structure_path = (
        MASK_ROOT_DIRECTORY
        / f"structure_masks_{resolution.value}"
        / structure_file_name
    )

    os.makedirs(structure_path.parent, exist_ok=True)

    download(url, structure_path)


def download(url: str, file_path: str | Path) -> None:
    """Downloads a file from the given URL and saves it to the given path.

    Args:
        url (str): URL to fetch.
        file_path (str | Path): Path to save the result to.
    """
    # Thin guard to not just download anything...
    if not url.startswith(BASE_ATLAS_URL) and not url.startswith(BASE_MASK_URL):
        raise ValueError("Invalid URL.")

    if isinstance(file_path, str):
        file_path = Path(file_path)
    tmp_file_path = file_path.with_suffix(f"{file_path.suffix}.tmp")

    # Allen SSL certificate is apparently not valid...
    context = get_ssl_context(check_hostname=False, check_certificate=False)
    try:
        with (
            urlopen(url, context=context) as response,
            open(tmp_file_path, "wb") as handle,
        ):
            shutil.copyfileobj(response, handle)
    except urllib.error.HTTPError:
        _module_logger.error(f"URL not found ('{url}').")

    shutil.move(tmp_file_path, file_path)


def get_ssl_context(
    check_hostname: bool = True, check_certificate: bool = True
) -> ssl.SSLContext:
    """Creates an SSL context to use with urllib.

    Args:
        check_hostname (bool, optional): Whether to enable hostname checking.
        check_certificate (bool, optional): Whether to enable certificate checking.

    Returns:
        ssl.SSLContext: An SSL context with the given options.
    """
    context = ssl.create_default_context()
    if not check_hostname:
        context.check_hostname = False
    if not check_certificate:
        context.verify_mode = ssl.CERT_NONE

    return context


def get_atlas_path(
    resolution: Resolution,
    atlas_type: Literal["average_template", "ara_nissl"] = "average_template",
    ensure_downloaded: bool = False,
) -> str:
    """Returns the path where an atlas file with the given properties should be.

    Note that without `ensure_downloaded`, the path is not guaranteed to point to an
    existing file.

    Args:
        resolution (Resolution): Resolution of the atlas.
        atlas_type (Literal["average_template", "ara_nissl"], optional):
            Type of the atlas.
        ensure_downloaded (bool, optional):
            Whether to download the atlas before returning the path if the file is not
            already available.

    Returns:
        str: The path to the would-be file.
    """
    path = str(ATLAS_ROOT_DIRECTORY / f"{atlas_type}_{resolution.value}.nrrd")
    if ensure_downloaded and not Path(path).exists():
        download_atlas(resolution, atlas_type)

    return path


def get_annotation_path(resolution: Resolution, ensure_downloaded: bool = False) -> str:
    """Returns the path where an annotation file with the given properties would be.

    Note that without `ensure_downloaded`, the path is not guaranteed to point to an
    existing file.

    Args:
        resolution (Resolution): Resolution of the annotation volume.
        ensure_downloaded (bool, optional):
            Whether to download the annotations before returning the path if the file
            is not already available.

    Returns:
        str: The path to the would-be file.
    """
    path = str(ANNOTATION_ROOT_DIRECTORY / f"annotation_{resolution}.nrrd")
    if ensure_downloaded and not Path(path).exists():
        download_annotation_volume(resolution)

    return path


def get_structure_id(structure: str, resolution: Resolution) -> int:
    """Returns the ID of the given structure.

    Args:
        structure (str): Name or acronym of the structure.
        resolution (Resolution): Resolution of the structure tree to use.

    Returns:
        int: The ID of the structure.
    """
    try:
        return get_structure_tree(resolution).get_structures_by_name([structure])[0][
            "id"
        ]
    except KeyError:
        return get_structure_tree(resolution).get_structures_by_acronym([structure])[0][
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


def get_structure_mask_path(
    structure_name: str, resolution: Resolution, ensure_downloaded: bool = False
) -> str:
    """Returns the path where a mask file with the given properties would be.

    Note that without `ensure_downloaded`, the path is not guaranteed to point to an
    existing file.

    Args:
        structure_name (str): Name of the structure.
        resolution (Resolution): Resolution of the mask.
        ensure_downloaded (bool, optional):
            Whether to download the mask before returning the path if the file is not
            already available.

    Returns:
        str: The path to the would-be file.
    """
    structure_id = get_structure_id(structure_name, resolution)
    mask_directory = MASK_ROOT_DIRECTORY / f"structure_masks_{resolution.value}"

    path = str(mask_directory / f"structure_{structure_id}.nrrd")
    if ensure_downloaded and not Path(path).exists():
        download_structure_mask(structure_name, resolution)

    return path


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
