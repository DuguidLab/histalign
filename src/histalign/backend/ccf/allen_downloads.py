# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierDelrée@protonmail.com>
#
# SPDX-License-Identifier: MIT

from pathlib import Path
import ssl
from typing import Literal, Optional
from urllib.request import urlopen

import allensdk
from PySide6 import QtCore


BASE_ATLAS_URL = (
    "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf"
)


def download_atlas(
    resolution: Literal[10, 25, 50, 100],
    atlas_type: Literal["average_volume", "ara_nissl"] = "average_volume",
    data_directory: Optional[str] = None,
) -> str:
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
