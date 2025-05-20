# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from fractions import Fraction
import logging
from pathlib import Path
import re
from typing import Optional

import numpy as np
import tifffile
from tifffile import RESUNIT

from histalign.io import DimensionOrder
from histalign.io.image import ImageFile, register_plugin
from histalign.io.image.metadata import OmeXml, OmeXmlChannel, UnitsLength

_module_logger = logging.getLogger(__name__)


class TiffImagePlugin(ImageFile):
    format: str = "TIFF"
    extensions: tuple[str, ...] = (".tif", ".tiff")

    # Although the TIFF standard might allow for multiple series in the same file,
    # there aren't any way I know of to memmap writing such a file. Hence, only allow
    # a single series.
    series_support = 1

    @property
    def shape(self) -> tuple[int, ...]:
        return self.file_handle.shape

    @property
    def dtype(self) -> np.dtype:
        return self.file_handle.dtype

    def _open(
        self, file_path: Path, mode: str, metadata: Optional[OmeXml] = None, **kwargs
    ) -> None:
        if mode == "r":
            self.file_handle = tifffile.TiffFile(file_path, mode="r").asarray(
                out="memmap"
            )
        else:
            if (shape := kwargs.get("shape")) is None:
                raise ValueError("No shape provided for new file in writing mode.")
            if (dtype := kwargs.get("dtype")) is None:
                raise ValueError("No dtype provided for new file in writing mode.")

            if metadata is not None:
                # TODO: Fix channel names in metadata. `tifffile` seems to name all the
                #       channels after the first channel name.
                metadata = metadata.model_dump()
                # When writing with `ome=True`, `tifffile` doesn't like our
                # "DimensionOrder". We pass it as "axes" instead.
                metadata["axes"] = metadata["DimensionOrder"]
                metadata.pop("DimensionOrder")

            self.file_handle = tifffile.memmap(
                file_path,
                shape=shape,
                dtype=dtype,
                # Hard-coded as True in case the file is larger than 4GB
                bigtiff=True,
                # Required to have ImageJ read the metadata correctly
                ome=True,
                metadata=metadata,
            )

        # Kept for metadata parsing
        self._file_handle = tifffile.TiffFile(file_path)

    def load(self) -> np.ndarray:
        return self.file_handle[:]

    def try_get_dimension_order(self) -> Optional[DimensionOrder]:
        return convert_tiff_axes_to_dimension_order(self._file_handle.series[0].axes)

    def read_image(self, index: tuple[slice, ...]) -> np.ndarray:
        return self.file_handle[index]

    def write_image(self, image: np.ndarray, index: tuple[slice, ...]) -> None:
        self.file_handle[index] = image

    def _extract_metadata(self) -> OmeXml:
        # As far as I'm aware, channel metadata cannot be stored in TIFF tags
        c_size = (
            self.shape[self.dimension_order.value.index("C")]
            if "C" in self.dimension_order.value
            else 0
        )
        channel_list = [OmeXmlChannel(Name=f"channel{i + 1}") for i in range(c_size)]

        return OmeXml(
            DimensionOrder=self.dimension_order,
            SizeX=self.shape[self.dimension_order.value.index("X")],
            SizeY=self.shape[self.dimension_order.value.index("Y")],
            SizeC=(
                self.shape[self.dimension_order.value.index("C")]
                if "C" in self.dimension_order.value
                else None
            ),
            SizeZ=(
                self.shape[self.dimension_order.value.index("Z")]
                if "Z" in self.dimension_order.value
                else None
            ),
            SizeT=(
                self.shape[self.dimension_order.value.index("T")]
                if "T" in self.dimension_order.value
                else None
            ),
            Type=self.dtype,
            # TIFF stores sizes in unit/pixel, hence invert the fraction
            PhysicalSizeX=float(
                Fraction(*self._file_handle.pages[0].tags["XResolution"].value[::-1])
            ),
            PhysicalSizeY=float(
                Fraction(*self._file_handle.pages[0].tags["YResolution"].value[::-1])
            ),
            # TIFF standard doesn't seem to have a way to store a tag for Z resolution.
            # Only ImageJ TIFFs seem to store it as far as I know.
            # See: https://forum.image.sc/t/saving-tif-with-voxel-size-in-python/72299/3
            PhysicalSizeZ=(
                self._file_handle.imagej_metadata.get("spacing")
                if self._file_handle.imagej_metadata
                else None
            ),
            PhysicalSizeXUnit=convert_tiff_resolution_unit_to_ome(
                self._file_handle.pages[0].tags["ResolutionUnit"].value
            ),
            PhysicalSizeYUnit=convert_tiff_resolution_unit_to_ome(
                self._file_handle.pages[0].tags["ResolutionUnit"].value
            ),
            # See "PhysicalSizeZ"
            PhysicalSizeZUnit=(
                convert_imagej_tiff_z_unit_to_ome(
                    self._file_handle.imagej_metadata.get("unit")
                )
                if self._file_handle.imagej_metadata
                else None
            ),
            Channel=channel_list,
        )


def convert_tiff_resolution_unit_to_ome(value: RESUNIT) -> UnitsLength:
    """Converts a TIFF tag ResolutionUnit value to a UnitsLength variant.

    Note that the TIFF standard seems to only support three values: NONE, INCH, and
    CENTIMETER. However, `tifffile` has more variants, and this function tries to
    support them as well.

    Args:
        value (RESUNIT): Value of the RESUNIT variant to convert.

    Returns:
        The variant `value` corresponds to.

    References:
        TIFF tags specs: https://web.archive.org/web/20200809235709/https://www.awaresystems.be/imaging/tiff/tifftags/resolutionunit.html
        `tifffile` enum: https://github.com/cgohlke/tifffile/blob/8a25a0d4738390af0a1f693705f29875d88fc320/tifffile/tifffile.py#L17285
    """
    match value:
        case RESUNIT.NONE:
            converted = UnitsLength.micro
            _module_logger.warning(
                f"Encountered OME-incompatible, TIFF '{value}' resolution unit. "
                f"Defaulting to '{converted}'."
            )
        case RESUNIT.INCH:
            converted = UnitsLength.inches
        case RESUNIT.CENTIMETER:
            converted = UnitsLength.centi
        case RESUNIT.MILLIMETER:
            converted = UnitsLength.milli
        case RESUNIT.MICROMETER:
            converted = UnitsLength.micro
        case _:
            converted = UnitsLength.micro
            _module_logger.warning(
                f"Unknown RESUNIT variant '{value}'. " f"Defaulting to '{converted}'."
            )

    return converted


def convert_imagej_tiff_z_unit_to_ome(value: str) -> UnitsLength:
    """Converts ImageJ "spacing" unit to UnitsLength.

    Args:
        value (str): String representation of the unit.

    Returns:
        The UnitsLength variant corresponding to `value`.
    """
    # I'm not aware of any documentation of the possible values of the spacing unit (it
    # might even be user-defined), hence try to support the most common ones.
    match value:
        case "um":
            return UnitsLength.micro
        case "in":
            return UnitsLength.inches
        case _:
            _module_logger.warning(
                f"Encountered unknown Z resolution unit '{value}' while parsing TIFF "
                f"metadata. Assuming µm."
            )
            return UnitsLength.micro


def convert_tiff_axes_to_dimension_order(axes: str) -> Optional[DimensionOrder]:
    """Converts a `TiffPageSeries.axes` to a `DimensionOrder`.

    Args:
        axes (str): String representation of the dimensions.

    Returns:
        The converted dimension order or `None` if the conversion failed.

    References:
        `tifffile`'s conventions on naming axes discussion: https://github.com/cgohlke/tifffile/issues/293
        `tifffile`'s axes legend: https://github.com/cgohlke/tifffile/blob/78b57cf84bd92528ba8877ea4972769bb4d43600/tifffile/tifffile.py#L18594-L18618
    """
    # Check axes only contains supported dimensions
    if not re.fullmatch(r"^[XYZCS]+$", axes).group() == axes:
        return None

    # We cast S to C, hence ensure both aren't present
    if "C" in axes and "S" in axes:
        return None
    axes = re.sub("S", "C", axes)

    return DimensionOrder(axes)


register_plugin(
    format=TiffImagePlugin.format,
    plugin=TiffImagePlugin,
    extensions=TiffImagePlugin.extensions,
    supports_read=True,
    supports_write=True,
)
