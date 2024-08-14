# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
import os
import shutil
import ssl
import urllib.error
from pathlib import Path
from typing import Any, Literal
from urllib.request import urlopen

from PySide6 import QtCore


ALLOWED_RESOLUTIONS = (10, 25, 50, 100)
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

ATLAS_ROOT_DIRECTORY = DATA_ROOT / "atlases"
os.makedirs(ATLAS_ROOT_DIRECTORY, exist_ok=True)
MASK_ROOT_DIRECTORY = DATA_ROOT / "structure_masks"
os.makedirs(MASK_ROOT_DIRECTORY, exist_ok=True)

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)
formatter = logging.Formatter(logging.BASIC_FORMAT)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)


def get_structures_hierarchy_path() -> str:
    path = DATA_ROOT / f"structures.json"

    # Easiest option to have the Allen SDK do the work for us
    if not path.exists():
        get_structure_tree(100)

    return str(path)


def get_structure_names_list(resolution: int = 10) -> list[str]:
    ensure_valid_resolution(resolution)

    return list(get_structure_tree(resolution).get_name_map().values())


def get_structure_tree(resolution: int) -> Any:
    # This takes a long time to import (~4 seconds on my machine) so only "lazily"
    # import it.
    from allensdk.core.reference_space_cache import ReferenceSpaceCache

    ensure_valid_resolution(resolution)

    return ReferenceSpaceCache(
        resolution=resolution,
        reference_space_key=os.path.join("annotation", "ccf_2017"),
        manifest=str(DATA_ROOT / f"manifest.json"),
    ).get_structure_tree()


def get_atlas_path(
    resolution: int,
    atlas_type: Literal["average_template", "ara_nissl"] = "average_template",
):
    ensure_valid_resolution(resolution)

    atlas_file_name = f"{atlas_type}_{resolution}.nrrd"
    atlas_path = ATLAS_ROOT_DIRECTORY / atlas_file_name

    if atlas_path.exists():
        return str(atlas_path)
    else:
        return download_atlas(resolution, atlas_type)


def download_atlas(
    resolution: int,
    atlas_type: Literal["average_template", "ara_nissl"] = "average_template",
) -> str:
    ensure_valid_resolution(resolution)

    atlas_file_name = f"{atlas_type}_{resolution}.nrrd"
    url = "/".join([BASE_ATLAS_URL, atlas_type, atlas_file_name])
    atlas_path = ATLAS_ROOT_DIRECTORY / atlas_file_name

    download(url, atlas_path)

    return str(atlas_path)


def get_structure_path(structure_name: str, resolution: int) -> str:
    ensure_valid_resolution(resolution)

    structure_id = get_structure_id(structure_name, resolution)

    mask_directory = MASK_ROOT_DIRECTORY / f"structure_masks_{resolution}"
    mask_file_path = mask_directory / f"structure_{structure_id}.nrrd"

    if mask_file_path.exists():
        return str(mask_file_path)
    else:
        return download_structure_mask(structure_id, resolution)


def get_structure_id(structure_name: str, resolution: int) -> int:
    ensure_valid_resolution(resolution)

    return get_structure_tree(resolution).get_structures_by_name([structure_name])[0][
        "id"
    ]


def download_structure_mask(structure_id: int, resolution) -> str:
    ensure_valid_resolution(resolution)

    structure_file_name = f"structure_{structure_id}.nrrd"
    url = "/".join(
        [BASE_MASK_URL, f"structure_masks_{resolution}", structure_file_name]
    )
    output_file_path = (
        MASK_ROOT_DIRECTORY / f"structure_masks_{resolution}" / structure_file_name
    )

    os.makedirs(output_file_path.parent, exist_ok=True)

    download(url, output_file_path)

    return str(output_file_path)


def download(url: str | Path, file_path: str | Path) -> None:
    # Allen SSL certificate is apparently not valid...
    context = get_ssl_context(check_hostname=False, check_certificate=False)
    try:
        with urlopen(url, context=context) as response, open(file_path, "wb") as handle:
            shutil.copyfileobj(response, handle)
    except urllib.error.HTTPError:
        logger.error(f"URL not found ('{url}').")


def get_ssl_context(
    check_hostname: bool = True, check_certificate: bool = True
) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not check_hostname:
        context.check_hostname = False
    if not check_certificate:
        context.verify_mode = ssl.CERT_NONE

    return context


def ensure_valid_resolution(resolution) -> None:
    if resolution not in ALLOWED_RESOLUTIONS:
        raise ValueError(
            f"Invalid resolution. Allowed: {ALLOWED_RESOLUTIONS}, got {resolution}."
        )
