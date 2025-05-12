# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import json
from pathlib import Path

import numpy as np

from histalign.backend.ccf import get_atlas_path
from histalign.backend.registration import Registrator
from histalign.backend.workspace import Volume, VolumeSlicer
from histalign.io import load_alignment_settings, load_volume


def re_baseline(transformation: str, volume_path: Path, volume: Volume) -> None:
    current_settings = load_alignment_settings(
        f"tests/registration/resources/{transformation}_alignment_settings.json"
    )
    current_settings.volume_path = volume_path

    forwarded_image = registrator.get_forwarded_image(image, current_settings)
    volume_image = VolumeSlicer(volume=volume).slice(current_settings.volume_settings)

    forward_composite_image = np.where(
        forwarded_image > 10, forwarded_image * 3, volume_image
    )
    np.savez_compressed(
        f"tests/registration/resources/{transformation}_expected_output1.npz",
        array=forward_composite_image,
    )

    reversed_image = registrator.get_reversed_image(current_settings, "atlas", image)

    np.savez_compressed(
        f"tests/registration/resources/{transformation}_expected_output2.npz",
        array=np.where(reversed_image, reversed_image, image * 3),
    )

    with open(
        f"tests/registration/resources/{transformation}_alignment_settings.json",
        "w",
    ) as handle:
        dump = current_settings.model_dump()

        dump["volume_path"] = ""
        dump["histology_path"] = (
            "tests/registration/resources/"
            "A2_mcherry555_mecp488_dapi_image0000_channel2_maximum_uint8.npz"
        )

        json.dump(dump, handle)


try:
    alignment_settings = load_alignment_settings(
        "tests/registration/resources/complete_alignment_settings.json"
    )

    volume_path = get_atlas_path(
        alignment_settings.volume_settings.resolution, ensure_downloaded=True
    )
    alignment_settings.volume_path = volume_path

    image = np.load(
        "tests/registration/resources/"
        "A2_mcherry555_mecp488_dapi_image0000_channel2_maximum_uint8.npz"
    )
    image = image["array"]

    volume = load_volume(alignment_settings.volume_path)

    registrator = Registrator(True, True)

    for transformation in [
        "identity",
        "scale",
        "shear",
        "rotation",
        "translation",
        "offset",
        "pitch",
        "yaw",
        "complete",
    ]:
        re_baseline(transformation, volume_path, volume)
except FileNotFoundError:
    print("Please navigate to the project root folder before running this re-baseline.")
