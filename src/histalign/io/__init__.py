# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

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

from histalign.backend.maths import normalise_array
from histalign.backend.models import AlignmentSettings

data_directories = QtCore.QStandardPaths.standardLocations(
    QtCore.QStandardPaths.GenericDataLocation
)
if not data_directories:
    raise ValueError("Cannot find a data directory.")
DATA_ROOT = Path(data_directories[0]) / "histalign"
del data_directories

ALIGNMENT_FILE_NAME_PATTERN = re.compile(r"[0-9a-f]{32}\.json")

_SUPPORTED_ARRAY_FORMATS = [
    ".h5",
    ".hdf5",
    ".jpg",
    ".jpeg",
    "png",
    ".npy",
    "npz",
    ".nrrd",
]

_module_logger = logging.getLogger(__name__)


def load_image(
    path: str | Path,
    normalise_dtype: Optional[np.dtype] = None,
    allow_stack: bool = False,
    allow_h5py_dataset: bool = False,
) -> np.ndarray:
    """Loads a 2D image or 3D stack from disk.

    Args:
        path (str | Path): Path to the file.
        normalise_dtype (Optional[np.dtype], optional):
            Data type to normalise to. Leave as `None` to disable normalisation.
        allow_stack (bool): Whether to allow 3D image stacks.
        allow_h5py_dataset (bool):
            Whether to allow returning an h5py.Dataset instead of a regular array.

    Returns:
        np.ndarray: The loaded file as a NumPy array.
    """
    array = load_array(path, normalise_dtype, allow_h5py_dataset)

    dimension_count = len(array.shape)
    if dimension_count == 3 and not allow_stack:
        raise ValueError(
            f"Provided array is 3-dimensional but only 2D images are allowed."
        )
    elif dimension_count != 2:
        raise ValueError(
            f"Provided array is {dimension_count}-dimensional but only 2D images "
            f"and 3D stacks are supported."
        )

    return array


def load_volume(
    path: str | Path,
    normalise_dtype: Optional[np.dtype] = None,
    as_array: bool = False,
    allow_h5py_dataset: bool = False,
) -> np.ndarray | vedo.Volume:
    """Loads a 3D volume from disk.

    Args:
        path (str | Path): Path to the file.
        normalise_dtype (Optional[np.dtype], optional):
            Data type to normalise to. Leave as `None` to disable normalisation.
        as_array (bool):
            Whether to return a NumPy array instead of a vedo.Volume.
        allow_h5py_dataset (bool):
            Whether to allow returning an h5py.Dataset instead of a regular array.

    Returns:
        np.ndarray | vedo.Volume: NumPy array or vedo.Volume object with the file data.
    """
    array = load_array(path, normalise_dtype, allow_h5py_dataset)

    dimension_count = len(array.shape)
    if dimension_count != 3:
        raise ValueError(
            f"Provided array is {dimension_count}-dimensional but a 3D volume was "
            f"expected."
        )

    return array if as_array else vedo.Volume(array)


# noinspection PyUnboundLocalVariable
def load_array(
    path: str | Path,
    normalise_dtype: Optional[np.dtype] = None,
    allow_h5py_dataset: bool = False,
) -> np.ndarray:
    """Loads an array from disk.

    Args:
        path (str | Path): Path to the array to load.
        normalise_dtype (Optional[np.dtype], optional):
            Optional dtype to use to normalise the array.
        allow_h5py_dataset (bool, optional):
            Whether to allow the returned object to be an h5py.Dataset. For most
            operations, they are equivalent to NumPy array but they are are not quite
            interchangeable.

    Returns:

    """
    path = Path(path)

    match path.suffix:
        case ".h5" | ".hdf5":
            handle = h5py.File(path)

            dataset_name = list(handle.keys())
            if len(dataset_name) < 1:
                raise ValueError(f"Could not find a dataset in HDF5 file '{path}'.")
            elif len(dataset_name) > 1:
                raise ValueError(f"Found more than one dataset in HDF5 file '{path}'.")

            array = handle[dataset_name[0]]
            if not allow_h5py_dataset:
                array = array[:]
                handle.close()
        case ".jpg" | ".jpeg" | ".png":
            array = np.array(Image.open(path))
        case ".npy":
            array = np.load(path)
        case ".npz":
            with np.load(path) as handle:
                keys = list(handle.keys())
                if len(keys) < 1:
                    raise ValueError(f"Could not find an array in NPZ file '{path}'.")
                elif len(keys) > 1:
                    raise ValueError(f"Found more than one array in NPZ file '{path}'.")

                array = handle[keys[0]]
        case ".nrrd":
            array = nrrd.read(str(path))[0]
        case other:
            if other in _SUPPORTED_ARRAY_FORMATS:
                raise NotImplementedError(f"Format not yet implemented.")

            raise ValueError(f"Unsupported array file extension '{other}'.")

    if normalise_dtype is not None:
        array = normalise_array(array, normalise_dtype)

    return array


def load_alignment_settings(path: str | Path) -> AlignmentSettings:
    """Loads alignment settings from an alignment path.

    Args:
        path (str | Path): Path to the alignment settings file.

    Returns:
        AlignmentSettings: A model with fields initialised to the parsed values.
    """
    with open(path) as handle:
        return AlignmentSettings(**json.load(handle))


def is_alignment_file(path: str | Path) -> bool:
    """Returns whether the given path points to an alignment settings file.

    Args:
        path (str | Path): Path to the file to check.

    Returns:
        bool: Whether the file path points to an alignment settings file.
    """

    path = Path(path)

    # Add extra check to make sure this is a not a hidden file (doesn't start with a
    # period)
    return (
        path.is_file()
        and re.fullmatch(ALIGNMENT_FILE_NAME_PATTERN, path.name) is not None
        and not path.name.startswith(".")
    )


def gather_alignment_paths(alignment_directory: str | Path) -> list[Path]:
    """Gathers alignment settings paths.

    Alignment settings paths are the files where registration settings are stored.

    Args:
        alignment_directory (str | Path): Directory to iterate to find alignment paths.

    Returns:
        list[Path]: The gathered alignment paths.
    """
    alignment_directory = Path(alignment_directory)

    paths = []
    for file in alignment_directory.iterdir():
        if not is_alignment_file(file):
            continue

        paths.append(file)

    return paths


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
