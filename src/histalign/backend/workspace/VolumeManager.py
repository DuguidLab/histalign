# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import math
import typing

import nrrd
import numpy as np
import vedo

from histalign.backend.models.VolumeSettings import VolumeSettings


class VolumeManager:
    def __init__(self) -> None:
        self._volume = None

    @property
    def shape(self):
        if self._volume is None:
            raise Exception("Tried accessing shape of volume without a volume loaded.")

        return self._volume.shape

    def load_volume(self, file_path: str) -> None:
        file_extension = file_path.split(".")[-1]

        match file_extension:
            case "nrrd":
                # If using NRRD, assume it is 16-bit
                array = nrrd.read(file_path)[0]
                array = np.interp(
                    array, (array.min(), array.max()), (0, 2**8 - 1)
                ).astype(np.uint8)
            case "npy":
                # If using NPY, assume it was already converted to 8-bit
                array = np.load(file_path)
            case _:
                raise ValueError("Unknown volume file type.")

        self._volume = vedo.Volume(array)

    def slice_volume(
        self, settings: typing.Optional[VolumeSettings] = None
    ) -> np.ndarray:
        if settings is None:
            settings = VolumeSettings()

        if settings.origin is None:
            settings.origin = tuple(self._volume.center())

        slice_mesh = self._volume.slice_plane(
            origin=(*settings.origin[:-1], settings.origin[-1] + settings.offset),
            normal=self.calculate_normals(settings.leaning_angle, settings.axes),
            autocrop=True,
        )

        return slice_mesh.pointdata["ImageScalars"].reshape(
            slice_mesh.metadata["shape"]
        )

    @staticmethod
    def calculate_normals(angle: int, axes: tuple[int, int]) -> list[float]:
        normals = [0.0] * 3

        normals[list({0, 1, 2} - set(axes))[0]] = math.cos(math.radians(angle))

        normals[axes[1]] = math.sin(math.radians(angle))
        normals[axes[1]] *= -1 if axes[1] - axes[0] == 1 else 1

        return normals
