# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import os
from pathlib import Path
import shutil
import ssl
from typing import Literal, Optional
from urllib.request import urlopen

import allensdk
from PySide6 import QtCore


ALLOWED_RESOLUTIONS = (10, 25, 50, 100)
BASE_ATLAS_URL = (
    "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf"
)

data_directories = QtCore.QStandardPaths.standardLocations(
    QtCore.QStandardPaths.GenericDataLocation
)
if not data_directories:
    raise ValueError("Cannot find a data directory.")
ATLAS_ROOT_DIRECTORY = Path(data_directories[0]) / "histalign" / "atlases"
os.makedirs(ATLAS_ROOT_DIRECTORY, exist_ok=True)


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

    # Allen SSL certificate is apparently not valid...
    context = get_ssl_context(check_hostname=False, check_certificate=False)

    with urlopen(url, context=context) as response, open(atlas_path, "wb") as handle:
        shutil.copyfileobj(response, handle)

    return str(atlas_path)


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
