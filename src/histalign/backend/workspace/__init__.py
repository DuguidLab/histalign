# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
from threading import Event
import time
from typing import Literal, Optional

from PIL import Image
from PySide6 import QtCore
import numpy as np
from scipy import ndimage
from skimage.transform import resize
import vedo
from vtkmodules.vtkCommonDataModel import vtkDataSet

from histalign.backend.ccf.downloads import download_atlas
from histalign.backend.ccf.paths import get_atlas_path
import histalign.backend.io as io
from histalign.backend.models import (
    AlignmentSettings,
    Orientation,
    ProjectSettings,
    QuantificationSettings,
    Resolution,
    VolumeSettings,
)
from histalign.backend.models.errors import InvalidOrientationError

DOWNSAMPLE_TARGET_SHAPE = (3000, 3000)
THUMBNAIL_DIMENSIONS = (320, 180)
THUMBNAIL_ASPECT_RATIO = THUMBNAIL_DIMENSIONS[0] / THUMBNAIL_DIMENSIONS[1]


class HistologySlice:
    """Wrapper around histology images present on the file system.

    The class allows easier management of the images and record keeping by a `Workspace`
    by handling the loading from disk and thumbnail generation for the GUI.

    Attributes:
        hash (str): MD5 hash obtained from the image's file name.
        file_path (str): Absolute file path of the image.
        image_array (np.ndarray | None): Array of the image if it has been loaded or
                                         None otherwise.
        thumbnail_array (np.ndarray | None): Array of the thumbnail if it has been
                                             generated or None otherwise.
    """

    hash: str
    file_path: str
    image_array: Optional[np.ndarray] = None
    thumbnail_array: Optional[np.ndarray] = None
    image_downsampling_factor: Optional[int] = None

    def __init__(self, file_path: str) -> None:
        """Creates a new wrapper around the image located at `file_path`.

        Args:
            file_path (str): Path to the image to wrap.
        """
        self.hash = self.generate_file_name_hash(file_path)
        self.file_path = os.path.abspath(file_path)

        self.image_array = None
        self.thumbnail_array = None

        self.logger = logging.getLogger(__name__)

    def load_image(self, working_directory: str, downsampling_factor: int = 0) -> None:
        """Loads wrapped image into memory.

        To avoid having to reload the image again for it, the thumbnail is also
        generated before returning.

        Note that the greater the downsampling factor and the smaller the image, the
        greater the discrepancy between the original aspect ratio and the downsampled
        one. Do not set a downsampling factor if you are unsure whether the discrepancy
        will impact your analysis.

        Args:
            working_directory (str): Working directory to use to find the cache
                                     location.
            downsampling_factor (int): Factor to downsample raw image by. If set to 0
                                       (the default), the image is automatically
                                       downsampled to a manageable size if necessary or
                                       kept as-is if it is already small enough.
        """
        self.image_array = self._load_image(downsampling_factor)

        self.generate_thumbnail(working_directory)

    # noinspection PyUnboundLocalVariable
    def generate_thumbnail(self, working_directory: Optional[str] = None) -> None:
        """Generates thumbnail for self.

        In order to avoid loading the wrapped image into memory unnecessarily, the
        thumbnail is not automatically generated during initialisation. Instead, call
        this method if a thumbnail is required. If the image was loaded at any point,
        a thumbnail will exist already.

        If a thumbnail was previously generated in the provided directory, the cached
        thumbnail will be loaded instead, meaning the image is not loaded into memory.

        Args:
            working_directory (str, optional): Working directory to use to find the
                                               cache location. If set to `None`, the
                                               thumbnail is not cached.
        """
        self.logger.debug(f"Generating thumbnail for {self.hash[:10]}.")

        if working_directory is not None:
            cache_root = Path(working_directory) / ".cache" / "thumbnails"
            os.makedirs(cache_root, exist_ok=True)

            # Try loading cached file
            cache_path = str(cache_root / f"{self.hash[:10]}.png")
            with contextlib.suppress(FileNotFoundError):
                self.thumbnail_array = np.array(Image.open(cache_path))
                self.logger.debug(f"Loaded thumbnail from cache ('{cache_path}').")
                return

        image_array = self.image_array
        if image_array is None:
            image_array = self._load_image(4)

        # Generate thumbnail from `self.image_array`
        aspect_ratio = image_array.shape[1] / image_array.shape[0]
        if aspect_ratio >= THUMBNAIL_ASPECT_RATIO:
            temporary_height = image_array.shape[0] / (
                image_array.shape[1] / THUMBNAIL_DIMENSIONS[0]
            )

            thumbnail_array = resize(
                image_array, (temporary_height, THUMBNAIL_DIMENSIONS[0])
            )

            padding = (THUMBNAIL_DIMENSIONS[1] - thumbnail_array.shape[0]) / 2
            off_by_one = padding - (padding // 1) == 0.5
            padding = int(padding)

            thumbnail_array = np.pad(
                thumbnail_array,
                ((padding, padding + off_by_one), (0, 0)),
            )
        else:
            temporary_width = image_array.shape[1] / (
                image_array.shape[0] / THUMBNAIL_DIMENSIONS[1]
            )

            thumbnail_array = resize(
                image_array, (THUMBNAIL_DIMENSIONS[1], temporary_width)
            )

            padding = (THUMBNAIL_DIMENSIONS[0] - thumbnail_array.shape[1]) / 2
            off_by_one = padding - (padding // 1) == 0.5
            padding = int(padding)

            thumbnail_array = np.pad(
                thumbnail_array,
                ((0, 0), (padding, padding + off_by_one)),
            )

        thumbnail_array = self.normalise_to_8_bit(thumbnail_array)

        if working_directory is not None:
            # Cache thumbnail
            Image.fromarray(thumbnail_array).save(cache_path)
            self.logger.debug(
                f"Finished generating thumbnail and cached it to '{cache_path}'."
            )

        self.thumbnail_array = thumbnail_array

    @staticmethod
    def downsample(array: np.ndarray, downsampling_factor: int) -> np.ndarray:
        """Returns `array` downsampled by `downsampling_factor`.

        Args:
            array (np.ndarray): Array to downsample.
            downsampling_factor (int): Factor to downsample `array` by.

        Returns:
            np.ndarray: Array after downsampling.
        """
        # NOTE: this is around 1.5 orders of magnitude faster than just using
        # skimage.transform.resize or rescale.
        size = np.round(np.array(array.shape) / downsampling_factor).astype(int)
        return np.array(Image.fromarray(array).resize(size[::-1].tolist()))

    @staticmethod
    def normalise_to_8_bit(array: np.ndarray) -> np.ndarray:
        """Returns `array` after normalisation and conversion to u8.

        Args:
            array (np.ndarray): Array to normalise and convert.

        Returns:
            np.ndarray: Array after normalisation and conversion.
        """
        return np.interp(
            array,
            (array.min(), array.max()),
            (0, 2**8 - 1),
        ).astype(np.uint8)

    @staticmethod
    def generate_file_name_hash(file_path: str) -> str:
        """Generate a hash for this slice.

        Note this function only uses the file name at the end of the file path to
        generate the hash. If you require a hash that takes into account the whole,
        resolved path, use `Workspace.generate_directory_hash()`.

        Args:
            file_path (str): File path to use when generating a hash. The file name will
                             be extracted as the last part after splitting on the OS
                             separator.

        Returns:
            str: The generated hash.
        """
        file_name = file_path.split(os.sep)[-1]
        return hashlib.md5(file_name.encode("UTF-8")).hexdigest()

    # noinspection PyUnboundLocalVariable
    def _load_image(self, downsampling_factor: int) -> np.ndarray:
        if downsampling_factor < 1 and downsampling_factor != 0:
            raise ValueError(
                f"Invalid downsampling factor of {downsampling_factor}. "
                f"Factor should be greater than 1 or equal to 0."
            )

        start_time = time.perf_counter()

        image_array = io.load_image(self.file_path)

        if downsampling_factor == 0:
            # If the image is smaller than DOWNSAMPLE_TARGET_SHAPE, don't downsample
            downsampling_factor = round(
                max(
                    1.0,
                    (np.array(image_array.shape) / DOWNSAMPLE_TARGET_SHAPE).max(),
                )
            )
        self.image_downsampling_factor = downsampling_factor
        image_array = self.downsample(image_array, downsampling_factor)

        image_array = self.normalise_to_8_bit(image_array)

        self.logger.debug(
            f"Loaded and processed '{self.file_path.split(os.sep)[-1]}' "
            f"({self.hash[:10]}) in {time.perf_counter() - start_time:.2f} seconds."
        )

        return image_array

    def __eq__(self, other: "HistologySlice") -> bool:
        return self.hash == other.hash


class ThumbnailGeneratorThread(QtCore.QThread):
    stop_event: Event = Event()

    def __init__(self, parent: "Workspace") -> None:
        super().__init__(parent)

    def run(self) -> None:
        with ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(
                self.generate_thumbnail, range(len(self.parent()._histology_slices))
            )

    def generate_thumbnail(self, index: int):
        if self.stop_event.is_set():
            return

        parent = self.parent()
        histology_slice = parent._histology_slices[index]

        histology_slice.generate_thumbnail(parent.working_directory)
        parent.thumbnail_generated.emit(
            index,
            Path(histology_slice.file_path).stem,
            histology_slice.thumbnail_array.copy(),
        )


class Volume:
    """Wrapper class around vedo.Volume

    This class does not directly inherit from vedo.Volume to allow lazy methods for
    downloading from the AllenSDK and loading from the filesystem.
    """

    file_path: Path
    resolution: Resolution
    dtype: np.dtype

    downloading: bool = False
    loading: bool = False
    downloaded: Event = Event()
    loaded: Event = Event()

    def __init__(
        self,
        file_path: Path,
        resolution: Resolution,
        convert_dtype: Optional[np.dtype] = None,
        lazy: bool = False,
    ) -> None:
        self.file_path = file_path
        self.resolution = resolution
        self.dtype = convert_dtype

        self._volume = None
        if not lazy:
            self.ensure_loaded()

    @property
    def shape(self) -> tuple[int, int, int]:
        if self._volume is None:
            return 0, 0, 0

        # Appease the type checking gods
        return (
            int(self._volume.shape[0]),
            int(self._volume.shape[1]),
            int(self._volume.shape[2]),
        )

    @property
    def dataset(self) -> vtkDataSet:
        self.ensure_loaded()
        return self._volume.dataset

    def slice_plane(
        self,
        origin: list[float],
        normal: list[float],
        autocrop: bool = False,
        border: float = 0.5,
        mode: str = "linear",
    ) -> vedo.Mesh:
        self.ensure_loaded()
        return self._volume.slice_plane(origin, normal, autocrop, border, mode)

    def ensure_downloaded(self) -> None:
        if not os.path.exists(self.file_path):
            self.downloading = True
            download_atlas(self.resolution)
            self.downloading = False

        self.downloaded.set()

    def ensure_loaded(self) -> None:
        if self._volume is None:
            if not self.downloading:
                self.ensure_downloaded()
            else:
                self.downloaded.wait()

            if not self.loading:
                self.loading = True
                self._volume = io.load_volume(self.file_path, self.dtype)
                self.loading = False
            else:
                self.loaded.wait()

        self.loaded.set()


class VolumeLoaderThread(QtCore.QThread):
    volume_slicer: Volume

    volume_downloaded: QtCore.Signal = QtCore.Signal()
    volume_loaded: QtCore.Signal = QtCore.Signal()

    def __init__(
        self, volume: "Volume", parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)

        self.volume = volume

    def run(self) -> None:
        self.volume.ensure_downloaded()
        self.volume_downloaded.emit()

        self.volume.ensure_loaded()
        self.volume_loaded.emit()


class VolumeSlicer:
    volume: Volume | vedo.Volume

    def __init__(
        self,
        *,
        volume: Optional[Volume | vedo.Volume] = None,
        path: Optional[Path] = None,
        resolution: Optional[Resolution] = None,
        convert_dtype: np.dtype = np.uint8,
        lazy: bool = True,
    ) -> None:
        if volume is not None:
            self.volume = volume
        else:
            if path is None or resolution is None:
                raise ValueError("Either provide a volume or a path and a resolution.")
            self.volume = Volume(path, resolution, convert_dtype, lazy)

    def slice(
        self,
        settings: VolumeSettings,
        interpolation: Literal["nearest", "linear", "cubic"] = "cubic",
        return_mesh: bool = False,
    ) -> np.ndarray | vedo.Mesh:
        plane_mesh = self.volume.slice_plane(
            origin=self.compute_origin_from_orientation(
                self.volume.dataset.GetCenter(), settings
            ),
            normal=self.compute_normal(settings),
            autocrop=True,
            mode=interpolation,
        )

        if return_mesh:
            return plane_mesh

        slice_array = plane_mesh.pointdata["ImageScalars"].reshape(
            plane_mesh.metadata["shape"]
        )

        if settings.orientation == Orientation.CORONAL:
            slice_array = ndimage.rotate(slice_array, -settings.pitch)
            # Because coronal "looks" against its axis, put left hemisphere on left
            slice_array = np.fliplr(slice_array)
        if settings.orientation == Orientation.HORIZONTAL:
            slice_array = ndimage.rotate(slice_array, -90)
            slice_array = ndimage.rotate(slice_array, -settings.pitch)

        return slice_array

    @staticmethod
    def compute_origin_from_orientation(
        center: list[float] | tuple[float, ...], settings: VolumeSettings
    ) -> list[float]:
        if len(center) != 3:
            raise ValueError(f"Expected center with 3 coordinates, got {len(center)}.")

        # vedo computes the center with float precision but offset calculations assume
        # integer values.
        center = list(map(math.ceil, center))

        match settings.orientation:
            case Orientation.CORONAL:
                # Increasing the offset should bring the user more anterior, hence take
                # away the offset to the center.
                # Also, just like the max value of int8 is 127, the center 0-value needs
                # to be shifted one back. (i.e., an axis with length 10 can have an
                # offset between (10 // 2 = 5) and (10 // 2 - 1 + int(10 % 2)).
                center[0] -= 1
                center[0] -= settings.offset
            case Orientation.HORIZONTAL:
                center[1] += settings.offset
            case Orientation.SAGITTAL:
                center[2] += settings.offset
            case other:
                # Should be impossible thanks to pydantic
                raise InvalidOrientationError(other)

        return center

    @staticmethod
    def compute_normal(settings: VolumeSettings) -> list[float]:
        pitch_radians = math.radians(settings.pitch)
        yaw_radians = math.radians(settings.yaw)

        match settings.orientation:
            case Orientation.CORONAL:
                normal = [
                    math.cos(yaw_radians) * math.cos(pitch_radians),
                    -math.sin(pitch_radians),
                    -math.sin(yaw_radians) * math.cos(pitch_radians),
                ]
            case Orientation.HORIZONTAL:
                normal = [
                    math.sin(pitch_radians),
                    math.cos(yaw_radians) * math.cos(pitch_radians),
                    math.sin(yaw_radians) * math.cos(pitch_radians),
                ]
            case Orientation.SAGITTAL:
                normal = [
                    math.sin(yaw_radians) * math.cos(pitch_radians),
                    math.sin(pitch_radians),
                    math.cos(yaw_radians) * math.cos(pitch_radians),
                ]
            case other:
                # Should be impossible thanks to pydantic
                raise InvalidOrientationError(other)

        return normal


class Workspace(QtCore.QObject):
    project_settings: ProjectSettings
    alignment_settings: AlignmentSettings

    working_directory: str
    last_parsed_directory: Optional[str] = None
    current_aligner_image_hash: Optional[str] = None
    current_aligner_image_index: Optional[int] = None

    thumbnail_generated: QtCore.Signal = QtCore.Signal(int, str, np.ndarray)

    def __init__(
        self, project_settings: ProjectSettings, parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)

        self.project_settings = project_settings

        self.working_directory = str(project_settings.project_path)

        volume_path = get_atlas_path(project_settings.resolution)
        self.alignment_settings = AlignmentSettings(
            volume_path=volume_path,
            volume_settings=VolumeSettings(
                orientation=project_settings.orientation,
                resolution=project_settings.resolution,
            ),
        )

        self._histology_slices: list[HistologySlice] = []
        self._thumbnail_thread = ThumbnailGeneratorThread(self)

    @property
    def resolution(self) -> Resolution:
        return self.project_settings.resolution

    def parse_image_directory(
        self, directory_path: str, only_neun: bool = True
    ) -> None:
        self.last_parsed_directory = directory_path

        working_directory_hash = self.generate_directory_hash(directory_path)
        working_directory = (
            f"{self.project_settings.project_path}{os.sep}{working_directory_hash}"
        )

        metadata_path = f"{working_directory}{os.sep}metadata.json"
        if os.path.exists(metadata_path):
            with open(metadata_path) as handle:
                metadata = json.load(handle)

            previous_image_paths = metadata["slice_paths"]
            removed_paths = [
                path for path in metadata["slice_paths"] if not os.path.exists(path)
            ]
            added_paths = [
                path
                for path in self.gather_image_paths(directory_path)
                if path not in previous_image_paths
            ]

            # Avoid reloading a directory if it did not change
            if (
                self.working_directory == working_directory
                and not removed_paths
                and not added_paths
                and self._histology_slices  # Still load when opening project
            ):
                return

            # Remove paths that no longer point to slices and add new ones
            for path in removed_paths:
                previous_image_paths.remove(path)
            for path in added_paths:
                previous_image_paths.append(path)

            valid_paths = previous_image_paths
        else:
            valid_paths = self.gather_image_paths(directory_path, only_neun)

        self.working_directory = working_directory
        os.makedirs(self.working_directory, exist_ok=True)

        self._histology_slices = self._deserialise_slices(valid_paths)
        self.save_metadata()

    def get_image(self, index: int) -> Optional[np.ndarray]:
        if index >= len(self._histology_slices):
            return None

        histology_slice = self._histology_slices[index]
        if histology_slice.image_array is None:
            self._histology_slices[index].load_image(self.working_directory)
        self.current_aligner_image_hash = histology_slice.hash
        self.current_aligner_image_index = index

        self.alignment_settings.histology_path = histology_slice.file_path
        self.alignment_settings.histology_downsampling = (
            histology_slice.image_downsampling_factor
        )

        return histology_slice.image_array

    def get_thumbnail(self, index: int, timeout: int = 10) -> Optional[np.ndarray]:
        if index >= len(self._histology_slices):
            return None

        while True:
            if self._histology_slices[index].thumbnail_array is not None:
                break

            if not self._thumbnail_thread.is_alive():
                self._histology_slices[index].generate_thumbnail(self.working_directory)
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
        self.save_metadata()

    def start_thumbnail_generation(self) -> None:
        self._thumbnail_thread.start()

    def stop_thumbnail_generation(self) -> None:
        self._thumbnail_thread.stop_event.set()

    def build_alignment_path(self) -> Optional[str]:
        if self.current_aligner_image_hash is None:
            return None

        return f"{self.working_directory}{os.sep}{self.current_aligner_image_hash}.json"

    def save_metadata(self) -> None:
        with open(f"{self.working_directory}{os.sep}metadata.json", "w+") as handle:
            try:
                contents = json.load(handle)
            except json.JSONDecodeError as e:
                if e.args[0].startswith("Expecting value: line 1 column 1"):
                    contents = {}
                else:
                    raise e

            contents["directory_path"] = self.last_parsed_directory
            contents["slice_paths"] = self._serialise_slices(self._histology_slices)

            json.dump(contents, handle)

    def save(self) -> None:
        with open(
            f"{self.project_settings.project_path}{os.sep}project.json", "w"
        ) as handle:
            dump = {
                "project_settings": self.project_settings.model_dump(),
                "workspace_settings": {
                    "working_directory": self.working_directory,
                    "last_parsed_directory": self.last_parsed_directory,
                    "current_aligner_image_hash": self.current_aligner_image_hash,
                    "current_aligner_image_index": self.current_aligner_image_index,
                },
                "alignment_settings": self.alignment_settings.model_dump(),
            }
            json.dump(dump, handle)

    @staticmethod
    def load(file_path) -> "Workspace":
        # Literal "/" instead of `os.sep` since "\"s are automatically converted to "/"s
        # by either PySide or pathlib
        if file_path.split("/")[-1] != "project.json":
            raise ValueError("Invalid project file.")

        with open(file_path) as handle:
            contents = json.load(handle)

        project_settings = ProjectSettings(**contents["project_settings"])
        workspace = Workspace(project_settings)

        alignment_settings = AlignmentSettings(**contents["alignment_settings"])
        workspace.alignment_settings = alignment_settings

        workspace_settings = contents["workspace_settings"]
        workspace.working_directory = workspace_settings["working_directory"]
        workspace.last_parsed_directory = workspace_settings["last_parsed_directory"]
        workspace.current_aligner_image_hash = workspace_settings[
            "current_aligner_image_hash"
        ]
        workspace.current_aligner_image_index = workspace_settings[
            "current_aligner_image_index"
        ]

        if workspace.last_parsed_directory is not None:
            workspace.parse_image_directory(workspace.last_parsed_directory)

        return workspace

    @QtCore.Slot()
    def save_alignment(self) -> None:
        alignment_path = self.build_alignment_path()
        if alignment_path is None:
            return

        with open(alignment_path, "w") as handle:
            handle.write(self.alignment_settings.model_dump_json())

    @QtCore.Slot()
    def load_alignment(self) -> bool:
        alignment_path = self.build_alignment_path()
        if alignment_path is None:
            return False

        with open(alignment_path) as handle:
            alignment_settings = AlignmentSettings(**json.load(handle))

        alignment_settings.volume_settings.offset = int(
            round(
                alignment_settings.volume_settings.offset
                * (alignment_settings.volume_settings.resolution / self.resolution)
            )
        )

        self.alignment_settings = alignment_settings

    @QtCore.Slot()
    def update_alignment_scaling(self, scaling: dict[str, float]) -> None:
        volume_scaling = scaling.get("volume_scaling")
        histology_scaling = scaling.get("histology_scaling")

        if volume_scaling:
            self.alignment_settings.volume_scaling = volume_scaling
        if histology_scaling:
            self.alignment_settings.histology_scaling = histology_scaling

    @staticmethod
    def gather_image_paths(directory_path: str, only_neun: bool = True) -> list[str]:
        image_paths = []
        for path in Path(directory_path).iterdir():
            if path.suffix in (".h5", ".hdf5", ".npy", ".jpg", ".jpeg", ".png"):
                if only_neun and path.stem.split("-")[-1] != "neun":
                    continue
                image_paths.append(str(path))

        # Natural sorting taken from: https://stackoverflow.com/a/16090640
        image_paths.sort(
            key=lambda s: [
                int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)
            ]
        )

        return image_paths

    @staticmethod
    def generate_directory_hash(file_path: str) -> str:
        return hashlib.md5(str(Path(file_path).resolve()).encode("UTF-8")).hexdigest()[
            :10
        ]

    @staticmethod
    def _serialise_slices(histology_slices: list[HistologySlice]) -> list[str]:
        return [histology_slice.file_path for histology_slice in histology_slices]

    @staticmethod
    def _deserialise_slices(path_list: list[str]) -> list[HistologySlice]:
        return [HistologySlice(file_path) for file_path in path_list]
