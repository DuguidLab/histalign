# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from collections.abc import Sequence
from contextlib import suppress
import json
from json import JSONDecodeError
import logging
from pathlib import Path
from typing import Optional

import h5py
import numpy as np

from histalign.io import DimensionOrder
from histalign.io.image import MultiSeriesImageFile, register_plugin
from histalign.io.image.metadata import OmeXml, OmeXmlChannel, UnitsLength

_module_logger = logging.getLogger(__name__)


class Hdf5ImagePlugin(MultiSeriesImageFile):
    format: str = "HDF5"
    extensions: tuple[str, ...] = (".h5", ".hdf5")

    series_support = 2

    @property
    def shape(self) -> tuple[int, ...]:
        return self.file_handle[self._datasets[self.series_index]].shape

    @property
    def dtype(self) -> np.dtype:
        return self.file_handle[self._datasets[self.series_index]].dtype

    @property
    def series_count(self) -> int:
        return len(self._datasets)

    def _open(
        self, file_path: Path, mode: str, metadata: Optional[OmeXml] = None, **kwargs
    ) -> None:
        self.file_handle = h5py.File(file_path, mode)
        if mode != "r":
            if (shape := kwargs.get("shape")) is None:
                raise ValueError("No shape provided for new file in writing mode.")
            if (dtype := kwargs.get("dtype")) is None:
                raise ValueError("No dtype provided for new file in writing mode.")
            self.create_series(shape, dtype, metadata)

        self.query_datasets()

    def load(self) -> np.ndarray:
        return self.file_handle[self._datasets[self.series_index]][:]

    def close(self) -> None:
        self.file_handle.close()
        super().close()

    def try_get_dimension_order(self) -> Optional[DimensionOrder]:
        dimension_order = self.file_handle[self._datasets[self.series_index]].attrs.get(
            "DimensionOrder"
        )
        if dimension_order is None:
            return dimension_order

        # Dimension order is stored as a quoted string
        return dimension_order[1:-1]

    def read_image(self, index: tuple[slice, ...]) -> np.ndarray:
        return self.file_handle[self._datasets[self.series_index]][index]

    def write_image(self, image: np.ndarray, index: tuple[slice, ...]) -> None:
        self.file_handle[self._datasets[self.series_index]][index] = image

    def create_series(
        self, shape: Sequence[int], dtype: np.dtype, metadata: Optional[OmeXml] = None
    ) -> None:
        self.file_handle.create_dataset(
            name=f"series{self.series_index}",
            shape=shape,
            dtype=dtype,
        )
        self.query_datasets()
        if metadata is not None:
            self._add_metadata(metadata)
        self.reset_index()

    def query_datasets(self) -> None:
        self._datasets = list(self.file_handle.keys())

    def _add_metadata(self, metadata: OmeXml) -> None:
        dataset = self.file_handle[self._datasets[self.series_index]]

        # There isn't any standard for metadata packaging in an HDF5 file for scientific
        # images (in a simple manner, i.e. no NWB). This tries to mirror the OME-XML
        # standard but we are still only compatible with ourselves.
        for attribute_name, value in metadata.model_dump().items():
            dataset.attrs[attribute_name] = json.dumps(value)

        # Element size compatibility with HDF5 Vibez plugin for ImageJ.
        # Dimensions are read in order "depth (Z) -> height (Y) -> width (X)".
        # For reference of how the plugin saves element sizes itself, see:
        # https://github.com/fiji/HDF5_Vibez/blob/5ae1911a5536e4bb460b483308dc545c47675c49/src/main/java/sc/fiji/hdf5/HDF5ImageJ.java#L750
        dataset.attrs["element_size_um"] = [
            convert_to_microns(metadata.PhysicalSizeZ, metadata.PhysicalSizeZUnit),
            convert_to_microns(metadata.PhysicalSizeY, metadata.PhysicalSizeYUnit),
            convert_to_microns(metadata.PhysicalSizeX, metadata.PhysicalSizeXUnit),
        ]

    def _extract_metadata(self) -> OmeXml:
        dataset = self.file_handle[self._datasets[self.series_index]]

        attrs = dataset.attrs
        attributes = {}
        for name, attribute in attrs.items():
            with suppress(JSONDecodeError, TypeError):
                attributes[name] = json.loads(attribute)

        channel_list = [
            OmeXmlChannel(**channel) for channel in attributes.get("Channel", [])
        ]

        return OmeXml(
            DimensionOrder=attributes.get("DimensionOrder") or self.dimension_order,
            SizeX=attributes.get("SizeX")
            or self.shape[self.dimension_order.value.index("X")],
            SizeY=attributes.get("SizeY")
            or self.shape[self.dimension_order.value.index("Y")],
            SizeC=attributes.get("SizeC")
            or (
                self.shape[self.dimension_order.value.index("C")]
                if "C" in self.dimension_order.value
                else None
            ),
            SizeZ=attributes.get("SizeZ")
            or (
                self.shape[self.dimension_order.value.index("Z")]
                if "Z" in self.dimension_order.value
                else None
            ),
            SizeT=attributes.get("SizeT")
            or (
                self.shape[self.dimension_order.value.index("T")]
                if "T" in self.dimension_order.value
                else None
            ),
            Type=attributes.get("Type") or self.dtype,
            PhysicalSizeX=attributes.get("PhysicalSizeX"),
            PhysicalSizeY=attributes.get("PhysicalSizeY"),
            PhysicalSizeZ=attributes.get("PhysicalSizeZ"),
            PhysicalSizeXUnit=attributes.get("PhysicalSizeXUnit"),
            PhysicalSizeYUnit=attributes.get("PhysicalSizeYUnit"),
            PhysicalSizeZUnit=attributes.get("PhysicalSizeZUnit"),
            Channel=channel_list,
        )


def convert_to_microns(value: float, unit: UnitsLength) -> float:
    """Converts values from a unit to microns.

    Args:
        value (float): Value to convert.
        unit (UnitsLength): Unit of `value`.

    Returns:
        float: The converted value.
    """
    match unit:
        case UnitsLength.nano:
            return value / 1_000
        case UnitsLength.micro:
            return value
        case UnitsLength.milli:
            return value * 1_000
        case UnitsLength.centi:
            return value * 10_000
        case UnitsLength.inches:
            return value * 25_400
        case _:
            _module_logger.warning(
                f"NotImplementedError: Unknown enum variant '{unit}' for conversion to "
                f"microns. Leaving as-is."
            )
            return value


register_plugin(
    format=Hdf5ImagePlugin.format,
    plugin=Hdf5ImagePlugin,
    extensions=Hdf5ImagePlugin.extensions,
    supports_read=True,
    supports_write=True,
)
