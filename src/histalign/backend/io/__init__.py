# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

"""This module provides an API for loading 2D and 3D files and inspecting directories."""

import json
import logging
import os
from pathlib import Path
import re
import shutil
from typing import Optional

import h5py
import nrrd
import numpy as np
from PIL import Image
from PySide6 import QtCore
import vedo

from histalign.backend.models import AlignmentSettings
from histalign.backend.preprocessing import normalise_array

data_directories = QtCore.QStandardPaths.standardLocations(
    QtCore.QStandardPaths.GenericDataLocation
)
if not data_directories:
    raise ValueError("Cannot find a data directory.")
DATA_ROOT = Path(data_directories[0]) / "histalign"
del data_directories

ALIGNMENT_FILE_NAME_PATTERN = re.compile(r"[0-9a-f]{32}\.json")

_module_logger = logging.getLogger(__name__)


def load_image(
    file_path: str | Path,
    normalise_dtype: Optional[np.dtype] = None,
    allow_stack: bool = False,
    allow_dataset: bool = False,
) -> np.ndarray:
    """Loads a 2D image or 3D stack from disk.

    Args:
        file_path (str | Path): Path to the file.
        normalise_dtype (Optional[np.dtype], optional):
            Data type to normalise to. Leave as `None` to disable normalisation.
        allow_stack (bool): Whether to allow 3D image stacks.
        allow_dataset (bool):
            Whether to allow returning an h5py.Dataset instead of a regular array.

    Returns:
        np.ndarray: The loaded file as a NumPy array.
    """
    if isinstance(file_path, Path):
        file_path = str(file_path)

    match file_path.split(".")[-1]:
        case "h5" | "hdf5":
            h5_handle = h5py.File(file_path, "r")
            dataset_name = list(h5_handle.keys())

            if len(dataset_name) != 1:
                raise ValueError(
                    f"Unexpected number of datasets found. "
                    f"Expected 1, found {len(dataset_name)}. "
                    f"Make sure the file only contains a single image."
                )

            array = h5_handle[dataset_name[0]]

            if len(array.shape) != 2:
                if not (allow_stack and len(array.shape) == 3):
                    raise ValueError(
                        f"Unexpected number of dataset dimensions. "
                        f"Expected 2, found {len(array.shape)}. "
                        f"Make sure the image has been project to only contain "
                        f"XY data."
                    )

            # Datasets can behave as arrays most but not all of the time
            if not allow_dataset:
                array = array[:]
                h5_handle.close()
        case "npy":
            array = np.load(file_path)
        case "npz":
            try:
                array = np.load(file_path)["array"]
            except KeyError:
                raise ValueError(
                    "Expected .npz file to have a key 'array' for the volume."
                )
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
    allow_dataset: bool = False,
) -> np.ndarray | vedo.Volume:
    """Loads a 3D volume from disk.

    Args:
        file_path (str | Path): Path to the file.
        normalise_dtype (Optional[np.dtype], optional):
            Data type to normalise to. Leave as `None` to disable normalisation.
        return_raw_array (bool):
            Whether to return a NumPy array instead of a vedo.Volume.
        allow_dataset (bool):
            Whether to allow returning an h5py.Dataset instead of a regular array.

    Returns:
        np.ndarray | vedo.Volume: NumPy array or vedo.Volume object with the file data.
    """
    if isinstance(file_path, Path):
        file_path = str(file_path)

    match file_path.split(".")[-1]:
        case "h5" | "hdf5":
            handle = h5py.File(file_path, "r")
            dataset_name = list(handle.keys())

            if len(dataset_name) != 1:
                raise ValueError(
                    f"Unexpected number of datasets found. "
                    f"Expected 1, found {len(dataset_name)}. "
                    f"Make sure the file only contains a single volume."
                )

            array = handle[dataset_name[0]]

            if len(array.shape) != 3:
                raise ValueError(
                    f"Unexpected number of dataset dimensions. "
                    f"Expected 3, found {len(array.shape)}. "
                    f"Make sure the volume contains XYZ data."
                )

            # Datasets can behave as arrays most but not all of the time
            if not allow_dataset:
                array = array[:]
                handle.close()
        case "nrrd":
            array = nrrd.read(file_path)[0]
        case "npy":
            array = np.load(file_path)
        case "npz":
            try:
                array = np.load(file_path)["array"]
            except KeyError:
                raise ValueError(
                    "Expected .npz file to have a key 'array' for the volume."
                )
        case other:
            raise ValueError(f"Unknown volume file extension '{other}'.")

    if normalise_dtype is not None:
        array = normalise_array(array, normalise_dtype)

    return array if return_raw_array else vedo.Volume(array)


def gather_alignment_paths(alignment_directory: str | Path) -> list[Path]:
    """Gathers alignment settings paths.

    Alignment settings paths are the files where registration settings are stored.

    Args:
        alignment_directory (str | Path): Directory to iterate to find alignment paths.

    Returns:
        list[Path]: The gathered alignment paths.
    """
    if isinstance(alignment_directory, str):
        alignment_directory = Path(alignment_directory)

    paths = []

    for file in alignment_directory.iterdir():
        if re.fullmatch(ALIGNMENT_FILE_NAME_PATTERN, file.name) is None:
            continue

        paths.append(file)

    return paths


def load_alignment_settings(path: str | Path) -> AlignmentSettings:
    """Loads alignment settings from an alignment path.

    Args:
        path (str | Path): Path to the alignment settings file.

    Returns:
        AlignmentSettings: A model with fields initialised to the parsed values.
    """
    with open(path) as handle:
        return AlignmentSettings(**json.load(handle))


def clear_directory(directory_path: str | Path) -> None:
    """Removes all files and directories from the given path.

    Note that the given path itself is not removed.

    Args:
        directory_path (str | Path): Path to the directory to clear.
    """
    _module_logger.debug(f"Clearing directory at: {directory_path}")

    if isinstance(directory_path, str):
        directory_path = Path(directory_path)

    for path in directory_path.iterdir():
        if path.is_file():
            os.remove(path)
        else:
            shutil.rmtree(path)
