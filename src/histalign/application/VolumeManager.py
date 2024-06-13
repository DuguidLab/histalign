# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import math
import time
import typing

import nrrd
import numpy as np
import vedo


class VolumeManager:
    average_volume: vedo.Volume
    annotation_volume: vedo.Volume

    def __init__(self, file_path: str) -> None:
        self.load_volume(file_path)

    def get_slice_from_volume(
        self,
        kind: typing.Literal["normal", "annotation"] = "normal",
        origin: typing.Optional[tuple[int, int, int]] = None,
        angle: int = 0,
        axes: tuple[int, int] = (0, 1),
        offset: int = 0,
    ) -> np.ndarray:
        kind = kind.lower()
        if kind == "normal":
            volume = self.average_volume
        elif kind == "annotation":
            if self.annotation_volume is None:
                raise Exception("No volume for type 'annotation'.")
            volume = self.annotation_volume
        else:
            raise Exception("Invalid volume type.")

        if origin is None:
            origin = volume.center()

        volume_slice = volume.slice_plane(
            origin=(
                *origin[:2],
                origin[2] + offset,
            ),
            normal=self.calculate_normals(angle, axes),
            autocrop=True,
        )

        slice_array = volume_slice.pointdata["ImageScalars"].reshape(
            volume_slice.metadata["shape"]
        )
        return slice_array

    def load_volume(
        self, file_path: str, kind: typing.Literal["normal", "annotation"] = "normal"
    ) -> None:
        extension = file_path.split(".")[-1]
        if extension == "nrrd":
            # If using NRRD, assume it is 16-bit
            array = nrrd.read(file_path)[0]
            array = np.interp(
                array, (array.min(), array.max()), (0, 2**8 - 1)
            ).astype(np.uint8)
        elif extension == "npy":
            # If using NPY, assume it was already converted to 8-bit
            array = np.load(file_path)

        volume = vedo.Volume(array)

        kind = kind.lower()
        if kind == "normal":
            self.average_volume = volume
        elif kind == "annotation":
            self.annotation_volume = volume
        else:
            raise Exception("Invalid volume type.")

    @staticmethod
    def calculate_normals(angle: int, axes: tuple[int, int]) -> list[int | float]:
        normals = [0, 0, 0]

        normals[list({0, 1, 2} - set(axes))[0]] = math.cos(math.radians(angle))

        normals[axes[1]] = math.sin(math.radians(angle))
        normals[axes[1]] *= -1 if axes[1] - axes[0] == 1 else 1

        return normals
