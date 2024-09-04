# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Optional

import h5py
import nrrd
import numpy as np
from PIL import Image
import vedo


def load_image(
    file_path: str | Path, normalise_dtype: Optional[np.dtype] = None
) -> np.ndarray:
    if isinstance(file_path, Path):
        file_path = str(file_path)

    match file_path.split(".")[-1]:
        case "h5" | "hdf5":
            with h5py.File(file_path, "r") as h5_handle:
                dataset_name = list(h5_handle.keys())

                if len(dataset_name) != 1:
                    raise ValueError(
                        f"Unexpected number of datasets found. "
                        f"Expected 1, found {len(dataset_name)}. "
                        f"Make sure the file only contains a single image."
                    )

                array = h5_handle[dataset_name[0]][:]

                if len(array.shape) != 2:
                    raise ValueError(
                        f"Unexpected number of dataset dimensions. "
                        f"Expected 2, found {len(array.shape)}. "
                        f"Make sure the image has been project to only contain "
                        f"XY data."
                    )
        case "npy":
            array = np.load(file_path)
        case "jpg" | "jpeg" | "png":
            array = np.array(Image.open(file_path))
        case other:
            raise ValueError(f"Unknown file extension '{other}'.")

    if normalise_dtype is not None:
        array = normalise_array(array, normalise_dtype)

    return array


def load_volume(
    file_path: str | Path,
    normalise_dtype: Optional[np.dtype] = None,
    return_raw_array: bool = False,
) -> np.ndarray | vedo.Volume:
    if isinstance(file_path, Path):
        file_path = str(file_path)

    match file_path.split(".")[-1]:
        case "nrrd":
            array = nrrd.read(file_path)[0]
        case "npy":
            array = np.load(file_path)
        case other:
            raise ValueError(f"Unknown volume file extension '{other}'.")

    if normalise_dtype is not None:
        array = normalise_array(array, normalise_dtype)

    return array if return_raw_array else vedo.Volume(array)


def normalise_array(array: np.ndarray, dtype: np.dtype) -> np.ndarray:
    array = array.astype(float)
    array -= array.min()
    array *= np.iinfo(dtype).max / array.max()
    return np.round(array).astype(dtype)
