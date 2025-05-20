# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from datetime import datetime
import os
from pathlib import Path
from typing import Literal, Optional

import click
import numpy as np

from histalign.io.image import (
    DimensionOrder,
    get_appropriate_plugin_class,
    ImageFile,
    SUPPORTED_READ_FORMATS,
    SUPPORTED_WRITE_FORMATS,
    UnknownFileFormatError,
)
from histalign.io.image.metadata import OmeXmlChannel


@click.command(help="Inspect a file for information.")
@click.argument(
    "source",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--order",
    type=str,
    required=False,
    default="",
    callback=lambda _, __, value: value.upper(),
    help="Dimension order of 'SOURCE'.",
)
@click.option(
    "-s",
    "--system",
    type=click.Choice(["binary", "decimal"]),
    required=False,
    default="binary",
    help="System to use when computing sizes.",
)
def info(
    source: Path,
    order: str,
    system: Literal["binary", "decimal"],
) -> None:
    """Inspects `SOURCE` to dump information about its type, plugin, and properties.

    Args:
        source (Path): File to print info for.
        order (str): Order of the dimensions of 'SOURCE'.
        system (Literal["binary", "decimal"]): System to use when computing sizes.

    References:
        Byte-sizing systems: https://en.wikipedia.org/wiki/Byte#Multiple-byte_units
    """
    order: Optional[DimensionOrder] = DimensionOrder(order.upper()) if order else None

    string = _info_stat(source, system)
    string += _info_plugin(source)
    string += _info_file(source, order, system)

    click.echo(string)


def _info_stat(file_path: Path, system: Literal["binary", "decimal"]) -> str:
    stat = os.stat(file_path)
    return f"""\
{horizontal_line("File")}
File path:              {file_path.resolve()}
File name:              {file_path.name}
File size:              {convert_bytes_to_string(stat.st_size, system)}
File created:           {datetime.fromtimestamp(stat.st_ctime).strftime("%d-%m-%Y %H:%M:%S")}\
"""


def _info_plugin(file_path: Path) -> str:
    try:
        plugin = get_appropriate_plugin_class(file_path, mode="r")
    except UnknownFileFormatError:
        return f"""
{horizontal_line("Plugin")}
Format supported:       No\
"""

    supports_read = plugin.format in SUPPORTED_READ_FORMATS
    supports_write = plugin.format in SUPPORTED_WRITE_FORMATS
    supports_multi_series = plugin.supports_multi_series
    supports_series = plugin.supports_series

    return f"""
{horizontal_line("Plugin")}
Format supported:       Yes
Plugin name:            {plugin.__qualname__}
Plugin format:          {plugin.format}
Plugin extensions:      {", ".join(plugin.extensions)}
Supports read:          {"Yes" if supports_read else "No"}
Supports write:         {"Yes" if supports_write else "No"}
Supports multi-series:  {"Yes" if supports_multi_series else "No"}
Supports series:        {"Yes" if supports_series else "No"}\
"""


def _info_file(
    file_path: Path,
    order: Optional[DimensionOrder],
    system: Literal["binary", "decimal"],
) -> str:
    try:
        plugin = get_appropriate_plugin_class(file_path, mode="r")
    except UnknownFileFormatError:
        return ""

    supports_multi_series = plugin.supports_multi_series

    file = plugin(
        file_path, mode="r", dimension_order=order, allow_no_dimension_order=True
    )
    string = f"""
{horizontal_line("Properties")}
Dimension order:        {file.dimension_order.value if file.dimension_order is not None else "Unknown"}
Series count:           {file.series_count if supports_multi_series else 1}\
"""
    for series_index in range(file.series_count if supports_multi_series else 1):
        string += _info_series(file, series_index, system)
        if supports_multi_series and file.has_another_series:
            file.seek_next_series()

    return string


def _info_series(
    file: ImageFile, series_index: int, system: Literal["binary", "decimal"]
) -> str:
    string = f"""
{horizontal_line(f"Series {series_index + 1}")}
Shape:                  {file.shape}
Dtype:                  {np.dtype(file.dtype).name}
Size:                   {convert_bytes_to_string(np.prod(file.shape) * np.dtype(file.dtype).itemsize, system=system)}\
"""

    # TODO: Make sure plugins can parse metadata without a dimension order.
    try:
        metadata = file.metadata
    except AttributeError:
        string += f"""

Remaining series metadata not parsed. Most likely due to unknown dimension order. Try passing it as an option.
"""
        return string

    string += f"""

Dimension order:        {metadata.DimensionOrder}
SizeX:                  {metadata.SizeX}
SizeY:                  {metadata.SizeY}
SizeC:                  {metadata.SizeC}
SizeZ:                  {metadata.SizeZ}
SizeT:                  {metadata.SizeT}
Type:                   {metadata.Type}
PhysicalSizeX:          {metadata.PhysicalSizeX}
PhysicalSizeY:          {metadata.PhysicalSizeY}
PhysicalSizeZ:          {metadata.PhysicalSizeZ}
PhysicalSizeXUnit:      {metadata.PhysicalSizeXUnit}
PhysicalSizeYUnit:      {metadata.PhysicalSizeYUnit}
PhysicalSizeZUnit:      {metadata.PhysicalSizeZUnit}
"""

    channel_string = ""
    if metadata.Channel:
        channel_string = f"\nChannels:               "
        for channel in metadata.Channel:
            channel_string += _info_channel(channel)

    return string + channel_string


def _info_channel(metadata: OmeXmlChannel) -> str:
    return f"""
Name:                   {metadata.Name}
EmissionWavelength:     {metadata.EmissionWavelength}
EmissionWavelengthUnit: {metadata.EmissionWavelengthUnit}
Color:                  {metadata.Color}\
"""


def horizontal_line(name: str) -> str:
    try:
        terminal_width = os.get_terminal_size()[0]
    except OSError:
        terminal_width = 20
    left_padding, remainder = divmod(terminal_width - 2 - len(name), 2)
    right_padding = left_padding + remainder

    return f"{'-' * left_padding} {name} {'-' * right_padding}"


def convert_bytes_to_string(
    number_of_bytes: int,
    system: Literal["binary", "decimal"],
) -> str:
    if system not in ["binary", "decimal"]:
        raise ValueError("System should be one of decimal or binary.")

    base = 1000 if system == "decimal" else 1024

    K = base
    M = K * base
    G = M * base

    running_bytes_count = number_of_bytes
    number_of_g, running_bytes_count = divmod(running_bytes_count, G)
    number_of_m, running_bytes_count = divmod(running_bytes_count, M)
    number_of_k, running_bytes_count = divmod(running_bytes_count, K)

    string = ""
    filler = "i" if system == "binary" else ""
    if number_of_g:
        string += f"{number_of_g}G{filler}B "
    if number_of_m:
        string += f"{number_of_m}M{filler}B "
    if number_of_k:
        string += f"{number_of_k}K{filler}B "
    if running_bytes_count:
        string += f"{running_bytes_count}B"
    string = string.strip()

    return string
