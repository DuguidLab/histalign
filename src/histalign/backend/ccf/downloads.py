# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
import os
from pathlib import Path
import shutil
import ssl
from typing import Literal
import urllib.error
from urllib.request import urlopen

from histalign.backend.ccf import (
    ANNOTATION_ROOT_DIRECTORY,
    ATLAS_ROOT_DIRECTORY,
    BASE_ANNOTATION_URL,
    BASE_ATLAS_URL,
    BASE_MASK_URL,
    MASK_ROOT_DIRECTORY,
)
from histalign.backend.ccf.paths import get_structure_id
from histalign.backend.models import Resolution

_module_logger = logging.getLogger(__name__)


def download_atlas(
    resolution: Resolution,
    atlas_type: Literal["average_template", "ara_nissl"] = "average_template",
) -> None:
    atlas_file_name = f"{atlas_type}_{resolution.value}.nrrd"
    url = "/".join([BASE_ATLAS_URL, atlas_type, atlas_file_name])
    atlas_path = ATLAS_ROOT_DIRECTORY / atlas_file_name

    download(url, atlas_path)


def download_annotation_volume(resolution: Resolution) -> None:
    volume_file_name = f"annotation_{resolution}.nrrd"
    url = "/".join([BASE_ANNOTATION_URL, volume_file_name])
    volume_path = ANNOTATION_ROOT_DIRECTORY / volume_file_name

    download(url, volume_path)


def download_structure_mask(structure_name: str, resolution: Resolution) -> None:
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
    context = ssl.create_default_context()
    if not check_hostname:
        context.check_hostname = False
    if not check_certificate:
        context.verify_mode = ssl.CERT_NONE

    return context
