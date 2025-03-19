# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from collections.abc import Sequence
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
import h5py
import numpy as np
from PIL import Image
from PySide6 import QtCore
from scipy import ndimage
from scipy.spatial.distance import euclidean
from scipy.spatial.transform import Rotation
from skimage.transform import resize
import vedo  # type: ignore[import]

from histalign.backend.ccf.downloads import download_annotation_volume, download_atlas
from histalign.backend.ccf.paths import get_atlas_path, get_structure_tree
import histalign.backend.io as io
from histalign.backend.maths import (
    compute_centre,
    compute_normal,
    compute_normal_from_raw,
    compute_origin,
    find_plane_mesh_corners,
    signed_vector_angle,
)
from histalign.backend.models import (
    AlignmentSettings,
    Orientation,
    ProjectSettings,
    Resolution,
    VolumeSettings,
)

_module_logger = logging.getLogger(__name__)

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

        self._h5_handle = None

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

    def generate_thumbnail(self, working_directory: str) -> str:
        """Generates thumbnail for self.

        In order to avoid loading the wrapped image into memory unnecessarily, the
        thumbnail is not automatically generated during initialisation. Instead, call
        this method if a thumbnail is required. If the image was loaded at any point,
        a thumbnail will exist already.

        If a thumbnail was previously generated in the provided directory, the cached
        thumbnail will be loaded instead, meaning the image is not loaded into memory.

        Args:
            working_directory (str):
                Working directory to use to find the cache location.
        """
        self.logger.debug(f"Generating thumbnail for {self.hash[:10]}.")

        cache_root = Path(working_directory) / ".cache" / "thumbnails"
        os.makedirs(cache_root, exist_ok=True)

        # Try loading cached file
        cache_path = str(cache_root / f"{self.hash[:10]}.png")
        with contextlib.suppress(FileNotFoundError):
            Image.open(cache_path)
            self.logger.debug(f"Found cached thumbnail ('{cache_path}').")
            return cache_path

        image_array = self.image_array
        if image_array is None:
            # TODO: Include `histoflow` for IO
            if self.file_path.endswith(".h5"):
                h5_handle = h5py.File(self.file_path, "r")
                self._h5_handle = h5_handle

                dataset_name = list(h5_handle.keys())

                if len(dataset_name) != 1:
                    raise ValueError(
                        f"Unexpected number of datasets found. "
                        f"Expected 1, found {len(dataset_name)}. "
                        f"Make sure the file only contains a single image."
                    )

                image_array = h5_handle[dataset_name[0]][::4, ::4]

                if len(image_array.shape) != 2:
                    raise ValueError(
                        f"Unexpected number of dataset dimensions. "
                        f"Expected 2, found {len(image_array.shape)}. "
                        f"Make sure the image has been project to only contain "
                        f"XY data."
                    )
            else:
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

        # Cache thumbnail
        Image.fromarray(thumbnail_array).save(cache_path)
        self.logger.debug(
            f"Finished generating thumbnail and cached it to '{cache_path}'."
        )

        self.thumbnail_array = thumbnail_array

        if self._h5_handle is not None:
            self._h5_handle.close()
            self._h5_handle = None

        return cache_path

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
            executor.map(
                self.generate_thumbnail, range(len(self.parent()._histology_slices))
            )

    def generate_thumbnail(self, index: int):
        if self.stop_event.is_set():
            return

        parent = self.parent()
        histology_slice = parent._histology_slices[index]

        cache_path = histology_slice.generate_thumbnail(parent.working_directory)
        parent.thumbnail_generated.emit(
            index,
            cache_path,
            Path(histology_slice.file_path).name,
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
        return io.load_volume(self.path, self.dtype, return_raw_array=True)

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
            if path.suffix in (".h5", ".hdf5", ".npy", ".jpg", ".jpeg", ".png"):
                if only_neun and path.stem.split("-")[-1] != "neun":
                    continue

                # Only consider 2D, single-dataset files as valid
                if path.suffix in (".h5", ".hdf5"):
                    file = h5py.File(path, mode="r")
                    datasets = list(file.keys())
                    if len(datasets) != 1:
                        continue
                    if len(file[datasets[0]].shape) != 2:
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
