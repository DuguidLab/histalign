# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from collections.abc import Sequence
import logging
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

import numpy as np
from readlif.reader import LifFile, LifImage
from readlif.utilities import get_xml

from histalign.io.image import (
    DimensionOrder,
    generate_indices,
    ModeNotSupportedError,
    MultiSeriesImageFile,
    register_plugin,
)
from histalign.io.image.metadata import ChannelColor, OmeXml, OmeXmlChannel, UnitsLength

_module_logger = logging.getLogger(__name__)


class LifImagePlugin(MultiSeriesImageFile):
    format: str = "LIF"
    extensions: tuple[str, ...] = (".lif",)

    series_support = 2

    @property
    def shape(self) -> tuple[int, ...]:
        current_image = self.file_handle.get_image(self.series_index)

        shape = (
            current_image.dims.z,
            current_image.channels,
            current_image.dims.y,
            current_image.dims.x,
        )
        for i in range(len(shape)):
            if shape[i] == 1:
                continue
            return shape[i:]

    @property
    def dtype(self) -> np.dtype:
        bit_depths = self._current_image.bit_depth
        if len(set(bit_depths)) != 1:
            raise ValueError(
                "Unsupported varying bit-depth for different channels of the "
                "same series."
            )

        match bit_depths[0]:
            case 8:
                return np.uint8
            case 16:
                return np.uint16
            case 32:
                return np.uint32
            case _:
                raise ValueError(f"Unknown bit-depth for LIF file ({bit_depth}).")

    @property
    def series_count(self) -> int:
        return self.file_handle.num_images

    @property
    def _current_image(self) -> LifImage:
        return self.file_handle.get_image(self.series_index)

    def _open(
        self, file_path: Path, mode: str, metadata: Optional[OmeXml] = None, **kwargs
    ) -> None:
        # Plugin does not support writing hence metadata parameter is ignored
        if mode != "r":
            raise ModeNotSupportedError(self.format, mode)

        self.file_handle = LifFile(file_path)

        tree = ElementTree.fromstring(get_xml(str(file_path))[1])
        self._all_images_metadata = _parse_metadata(tree)

    def load(self) -> np.ndarray:
        whole_series = np.zeros(shape=self.shape)
        for index in generate_indices(
            self.dimension_order, self.shape, self.dimension_order
        ):
            whole_series[index] = self.read_image(index)

        return whole_series

    def try_get_dimension_order(self) -> Optional[DimensionOrder]:
        return self._all_images_metadata[self.series_index].DimensionOrder

    def read_image(self, index: tuple[slice, ...]) -> np.ndarray:
        frame = np.array(
            self._current_image.get_frame(
                t=0,
                z=index[-4].start if len(index) > 3 else 0,
                c=index[-3].start if len(index) > 2 else 0,
            )
        )
        return frame[(np.newaxis,) * (len(index) - 2)]

    def write_image(self, image: np.ndarray, index: tuple[slice, ...]) -> None:
        raise ModeNotSupportedError(self.format, "w")

    def create_series(
        self, shape: Sequence[int], dtype: np.dtype, metadata: Optional[OmeXml] = None
    ) -> None:
        raise ModeNotSupportedError(self.format, "w")

    def _extract_metadata(self) -> OmeXml:
        # Metadata is parsed in its entirety when opening the file. No parsing needed
        # here.
        return self._all_images_metadata[self.series_index]


def _parse_metadata(tree: ElementTree, parsed_tree: list | None = None) -> list[OmeXml]:
    # This function is heavily inspired by `readlif.reader.LifImage`'s parsing method
    # with appropriate changes for additional metadata where necessary.
    if parsed_tree is None:
        parsed_tree = []

    children = tree.findall("./Children/Element")
    if len(children) < 1:
        children = tree.findall("./Element")
    for item in children:
        has_children = len(item.findall("./Children/Element/Data")) > 0
        is_image = len(item.findall("./Data/Image")) > 0

        if is_image:
            # Known dimension IDs are:
            # 1: X
            # 2: Y
            # 3: Z
            # 4: T
            # Channels are not considered a dimension in LIF metadata.

            # Dimensions information
            dimensions = item.findall("./Data/Image/ImageDescription/Dimensions/")

            dimensions_dictionary = {
                int(dimension.attrib["DimID"]): int(
                    dimension.attrib["NumberOfElements"]
                )
                for dimension in dimensions
            }

            # Scale information
            scale_dictionary = {}
            for dimension in dimensions:
                dimension_id = int(dimension.attrib["DimID"])

                try:
                    length = float(dimension.attrib["Length"])

                    if dimension_id < 4:
                        # Pixel per micrometer
                        value = (int(dimensions_dictionary[dimension_id]) - 1) / (
                            float(length) * 10**6
                        )  # XML is in meters
                        # Micrometer per pixel
                        scale_dictionary[dimension_id] = 1 / value
                except (AttributeError, ZeroDivisionError):
                    scale_dictionary[dimension_id] = None

            # Channel information
            channels = item.findall(
                "./Data/Image/ImageDescription/Channels/ChannelDescription"
            )
            channel_count = len(channels)

            bit_depths = tuple(
                [int(channel.attrib["Resolution"]) for channel in channels]
            )
            if len(bit_depths) < 1:
                _module_logger.warning(
                    "Could not find channel bit depth while parsing LIF metadata. "
                    "Assuming 32-bit."
                )
                bit_depths = (32,)
            bit_depth = bit_depths[0]
            if len(set(bit_depths)) > 1:
                _module_logger.warning(
                    "Encountered varying bit depth for different channels of the same "
                    "LIF image while parsing metadata. Defaulting to largest one. Note "
                    "this might not lead to a valid conversion."
                )
                bit_depth = max(bit_depths)

            channel_list = []
            for index, channel in enumerate(
                item.findall(
                    "./Data/Image/Attachment/LDM_Block_Widefield_Sequential/"
                    "LDM_Block_Sequential_List/ATLCameraSettingDefinition/"
                    "WideFieldChannelConfigurator/WideFieldChannelInfo"
                )
            ):
                try:
                    channel_name = channel.attrib["UserDefName"]
                except AttributeError:
                    channel_name = f"channel{index}"

                channel_info = channel.findall(
                    "./IndividualCameraInfoArray/IndividualCameraInfo"
                )
                if len(channel_info) > 1:
                    _module_logger.warning(
                        "Encountered multiple channel info element while parsing LIF "
                        "metadata. Discarding all but the first one."
                    )
                if len(channel_info) < 1:
                    channel_lut = None
                    channel_emission_wavelength = None
                else:
                    channel_lut = channel_info[0].attrib.get("LUT")
                    try:
                        channel_emission_wavelength = int(
                            channel_info[0].attrib["EmissionWavelength"]
                        )
                    except (AttributeError, TypeError):
                        channel_emission_wavelength = None

                channel_list.append(
                    {
                        "Name": channel_name,
                        "EmissionWavelength": channel_emission_wavelength,
                        # Unit not in metadata, assuming nanometers
                        "EmissionWavelengthUnit": "nm",
                        "Color": convert_lut_to_color(channel_lut),
                    }
                )

            channels_xml = []
            for channel in channel_list:
                channels_xml.append(OmeXmlChannel(**channel))

            # Determines how many dimensions are included in the current series. This
            # is used to determine how far from the end of the "ZCYX" list of dimensions
            # to start from when figuring out the correct DimensionOrder. See above for
            # a list of dimension IDs and their corresponding "ZCYX" values.
            dimension_order_back_index = 2
            if channel_count:
                dimension_order_back_index = 3
            if 3 in dimensions_dictionary.keys():
                dimension_order_back_index = 4

            ome_xml = OmeXml(
                DimensionOrder=DimensionOrder("ZCYX"[-dimension_order_back_index:]),
                SizeX=dimensions_dictionary.get(1, 1),
                SizeY=dimensions_dictionary.get(2, 1),
                SizeC=channel_count or 1,
                SizeZ=dimensions_dictionary.get(3),
                SizeT=dimensions_dictionary.get(4),
                Type=f"uint{bit_depth}",
                PhysicalSizeX=scale_dictionary.get(1),
                PhysicalSizeY=scale_dictionary.get(2),
                # TODO: Ensure negative values are valid and not just due to corruption
                PhysicalSizeZ=abs(scale_dictionary.get(3, 1)),
                PhysicalSizeXUnit=UnitsLength.micro,
                PhysicalSizeYUnit=UnitsLength.micro,
                PhysicalSizeZUnit=UnitsLength.micro,
                Channel=channels_xml,
            )
            parsed_tree.append(ome_xml)

        if has_children:
            _parse_metadata(item, parsed_tree)

    return parsed_tree


def convert_lut_to_color(lut: str) -> ChannelColor:
    # Support most common colours, default to white otherwise
    match lut:
        case "Red":
            return ChannelColor(red=255, green=0, blue=0)
        case "Green":
            return ChannelColor(red=0, green=255, blue=0)
        case "Blue":
            return ChannelColor(red=0, green=0, blue=255)
        case "Yellow":
            return ChannelColor(red=255, green=255, blue=0)
        case "Cyan":
            return ChannelColor(red=0, green=255, blue=255)
        case "Magenta":
            return ChannelColor(red=255, green=0, blue=255)
        case _:
            return ChannelColor()


register_plugin(
    LifImagePlugin.format,
    LifImagePlugin,
    LifImagePlugin.extensions,
    supports_read=True,
    supports_write=False,
)
