# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Thread
from typing import Iterator, Optional

import numpy as np
from PySide6 import QtCore, QtWidgets

from histalign.application.HistologySlice import HistologySlice


class Workspace(QtWidgets.QWidget):
    """Representation of the current logical workspace.

    This class manages the current working directory and keeps track of the images that
    have been added to it. Each directory should be a single brain and will be presented
    to the user on the GUI as a series of thumbnails.

    Attributes:
        current_working_directory (str): The current working directory. This is where
                                         the cache and other project directories are
                                         created.
    """

    current_working_directory: str

    generated_thumbnail: QtCore.Signal = QtCore.Signal(int, np.ndarray)

    def __init__(
        self,
        working_directory: Optional[str] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """Creates a new workspace instance.

        Args:
            working_directory (str, optional): The working directory to use for this
                                               this workspace.
        """
        super().__init__(parent)

        self.current_working_directory = working_directory or os.getcwd()

        self._histology_slices: list[HistologySlice] = []
        self._thumbnail_thread: Optional[Thread] = None

    def parse_image_directory(
        self, directory_path: str, generate_thumbnails: bool = True
    ) -> None:
        """Iterates the provided directory for histology images.

        Note that no persistent loading of images into memory is done at this point.
        Instead, each file gets a `HistologySlice` wrapper representation added to the
        current workspace.

        Although the images are not persistently loaded into memory yet, if
        `generate_thumbnails` is set (the default), they are each loaded once in order
        for a thumbnail to be generated for them. To avoid unnecessarily clogging
        memory, the images are not kept in memory after the thumbnail has been
        generated.

        Args:
            directory_path (str): Path to iterate.
            generate_thumbnails (bool, optional): Whether to generate and thumbnails for
                                                  the parsed images.
        """
        self._histology_slices = [
            HistologySlice(str(path)) for path in Path(directory_path).iterdir()
        ]

        if generate_thumbnails:
            self._thumbnail_thread = Thread(target=self._generate_thumbnails)
            self._thumbnail_thread.start()

    def get_slice(self, index: int) -> Optional[HistologySlice]:
        """Returns the `HistologySlice` at `index` or `None`.

        Note that this method returns `None` when the index is out of range.

        This method should not usually be called unless you need to retrieve some
        information about the slice itself. Instead use `get_image` or `get_thumbnail`
        if you only want to display the slice.

        Args:
            index (int): Index of the slice to return.

        Returns:
            Optional[HistologySlice]: The `HistologySlice` wrapper at `index` or `None`
                                      if the index is out of range.
        """
        if index >= len(self._histology_slices):
            return None
        return self._histology_slices[index]

    def get_image(self, index: int) -> Optional[np.ndarray]:
        """Returns the image at `index` or `None`.

        Note that this method returns `None` when the index is out of range, not when
        the image has not been loaded yet. If the image was not loaded before the call
        to this method, it is loaded and then returned.

        Args:
            index (int): Index of the image to return.

        Returns:
            Optional[np.ndarray]: The underlying image array of the `HistologySlice` at
                                  `index` or `None` if the index is out of range.
        """
        if index >= len(self._histology_slices):
            return None

        while True:
            if self._histology_slices[index].image_array is None:
                self._histology_slices[index].load_image(self.current_working_directory)
            return self._histology_slices[index].image_array

    def iterate_images(self) -> Iterator[np.ndarray]:
        """Returns an iterator over the parsed images.

        Note that this is a potentially expansive operation as it will need to load each
        image into memory if they are not already.

        Returns:
            Iterator[np.ndarray]: An iterator over the parsed images.
        """
        for i in range(len(self._histology_slices)):
            yield self.get_image(i)

    def get_thumbnail(self, index: int, timeout: int = 30) -> Optional[np.ndarray]:
        """Returns the thumbnail at `index` or `None`.

        Note that this method returns `None` when the index is out of range, not when
        the thumbnail has not been generated yet. If the thumbnail was not generated
        before the call to this method, it is generated and then returned.
        Similarly to `parse_image_directory`, if the thumbnail's image is not already
        in memory, it will only be temporarily loaded and then dropped once the
        thumbnail has been generated.

        Args:
            index (int): Index of the thumbnail to return.
            timeout (int, optional): How long (in seconds) to wait for the background
                                     thread started in `parse_image_directory` to
                                     generate the thumbnail. Set to 0 to disable the
                                     timeout.

        Returns:
            Optional[np.ndarray]: The underlying thumbnail array of the `HistologySlice`
                                  at `index` or `None` if the index is out of range.
        """
        if index >= len(self._histology_slices):
            return None

        while True:
            if self._histology_slices[index].thumbnail_array is not None:
                break

            if not self._thumbnail_thread.is_alive():
                self._histology_slices[index].generate_thumbnail(
                    self.current_working_directory
                )
                break

            timeout -= 1
            if timeout == 0:
                logging.error(f"Timed out trying to retrieve thumbnail for {index=}.")
                return None
            time.sleep(1)

        return self._histology_slices[index].thumbnail_array

    def iterate_thumbnails(self) -> Iterator[np.ndarray]:
        """Returns an iterator over the parsed images' thumbnails.

        Note that this is a potentially expansive operation as it will need to load
        images into memory if they do not have a thumbnail yet.

        Returns:
            Iterator[np.ndarray]: An iterator over the parsed images.
        """
        for i in range(len(self._histology_slices)):
            yield self.get_thumbnail(i)

    def swap_slices(self, index1: int, index2: int) -> None:
        """Swaps two slices by index.

        Args:
            index1 (int): Index of the first slice.
            index2 (int): Index of the second slice.
        """
        self._histology_slices[index1], self._histology_slices[index2] = (
            self._histology_slices[index2],
            self._histology_slices[index1],
        )

    def _generate_thumbnails(self) -> None:
        with ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(self._generate_thumbnail, range(len(self._histology_slices)))

    def _generate_thumbnail(self, index: int) -> None:
        self._histology_slices[index].generate_thumbnail(self.current_working_directory)
        # Using .copy() is a workaround to avoid having the thumbnail be deleted
        # before it can be used by the connected slot (e.g., when loading a different
        # image directory while thumbnails for the previous one are still being
        # processed). Thumbnails are meant to be small but this should probably still
        # be fixed.
        # TODO: Avoid .copy()
        self.generated_thumbnail.emit(
            index, self._histology_slices[index].thumbnail_array.copy()
        )
