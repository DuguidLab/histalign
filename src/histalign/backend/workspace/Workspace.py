# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
import os
from pathlib import Path
from threading import Event, Thread
import time
from typing import Any, Optional

import numpy as np
import pydantic
from PySide6 import QtCore

from histalign.backend.ccf.allen_downloads import get_atlas_path
from histalign.backend.models import (
    AlignmentParameterAggregator,
    HistologySettings,
    ProjectSettings,
    VolumeSettings,
)
from histalign.backend.workspace.HistologySlice import HistologySlice


class Workspace(QtCore.QObject):
    project_directory_path: str
    current_working_directory: str
    atlas_resolution: int
    last_parsed_directory: Optional[str] = None

    current_aligner_image_hash: Optional[str] = None
    current_aligner_image_index: Optional[int] = None
    alignment_parameters: AlignmentParameterAggregator = AlignmentParameterAggregator()

    thumbnail_generated: QtCore.Signal = QtCore.Signal(int, np.ndarray)

    def __init__(
        self, project_settings: ProjectSettings, parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)

        self.project_directory_path = str(project_settings.project_directory_path)
        self.current_working_directory = self.project_directory_path

        self.update_atlas_resolution(project_settings.atlas_resolution)

        self._histology_slices: list[HistologySlice] = []
        self._thumbnail_thread: Optional[Thread] = None
        self._stop_event = Event()

    def get_image(self, index: int) -> Optional[np.ndarray]:
        if index >= len(self._histology_slices):
            return None

        histology_slice = self._histology_slices[index]
        if histology_slice.image_array is None:
            self._histology_slices[index].load_image(self.current_working_directory)
        self.current_aligner_image_hash = histology_slice.hash
        self.current_aligner_image_index = index

        self.aggregate_settings(
            {
                "histology_file_path": histology_slice.file_path,
                "downsampling_factor": histology_slice.image_downsampling_factor,
            }
        )

        return histology_slice.image_array

    def get_thumbnail(self, index: int, timeout: int = 10) -> Optional[np.ndarray]:
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
                self.logger.error(
                    f"Timed out trying to retrieve thumbnail at index {index}."
                )
                return None
            time.sleep(1)

        return self._histology_slices[index].thumbnail_array

    def swap_slices(self, index1: int, index2: int) -> None:
        self._histology_slices[index1], self._histology_slices[index2] = (
            self._histology_slices[index2],
            self._histology_slices[index1],
        )
        self.save_order()

    def update_atlas_resolution(self, resolution: int) -> None:
        ProjectSettings.validate_resolution(resolution)
        self.atlas_resolution = resolution

    def save(self) -> None:
        with open(f"{self.project_directory_path}{os.sep}project.json", "w") as handle:
            settings = {
                "project_directory_path": self.project_directory_path,
                "current_working_directory": self.current_working_directory,
                "atlas_resolution": self.atlas_resolution,
                "last_parsed_directory": self.last_parsed_directory,
                "current_aligner_image_hash": self.current_aligner_image_hash,
                "current_aligner_image_index": self.current_aligner_image_index,
            }
            json.dump(settings, handle)

    def save_order(self, file_path: Optional[str] = None) -> None:
        if file_path is None:
            file_path = f"{self.current_working_directory}{os.sep}metadata.json"

        with open(file_path, "w") as handle:
            json.dump(self._serialise_slices(), handle)

    @staticmethod
    def load(file_path) -> "Workspace":
        if file_path.split(os.sep)[-1] != "project.json":
            raise ValueError("Invalid project file.")

        with open(file_path) as handle:
            contents = json.load(handle)

        settings = ProjectSettings(**contents)
        workspace = Workspace(settings)

        workspace.current_working_directory = contents["current_working_directory"]
        workspace.last_parsed_directory = contents["last_parsed_directory"]
        workspace.current_aligner_image_hash = contents["current_aligner_image_hash"]
        workspace.current_aligner_image_index = contents["current_aligner_image_index"]

        return workspace

    def parse_image_directory(self, directory_path: str) -> None:
        current_directory_hash = self.generate_directory_hash(directory_path)
        self.current_working_directory = (
            f"{self.project_directory_path}{os.sep}{current_directory_hash}"
        )
        os.makedirs(self.current_working_directory, exist_ok=True)

        # TODO: Filter paths to only valid images extensions
        metadata_file = f"{self.current_working_directory}{os.sep}metadata.json"
        if directory_path == self.last_parsed_directory:
            try:
                with open(metadata_file) as handle:
                    contents = json.load(handle)
            except FileNotFoundError:
                self.logger.error(f"Could not find metadata file at '{metadata_file}'.")
                self.last_parsed_directory = None
                return self.parse_image_directory(directory_path)

            contents_histology_slices = (
                self._histology_slices or self._deserialise_slices(contents)
            )

            temp_histology_slices = [
                HistologySlice(str(path)) for path in Path(directory_path).iterdir()
            ]

            # Remove slices if they were removed from the directory
            i = 0
            while i < len(contents_histology_slices):
                if contents_histology_slices[i] not in temp_histology_slices:
                    contents_histology_slices.pop(i)
                else:
                    temp_histology_slices.remove(contents_histology_slices[i])
                    i += 1

            # Add remaining slices to the end in arbitrary order
            self._histology_slices = contents_histology_slices + temp_histology_slices
        else:
            self._histology_slices = [
                HistologySlice(str(path)) for path in Path(directory_path).iterdir()
            ]
            self.last_parsed_directory = directory_path

        self.save_order(metadata_file)

        self._thumbnail_thread = Thread(target=self._generate_thumbnails)
        self._thumbnail_thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    @QtCore.Slot()
    def save_alignment(self) -> None:
        if self.current_aligner_image_hash is None:
            return

        self.aggregate_settings(
            {
                "volume_file_path": get_atlas_path(self.atlas_resolution),
                "resolution": self.atlas_resolution,
            }
        )

        with open(
            f"{self.current_working_directory}{os.sep}{self.current_aligner_image_hash}.json",
            "w",
        ) as handle:
            handle.write(self.alignment_parameters.model_dump_json())

    @QtCore.Slot()
    def aggregate_settings(
        self, settings: dict[str, Any] | HistologySettings | VolumeSettings
    ) -> None:
        if isinstance(settings, pydantic.BaseModel):
            settings = settings.model_dump()

        new_aggregator = self.alignment_parameters.model_copy(update=settings)
        AlignmentParameterAggregator.model_validate(new_aggregator)
        self.alignment_parameters = new_aggregator

    def _generate_thumbnails(self) -> None:
        with ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(self._generate_thumbnail, range(len(self._histology_slices)))

    def _generate_thumbnail(self, index: int) -> None:
        if self._stop_event.is_set():
            return

        self._histology_slices[index].generate_thumbnail(self.current_working_directory)

        # Using .copy() is a workaround to avoid having the thumbnail be deleted
        # before it can be used by the connected slot (e.g., when loading a different
        # image directory while thumbnails for the previous one are still being
        # processed). Thumbnails are meant to be small but this should probably still
        # be fixed.
        # TODO: Avoid .copy()
        self.thumbnail_generated.emit(
            index, self._histology_slices[index].thumbnail_array.copy()
        )

    def _serialise_slices(self) -> list[str]:
        return [histology_slice.file_path for histology_slice in self._histology_slices]

    @staticmethod
    def generate_directory_hash(file_path: str) -> str:
        return hashlib.md5(str(Path(file_path).resolve()).encode("UTF-8")).hexdigest()[
            :10
        ]

    @staticmethod
    def _deserialise_slices(path_list: list[str]) -> list[HistologySlice]:
        return [HistologySlice(file_path) for file_path in path_list]
