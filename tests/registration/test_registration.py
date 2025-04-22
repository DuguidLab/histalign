# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

# Fix a typing bug when using `vedo` with python==3.10.12
from typing import TypeVar

import typing_extensions

Self = TypeVar("Self")
typing_extensions.Self = Self

from pathlib import Path

import numpy as np
import pytest

from histalign.backend.ccf import get_atlas_path
from histalign.io import load_alignment_settings, load_image, load_volume
from histalign.backend.registration import Registrator
from histalign.backend.workspace import VolumeSlicer


@pytest.mark.parametrize(
    "parameter",
    [
        # Histology settings only
        "scale",
        "shear",
        "rotation",
        "translation",
        # Atlas settings only
        "offset",
        "pitch",
        "yaw",
        # All settings
        "complete",
    ],
)
def test_registration(parameter: str) -> None:
    """Tests registration produces the expected images.

    See `registration-visual-test.ipynb` for details if this fails.
    """
    alignment_path = Path(
        f"tests/registration/resources/{parameter}_alignment_settings.json"
    )
    forward_expected_path = Path(
        f"tests/registration/resources/{parameter}_expected_output1.npz"
    )
    reverse_expected_path = Path(
        f"tests/registration/resources/{parameter}_expected_output2.npz"
    )

    alignment_settings = load_alignment_settings(alignment_path)

    image = load_image(alignment_settings.histology_path)

    if (
        not alignment_settings.volume_path.is_file()
        or not alignment_settings.volume_path.suffixes[-1] == ".nrrd"
    ):
        atlas_path = get_atlas_path(
            alignment_settings.volume_settings.resolution, ensure_downloaded=True
        )

        alignment_settings.volume_path = atlas_path

    atlas = load_volume(alignment_settings.volume_path)
    atlas_image = VolumeSlicer(volume=atlas).slice(alignment_settings.volume_settings)

    registrator = Registrator(True, True)

    forwarded_image = registrator.get_forwarded_image(image, alignment_settings)
    expected_forwarded_image = load_image(forward_expected_path)
    actual_forwarded_image = np.where(
        forwarded_image > 10, forwarded_image * 3, atlas_image
    )

    assert np.all(np.equal(expected_forwarded_image, actual_forwarded_image))

    reversed_image = registrator.get_reversed_image(alignment_settings, "atlas", image)
    expected_reversed_image = load_image(reverse_expected_path)
    actual_reversed_image = np.where(reversed_image, reversed_image, image * 3)

    assert np.all(np.equal(expected_reversed_image, actual_reversed_image))
