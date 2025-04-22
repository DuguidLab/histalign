# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
import contextlib
from functools import partial
import hashlib
import json
import logging
import math
from multiprocessing import Process, Queue
import os
from pathlib import Path
from queue import Empty
import re
from threading import Event
import time
from typing import Any, get_type_hints, Literal, Optional

from allensdk.core.structure_tree import StructureTree  # type: ignore[import]
import numpy as np
from PIL import Image
from PySide6 import QtCore
from scipy import ndimage
from scipy.spatial.distance import euclidean
from scipy.spatial.transform import Rotation
import vedo  # type: ignore[import]

from histalign.backend.ccf import (
    download_annotation_volume,
    download_atlas,
    get_atlas_path,
    get_structure_tree,
)
from histalign.backend.maths import (
    compute_centre,
    compute_normal,
    compute_normal_from_raw,
    compute_origin,
    find_plane_mesh_corners,
    normalise_array,
    signed_vector_angle,
)
from histalign.backend.models import (
    AlignmentSettings,
    Orientation,
    ProjectSettings,
    Resolution,
    VolumeSettings,
)
from histalign.io import ImageFile, open_file
import histalign.io as io
from histalign.io.image import EXTENSIONS, SUPPORTED_READ_FORMATS
from histalign.io.transform.transforms import downscaling_transform

_module_logger = logging.getLogger(__name__)

DOWNSAMPLE_TARGET_SHAPE = (3000, 3000)  # IJ not XY


class ThumbnailGeneratorThread(QtCore.QThread):
    stop_event: Event

    def __init__(self, parent: Workspace) -> None:
        super().__init__(parent)

        self._parent = parent

        self.stop_event = Event()

    def start(
        self,
        priority: QtCore.QThread.Priority = QtCore.QThread.Priority.InheritPriority,
    ):
        _module_logger.debug(f"Starting ThumbnailGeneratorThread ({hex(id(self))}).")
        super().start(priority)

    def run(self) -> None:
        with ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(self.generate_thumbnail, self.parent().iterate_handles())

    def generate_thumbnail(self, handle: ImageFile):
        if self.stop_event.is_set():
            return

        parent = self.parent()

        cache_path = build_thumbnail_path(Path(parent.working_directory), handle.hash)
        try:
            Image.open(cache_path)
            _module_logger.debug(
                f"Found cached thumbnail for '{handle.file_path}' at '{cache_path}'."
            )
        except FileNotFoundError:
            thumbnail = handle.generate_thumbnail()
            thumbnail = normalise_array(thumbnail, np.uint8)
            Image.fromarray(thumbnail).save(cache_path)
            _module_logger.debug(
                f"Cached thumbnail for '{handle.file_path}' at '{cache_path}'."
            )

        parent.thumbnail_generated.emit(
            parent.index(handle),
            cache_path,
            handle.file_path.name,
        )

    def parent(self) -> Workspace:
        return self._parent


class Volume(QtCore.QObject):
    """Wrapper class around vedo.Volume.

    It can be used anywhere a vedo.Volume is required as it passes attribute setting and
    getting through to the underlying vedo object. The wrapping provides a way to only
    lazily load the volume from disk, allowing the network and disk IO to happen in a
    different task.

    It is also a QObject which provides signals notifying of (down)loading progress.
    """

    path: Path
    resolution: Resolution
    dtype: Optional[np.dtype]

    _volume: Optional[vedo.Volume] = None

    downloaded: QtCore.Signal = QtCore.Signal()
    loaded: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        path: str | Path,
        resolution: Resolution,
        convert_dtype: Optional[type | np.dtype] = None,
        lazy: bool = False,
    ) -> None:
        super().__init__(None)

        if isinstance(path, str):
            path = Path(path)
        self.path = path

        self.resolution = resolution

        dtype = convert_dtype
        if isinstance(dtype, type):
            try:
                dtype = np.dtype(dtype)
            except TypeError:
                dtype = np.dtype(np.uint8)
                _module_logger.warning(
                    f"Could not interpret '{convert_dtype}' as a NumPy datatype. "
                    f"Defaulting to {dtype}."
                )
        self.dtype = dtype

        if not lazy:
            self.ensure_loaded()

    @property
    def is_loaded(self) -> bool:
        return self._volume is not None

    def ensure_loaded(self) -> None:
        """Ensures the volume is loaded (and downloads it if necessary)."""
        self._ensure_downloaded()
        self._ensure_loaded()

    def update_from_array(self, array: np.ndarray) -> None:
        """Updates the wrapped volume with a `vedo.Volume` of `array`."""
        self._volume = vedo.Volume(array)

    def load(self) -> np.ndarray:
        """Loads the raw numpy array this volume points to."""
        return io.load_volume(self.path, self.dtype, as_array=True)

    def _ensure_downloaded(self) -> None:
        if not self.path.exists() and not self.is_loaded:
            self._download()

        self.downloaded.emit()

    def _download(self) -> None:
        download_atlas(self.resolution)

    def _ensure_loaded(self) -> None:
        if not self.is_loaded:
            self._load()

        self.loaded.emit()

    def _load(self) -> None:
        self.update_from_array(self.load())

    def __getattr__(self, name: str) -> Any:
        if not self.is_loaded:
            self.ensure_loaded()
        return getattr(self._volume, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in get_type_hints(type(self)).keys() or name in dir(self):
            return super().__setattr__(name, value)

        if not self.is_loaded:
            self.ensure_loaded()
        setattr(self._volume, name, value)


class AnnotationVolume(Volume):
    """A wrapper around the Allen Institute's annotated CCF volumes.

    Since the Allen Institute has reserved some ID ranges, there are huge gaps in the
    values of the annotated volume. This wrapper maps the IDs present in the raw file
    into sequential values to allow a volume of uint16 instead of uint32, freeing a lot
    of memory and not really incurring any loading cost (around 2 seconds on my
    machine for the 25um annotated volume).

    The algorithm to efficiently replace the values in the annotated volume is taken
    from here: https://stackoverflow.com/a/29408060.
    """

    _id_translation_table: np.ndarray
    _structure_tree: StructureTree

    def get_name_from_voxel(self, coordinates: Sequence) -> str:
        """Returns the name of the brain structure at `coordinates`.

        Args:
            coordinates (Sequence): Integer coordinates of the voxel to return the name
                                    of.

        Returns:
            str: The name of the structure at `coordinates`.
        """

        if not hasattr(self, "_structure_tree") or not self.is_loaded:
            return ""

        if isinstance(coordinates, np.ndarray):
            coordinates = coordinates.tolist()
        if isinstance(coordinates, list):
            coordinates = tuple(map(int, coordinates))

        for i in range(len(coordinates)):
            if coordinates[i] < 0 or coordinates[i] >= self._volume.shape[i]:
                return ""

        value = self._volume.tonumpy()[coordinates]

        node_details = self._structure_tree.get_structures_by_id(
            [self._id_translation_table[value]]
        )[0]
        if node_details is not None:
            name = node_details["name"]
        else:
            name = ""

        return name

    def update_from_array(self, array: np.ndarray) -> None:
        unique_values = np.unique(array)
        replacement_array = np.empty(array.max() + 1, dtype=np.uint16)
        replacement_array[unique_values] = np.arange(len(unique_values))

        self._id_translation_table = unique_values
        self._structure_tree = get_structure_tree(Resolution.MICRONS_100)

        super().update_from_array(replacement_array[array])

    def _download(self) -> None:
        download_annotation_volume(self.resolution)


class VolumeLoaderThread(QtCore.QThread):
    """A QThread which uses a separate process to load a `Volume`.

    This class steps through a process to allow easier abrupt termination of the IO
    operation. Only using a QThread which does the work on its own causes a freeze of
    the whole application when abruptly terminating it while trying to close a file
    handle. This approach of using a separate process incurs some overhead to create the
    process but it is much easier to terminate it while allowing normal interruptions
    on the QThread.
    """

    volume: Volume

    def __init__(self, volume: Volume, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)

        self.volume = volume

    def start(
        self,
        priority: QtCore.QThread.Priority = QtCore.QThread.Priority.InheritPriority,
    ):
        _module_logger.debug(f"Starting VolumeLoaderThread ({hex(id(self))}).")
        super().start(priority)

    def run(self):
        # Shortcircuit to avoid pickling an already-loaded volume
        if self.volume.is_loaded:
            self.volume.downloaded.emit()
            self.volume.loaded.emit()
            return

        # Download
        process = Process(target=self.volume._ensure_downloaded)
        process.start()
        while process.is_alive():
            if self.isInterruptionRequested():
                process.terminate()
                process.join()
                return

            time.sleep(0.25)

        self.volume.downloaded.emit()

        # Load
        queue = Queue()
        process = Process(
            target=partial(self._run, self.volume, queue),
        )

        process.start()
        while process.is_alive():
            if self.isInterruptionRequested():
                process.terminate()
                process.join()
                return

            with contextlib.suppress(Empty):
                self.volume.update_from_array(queue.get(block=False))
                self.volume.loaded.emit()

            time.sleep(0.1)

    @staticmethod
    def _run(volume: Volume, queue: Queue) -> None:
        queue.put(volume.load())


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
        return_display_plane: bool = False,
        origin: Optional[list[float]] = None,
    ) -> np.ndarray | vedo.Mesh:
        origin = origin or compute_origin(compute_centre(self.volume.shape), settings)
        normal = compute_normal(settings)
        plane_mesh = self.volume.slice_plane(
            origin=origin, normal=normal.tolist(), mode=interpolation
        )

        # vedo cuts down the mesh in a way I don't fully understand. Therefore, the
        # origin of the plane used with `slice_plane` is not actually the centre of
        # the image that we can recover from mesh when working with an offset and
        # pitch/yaw. Instead, the image in `plane_mesh` is cropped and then padded so
        # that the centre of the image corresponds to the origin.
        display_plane = self.reproduce_display_plane(origin, settings)
        if return_display_plane:
            return display_plane

        plane_array = self.crop_and_pad_to_display_plane(
            plane_mesh, display_plane, origin, normal, settings
        )

        # Correct vedo-specific rotations and apply some custom rotations for
        # presentation to the user.
        if settings.orientation == Orientation.CORONAL:
            # Correct the vedo rotation so that superior is at the top and anterior
            # is at the bottom.
            plane_array = ndimage.rotate(plane_array, settings.pitch, reshape=False)
            # Flip left-right so that the left hemisphere is on the left
            plane_array = np.fliplr(plane_array)
        elif settings.orientation == Orientation.HORIZONTAL:
            # Correct the vedo rotation and apply own so that anterior is at the top
            # and posterior is at the bottom.
            plane_array = ndimage.rotate(
                plane_array, settings.pitch - 90, reshape=False
            )

        return plane_array

    @staticmethod
    def reproduce_display_plane(
        origin: np.ndarray, settings: VolumeSettings
    ) -> vedo.Plane:
        """Reproduces the slicing alignment plane but centred at `origin`.

        Args:
            origin (np.ndarray): Origin of the plane.
            settings (VolumeSettings): Settings used for alignment.

        Returns:
            vedo.Plane:
                A plane centred at `origin` and whose normal is the same as the plane
                described by `settings`.
        """
        orientation = settings.orientation
        pitch = settings.pitch
        yaw = settings.yaw

        display_plane = vedo.Plane(
            pos=origin,
            normal=compute_normal_from_raw(0, 0, orientation),
            s=(1.5 * max(settings.shape),) * 2,
        )

        match orientation:
            case Orientation.CORONAL:
                display_plane.rotate(pitch, axis=[0, 0, 1], point=origin)
                display_plane.rotate(
                    yaw,
                    axis=Rotation.from_euler("Z", pitch, degrees=True).apply([0, 1, 0]),
                    point=origin,
                )
                display_plane.rotate(
                    -pitch,
                    axis=Rotation.from_euler("ZY", [pitch, yaw], degrees=True).apply(
                        [1, 0, 0]
                    ),
                    point=origin,
                )
            case Orientation.HORIZONTAL:
                display_plane.rotate(180, axis=[0, 1, 0], point=origin)
                display_plane.rotate(pitch, axis=[0, 0, 1], point=origin)
                display_plane.rotate(
                    yaw,
                    axis=Rotation.from_euler("Z", pitch, degrees=True).apply([1, 0, 0]),
                    point=origin,
                )
                display_plane.rotate(
                    90 - pitch,
                    axis=Rotation.from_euler("ZX", [pitch, yaw], degrees=True).apply(
                        [0, 1, 0]
                    ),
                    point=origin,
                )
            case Orientation.SAGITTAL:
                # Pitch
                display_plane.rotate(pitch, axis=[1, 0, 0], point=origin)
                # Yaw
                display_plane.rotate(
                    yaw,
                    axis=Rotation.from_euler("X", pitch, degrees=True).apply([0, 1, 0]),
                    point=origin,
                )

        return display_plane

    @staticmethod
    def crop_and_pad_to_display_plane(
        image_plane: vedo.Mesh,
        display_plane: vedo.Plane,
        origin: np.ndarray,
        normal: np.ndarray,
        settings: VolumeSettings,
    ) -> np.ndarray:
        """Crops and pads the `image_plane` data into `display_plane`'s shape.

        From the display plane, the four corners are retrieved (a, b, c, d). From the
        image plane, three corners are retrieved (A, C, D). The display plane being in
        place, overlaps the image plane. Hence, the distance between A<->a and B<->b can
        be computed and decomposed into x, y, x_prime, and y_prime values which inform
        how to either crop the image plane data or pad it so that the final image
        represents the surface covered by the display plane.

        Args:
            image_plane (vedo.Mesh): Plane mesh with the image data.
            display_plane (vedo.Plane): Plane to crop to.
            origin (np.ndarray): Origin of the display plane.
            normal (np.ndarray): Normal of the display plane.
            settings (VolumeSettings): Settings used for alignment.

        Returns:
            np.ndarray:
                The cropped and padded image from `image_plane` fit to `display_plane`'s
                shape.
        """
        orientation = settings.orientation
        pitch = settings.pitch
        yaw = settings.yaw

        A, _, D, C = find_plane_mesh_corners(image_plane)
        a, b, d, c = display_plane.points

        if orientation == Orientation.SAGITTAL:
            # Mimic vedo rotation
            display_plane.rotate(
                signed_vector_angle(a - d, A - D, normal),
                axis=Rotation.from_euler("XY", [pitch, yaw], degrees=True).apply(
                    [0, 0, 1]
                ),
                point=origin,
            )
            a, b, d, c = display_plane.points

        e = euclidean(A, a)
        e_prime = euclidean(C, c)

        theta = signed_vector_angle(A - a, a - d, normal)
        theta_prime = signed_vector_angle(C - c, b - c, normal)

        x, y, x_prime, y_prime = VolumeSlicer.extract_values(
            e, theta, e_prime, theta_prime
        )

        match settings.orientation:
            case Orientation.CORONAL:
                x += 1
                y_prime -= 1
            case Orientation.HORIZONTAL:
                x_prime -= 1
                y += 1
            case Orientation.SAGITTAL:
                x += 1
                y += 1

        image = image_plane.pointdata["ImageScalars"].reshape(
            image_plane.metadata["shape"]
        )
        image = image[
            x if x > 0 else 0 : image.shape[0] - (-x_prime if x_prime < 0 else 0),
            y if y > 0 else 0 : image.shape[1] - (-y_prime if y_prime < 0 else 0),
        ]
        image = np.pad(
            image,
            (
                [-x if x < 0 else 0, x_prime if x_prime > 0 else 0],
                [-y if y < 0 else 0, y_prime if y_prime > 0 else 0],
            ),
        )

        return image

    @staticmethod
    def extract_values(
        e: float, theta: float, e_prime: float, theta_prime: float
    ) -> tuple[int, int, int, int]:
        """Computes the x, y, x_prime, and y_prime values required for cropping/padding.

        Args:
            e (float): Euclidean distance between A and a.
            theta (float): Signed angle between da and aA.
            e_prime (float): Euclidean distance between C and c.
            theta_prime (float): Signed angle between cb and cC.

        Returns:
            tuple[int, int, int, int]:
                The cropping and padding values.
        """
        x = round(e * math.cos(math.radians(theta)))
        y = round(e * math.sin(math.radians(theta)))
        x_prime = round(e_prime * math.cos(math.radians(theta_prime)))
        y_prime = round(e_prime * math.sin(math.radians(theta_prime)))

        return x, y, x_prime, y_prime


class Workspace(QtCore.QObject):
    project_settings: ProjectSettings
    alignment_settings: AlignmentSettings

    working_directory: str
    last_parsed_directory: Optional[str] = None
    current_aligner_image_hash: Optional[str] = None
    current_aligner_image_index: Optional[int] = None

    thumbnail_generated: QtCore.Signal = QtCore.Signal(int, Path, str)

    def __init__(
        self, project_settings: ProjectSettings, parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)

        self.project_settings = project_settings

        self.working_directory = str(project_settings.project_path)

        volume_path = get_atlas_path(project_settings.resolution)
        self.alignment_settings = AlignmentSettings(
            volume_path=Path(volume_path),
            volume_settings=VolumeSettings(
                orientation=project_settings.orientation,
                resolution=project_settings.resolution,
            ),
        )

        self._file_handles: list[ImageFile] = []
        self._thumbnail_thread = ThumbnailGeneratorThread(self)

    @property
    def resolution(self) -> Resolution:
        return self.project_settings.resolution

    def parse_image_directory(
        self, directory_path: str, only_neun: bool = False
    ) -> None:
        self.last_parsed_directory = directory_path
        self.current_aligner_image_hash = None
        self.current_aligner_image_index = None

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
                for path in self.gather_image_paths(directory_path, only_neun)
                if path not in previous_image_paths
            ]

            # Avoid reloading a directory if it did not change
            if (
                self.working_directory == working_directory
                and not removed_paths
                and not added_paths
                and self._file_handles  # Still load when opening project
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

        if len(valid_paths) == 0:
            _module_logger.warning(
                f"Could not find any valid images in '{directory_path}'."
            )

        self.working_directory = working_directory
        os.makedirs(self.working_directory, exist_ok=True)

        self._file_handles = self._deserialise_handles(valid_paths)
        self.save_metadata()

    def get_image(self, index: int) -> Optional[np.ndarray]:
        if index >= len(self._file_handles):
            _module_logger.error(
                f"Failed retrieving image at index {index}, index out of range."
            )
            return None

        image_handle = self._file_handles[index]
        self.current_aligner_image_hash = image_handle.hash
        self.current_aligner_image_index = index

        self.alignment_settings.histology_path = image_handle.file_path

        image = image_handle.read_image(image_handle.index)
        downsampling_factor = compute_downsampling_factor(image.shape)
        image = downscaling_transform(image, downsampling_factor, naive=True)

        self.alignment_settings.histology_downsampling = downsampling_factor

        return image

    def swap_images(self, index1: int, index2: int) -> None:
        self._file_handles[index1], self._file_handles[index2] = (
            self._file_handles[index2],
            self._file_handles[index1],
        )
        self.save_metadata()

    def start_thumbnail_generation(self) -> None:
        self._thumbnail_thread.start()

    def stop_thumbnail_generation(self) -> None:
        self._thumbnail_thread.stop_event.set()

    def iterate_handles(self) -> Iterator[ImageFile]:
        for handle in self._file_handles:
            yield handle

    def index(self, handle: ImageFile) -> int:
        """Returns the index of the handle provided.

        Args:
            handle (ImageFile): ImageFile handle to find the index of.

        Returns:
            int: The index of the handle or -1 if it is not found.
        """
        try:
            return self._file_handles.index(handle)
        except ValueError:
            return -1

    def list_hashes(self) -> list[str]:
        return [handle.hash for handle in self._file_handles]

    def build_alignment_path(self, hash: str = "") -> Optional[str]:
        hash = hash or self.current_aligner_image_hash

        if hash is None:
            return None

        return f"{self.working_directory}{os.sep}{hash}.json"

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
            contents["slice_paths"] = self._serialise_handles(self._file_handles)

            # noinspection PyTypeChecker
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
            # noinspection PyTypeChecker
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

        if workspace.last_parsed_directory is not None:
            workspace.parse_image_directory(workspace.last_parsed_directory)

        workspace.current_aligner_image_hash = workspace_settings[
            "current_aligner_image_hash"
        ]
        workspace.current_aligner_image_index = workspace_settings[
            "current_aligner_image_index"
        ]

        return workspace

    @QtCore.Slot()
    def save_alignment(self) -> None:
        alignment_path = self.build_alignment_path()
        if alignment_path is None:
            return

        with open(alignment_path, "w") as handle:
            handle.write(self.alignment_settings.model_dump_json())

    @QtCore.Slot()
    def load_alignment(self) -> None:
        alignment_path = self.build_alignment_path()
        if alignment_path is None:
            return

        with open(alignment_path) as handle:
            alignment_settings = AlignmentSettings(**json.load(handle))

        alignment_settings.volume_settings.offset = int(
            round(
                alignment_settings.volume_settings.offset
                * (alignment_settings.volume_settings.resolution / self.resolution)
            )
        )

        # Don't overwrite scalings as those are window-dependent
        alignment_settings.volume_scaling = self.alignment_settings.volume_scaling
        alignment_settings.histology_scaling = self.alignment_settings.histology_scaling

        self.alignment_settings = alignment_settings

    @QtCore.Slot()
    def delete_alignment(self) -> None:
        alignment_path = self.build_alignment_path()
        if alignment_path is None:
            return

        os.remove(alignment_path)

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
            if EXTENSIONS.get(path.suffix) in SUPPORTED_READ_FORMATS:
                if only_neun and path.stem.split("-")[-1] != "neun":
                    continue

                # Only consider 2D images
                handle = open_file(path)
                if len(handle.shape) != 2:
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
    def _serialise_handles(file_handles: list[ImageFile]) -> list[str]:
        return [str(handle.file_path) for handle in file_handles]

    @staticmethod
    def _deserialise_handles(path_list: list[str]) -> list[ImageFile]:
        return [open_file(path) for path in path_list]


def build_thumbnail_path(
    alignment_directory: Path, hash: str, ensure_directory_exists: bool = True
) -> Path:
    return (
        get_thumbnail_cache_root(alignment_directory, ensure_directory_exists)
        / f"{hash[:10]}.png"
    )


def get_thumbnail_cache_root(
    alignment_directory: Path, ensure_exists: bool = True
) -> Path:
    root = alignment_directory / ".cache"

    if ensure_exists:
        os.makedirs(root, exist_ok=True)

    return root


def compute_downsampling_factor(shape: tuple[int, ...]) -> int:
    """Computes the closest downsampling factor to fit shape inside default shape.

    Args:
        shape (tuple[int, ...]): Shape to downsample.

    Returns:
        int:
            The downsampling factor that scales shape down to fit inside
            DOWNSAMPLE_TARGET_SHAPE.
    """
    return math.ceil(
        max(
            1.0,
            (np.array(shape) / DOWNSAMPLE_TARGET_SHAPE).max(),
        )
    )
