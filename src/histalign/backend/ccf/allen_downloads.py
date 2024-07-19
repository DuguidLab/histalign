# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierDelrée@protonmail.com>
#
# SPDX-License-Identifier: MIT

from pathlib import Path
import ssl
from typing import Literal, Optional
from urllib.request import urlopen

import allensdk
from PySide6 import QtCore


ALLOWED_RESOLUTIONS = (10, 25, 50, 100)
BASE_ATLAS_URL = (
    "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf"
)


def get_atlas_path(
    resolution: int,
    atlas_type: Literal["average_template", "ara_nissl"] = "average_template",
    data_directory: Optional[str] = None,
):
    if resolution not in ALLOWED_RESOLUTIONS:
        raise ValueError(
            f"Invalid resolution. Allowed: {ALLOWED_RESOLUTIONS}, got {resolution}."
        )

    if not data_directory:
        data_directory = QtCore.QStandardPaths.standardLocations(
            QtCore.QStandardPaths.StandardLocation.GenericDataLocation
        )
        if not data_directory:
            raise ValueError("Cannot find a data directory.")

        data_directory = data_directory[0]

    atlas_file_name = f"{atlas_type}_{resolution}.nrrd"
    atlas_path = str(Path(data_directory) / atlas_file_name)

    if Path(atlas_path).exists():
        return atlas_path
    else:
        return download_atlas(resolution, atlas_type, data_directory)


def download_atlas(
    resolution: int,
    atlas_type: Literal["average_template", "ara_nissl"] = "average_template",
    data_directory: Optional[str] = None,
) -> str:
    if resolution not in ALLOWED_RESOLUTIONS:
        raise ValueError(
            f"Invalid resolution. Allowed: {ALLOWED_RESOLUTIONS}, got {resolution}."
        )

    if not data_directory:
        data_directory = QtCore.QStandardPaths.standardLocations(
            QtCore.QStandardPaths.StandardLocation.GenericDataLocation
        )
        if not data_directory:
            raise ValueError("Cannot find a data directory to download to.")

        data_directory = data_directory[0]

    atlas_file_name = f"{atlas_type}_{resolution}.nrrd"
    url = "/".join([BASE_ATLAS_URL, atlas_type, atlas_file_name])
    atlas_path = str(Path(data_directory) / atlas_file_name)

    # Allen SSL certificate is apparently not valid...
    context = get_ssl_context(check_hostname=False, check_certificate=False)

    with open(atlas_path, "wb") as handle:
        handle.write(urlopen(url, context=context).read())

    return atlas_path


def get_ssl_context(
    check_hostname: bool = True, check_certificate: bool = True
) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not check_hostname:
        context.check_hostname = False
    if not check_certificate:
        context.verify_mode = ssl.CERT_NONE

    return context
