# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

"""This sub-package handles most interactions with the file system and most commands."""

import json
import logging
import os
from pathlib import Path
import re
import shutil
from typing import Literal, Optional

import nrrd
import numpy as np
from PySide6 import QtCore
import vedo

from histalign.backend.maths import normalise_array
from histalign.backend.models import AlignmentSettings
from histalign.io.image import (
    DimensionOrder,
    get_appropriate_plugin_class,
    ImageFile,
    MultiSeriesImageFile,
    UnknownFileFormatError,
)

data_directories = QtCore.QStandardPaths.standardLocations(
    QtCore.QStandardPaths.GenericDataLocation
)
if not data_directories:
    raise ValueError("Cannot find a data directory.")
DATA_ROOT = Path(data_directories[0]) / "histalign"
del data_directories

ALIGNMENT_FILE_NAME_PATTERN = re.compile(r"[0-9a-f]{32}\.json")
HASHED_DIRECTORY_NAME_PATTERN = re.compile(r"[0-9a-f]{10}")

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
    force_yx: bool = True,
) -> np.ndarray:
    """Loads a 2D image or 3D stack from disk.

    Args:
        path (str | Path): Path to the file.
        normalise_dtype (Optional[np.dtype], optional):
            Data type to normalise to. Leave as `None` to disable normalisation. Note
            that normalisation happens on the whole array (for example, Z-stacks are
            normalised using min/max of the whole array).
        allow_stack (bool, optional): Whether to allow 3D image stacks.
        force_yx (bool, optional): Whether to transpose XY dimension order to YX.

    Returns:
        np.ndarray: The loaded file as a NumPy array.
    """
    file = open_file(path)

    if isinstance(file, MultiSeriesImageFile):
        if file.series_count < 1:
            file.close()
            raise ValueError(f"File does not have any data.")
        elif file.series_count > 1:
            file.close()
            raise ValueError(f"File has more than one series.")

    if "C" in file.dimension_order.value:
        file.close()
        raise ValueError(f"Multi-channel files are not allowed.")
    elif "Z" in file.dimension_order.value and not allow_stack:
        raise ValueError(
            f"Provided file data has a Z axis but only 2D images are allowed."
        )

    array = file.load()
    if normalise_dtype is not None:
        array = normalise_array(array, normalise_dtype)

    if force_yx:
        order = file.dimension_order

        x_index = order.value.index("X")
        y_index = order.value.index("Y")
        if x_index < y_index:
            array = array.swapaxes(x_index, y_index)

    return array


def load_volume(
    path: str | Path,
    normalise_dtype: Optional[np.dtype] = None,
    as_array: bool = False,
) -> np.ndarray | vedo.Volume:
    """Loads a 3D volume from disk.

    Args:
        path (str | Path): Path to the file.
        normalise_dtype (Optional[np.dtype], optional):
            Data type to normalise to. Leave as `None` to disable normalisation. Note
            that normalisation happens on the whole array (for example, Z-stacks are
            normalised using min/max of the whole array).
        as_array (bool):
            Whether to return a NumPy array instead of a vedo.Volume.

    Returns:
        np.ndarray | vedo.Volume: NumPy array or vedo.Volume object with the file data.
    """
    # TODO: Write NRRD plugin
    try:
        file = open_file(path, dimension_order=DimensionOrder.XYZ)

        if isinstance(file, MultiSeriesImageFile):
            if file.series_count < 1:
                file.close()
                raise ValueError(f"File does not have any data.")
            elif file.series_count > 1:
                file.close()
                raise ValueError(f"File has more than one series.")

        if "C" in file.dimension_order.value:
            file.close()
            raise ValueError(f"Multi-channel files are not allowed.")
        elif "Z" not in file.dimension_order.value:
            raise ValueError(
                f"Provided file data is only two-dimensional. Expected a volume."
            )

        array = file.load()
    except UnknownFileFormatError:
        suffix = Path(path).suffix
        if suffix == ".nrrd":
            array = nrrd.read(path)[0]
        else:
            # Continue raising
            raise

    if normalise_dtype is not None:
        array = normalise_array(array, normalise_dtype)

    return array if as_array else vedo.Volume(array)


# noinspection PyUnboundLocalVariable
def open_file(
    path: str | Path,
    mode: Literal["r", "w"] = "r",
    dimension_order: Optional[DimensionOrder] = None,
) -> ImageFile:
    """Opens a file from disk.

    Args:
        path (str | Path): Path to the file on disk.
        mode (Literal["r", "w"], optional): Mode to open the file with.
        dimension_order (Optional[str | DimensionOrder], optional):
            Order of the dimensions in the file. Leave as `None` to attempt guessing
            based on dimension sizes.

    Returns:
        ImageFile: A handle to the opened file.
    """
    path = Path(path)

    plugin_class = get_appropriate_plugin_class(path, mode)
    return plugin_class(path, mode, dimension_order)


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


def is_empty_directory(path: Path) -> bool:
    """Returns whether a given path points to an empty directory.

    If the path is not valid or not a directory, this function returns False.

    Args:
        path (Path): Path to the directory.

    Returns:
        bool: Whether the path points to a valid, empty directory.
    """
    if not path.exists() or not path.is_dir():
        return False

    try:
        next(path.iterdir())
        return False
    except StopIteration:
        return True


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


def list_alignment_directories(
    project_root: Path, allow_empty: bool = False
) -> list[str]:
    directories = []
    for path in project_root.iterdir():
        path: Path
        if (
            path.is_file()
            or re.fullmatch(HASHED_DIRECTORY_NAME_PATTERN, path.name) is None
        ):
            continue

        metadata_path = path / "metadata.json"
        if not metadata_path.exists():
            continue

        for child_path in path.iterdir():
            if is_alignment_file(child_path):
                break
        else:
            if not allow_empty:
                continue

        with metadata_path.open() as handle:
            directories.append(json.load(handle)["directory_path"])

    return directories
