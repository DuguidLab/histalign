# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from collections.abc import Iterable
import logging
from pathlib import Path
from typing import Optional

import click
import numpy as np

from histalign.io.convert import extract_file_extension
from histalign.io.image import (
    DimensionOrder,
    EXTENSIONS,
    generate_indices,
    get_appropriate_plugin_class,
    ImageFile,
    MultiSeriesImageFile,
    remove_extra_dimensions,
    SUPPORTED_WRITE_FORMATS,
    translate_between_orders,
    UnknownFileFormatError,
)

VALID_SPLIT_DIMENSIONS = ["C", "Z"]

_module_logger = logging.getLogger(__name__)


@click.command(help="Split files along a dimension.")
@click.argument(
    "source",
    type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path),
    required=True,
)
@click.option(
    "-d",
    "--destination",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=False,
    help=(
        "Directory to output converted files in. If not provided, this defaults to "
        "'SOURCE' if it is a file or its parent otherwise."
    ),
)
@click.option(
    "-o",
    "--on",
    type=click.Choice(VALID_SPLIT_DIMENSIONS, case_sensitive=False),
    required=True,
    callback=lambda _, __, value: value.upper(),
    help=(
        "Dimension to split on. Use C to split on channels. Use Z to split on Z "
        "indices."
    ),
)
@click.option(
    "-e",
    "--extension",
    type=str,
    required=False,
    default="",
    callback=lambda _, __, value: value.lower(),
    help=(
        "Extension to use when globbing 'SOURCE' if it is a directory. "
        "If 'SOURCE' is a file, this is ignored."
    ),
)
@click.option(
    "-o",
    "--order",
    type=str,
    required=False,
    default="",
    callback=lambda _, __, value: value.upper(),
    help="Dimension order of the 'SOURCE'.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Whether to overwrite destination files if they already exist.",
)
def split(
    source: Path,
    destination: Optional[Path],
    on: str,
    extension: str,
    order: str,
    force: bool,
) -> None:
    if source.is_dir() and not extension:
        raise ValueError(
            "Please provide a source extension when attempting to split a directory."
        )

    if destination is None:
        destination = source.parent if source.is_file() else source
    else:
        if destination.is_file():
            raise ValueError("Destination path should be a directory.")

    if not extension:
        try:
            extension = extract_file_extension(source, EXTENSIONS.keys())
        except ValueError:
            raise UnknownFileFormatError("".join(source.suffixes))

    if not extension.startswith("."):
        extension = "." + extension

    # Validate order
    order = DimensionOrder(order) if order else None

    # Default to HDF5 when splitting a format we can't write to
    if (format := EXTENSIONS[extension]) not in SUPPORTED_WRITE_FORMATS:
        _module_logger.warning(
            f"'{format}' does not support writing. "
            f"Defaulting to HDF5 for output format."
        )
        destination_extension = ".h5"
    else:
        destination_extension = extension
    source_paths = (
        [source] if source.is_file() else list(source.glob(f"[!.]*{extension}"))
    )
    for source_path in source_paths:
        _module_logger.info(f"Starting split of '{source_path}'.")
        _split(
            source_path,
            destination,
            extension,
            destination_extension,
            order,
            on,
            force,
        )


def _split(
    source_path: Path,
    destination_path: Path,
    source_extension: str,
    destination_extension: str,
    source_order: Optional[DimensionOrder],
    on: str,
    force: bool,
) -> None:
    source_plugin_class = get_appropriate_plugin_class(source_path, mode="r")
    source_file = source_plugin_class(
        source_path, mode="r", dimension_order=source_order
    )
    source_order = source_file.dimension_order

    if on.upper() not in source_order.value:
        _module_logger.info(
            f"'{source_path.name}' ('{source_order.value}') does not have the "
            f"requested '{on}' dimension. Skipping split."
        )

    for series_index in range(
        source_file.series_count if isinstance(source_file, MultiSeriesImageFile) else 1
    ):
        _module_logger.info(f"Splitting {series_index + 1} of '{source_path.name}'.")
        _split_series(
            source_file,
            source_path,
            destination_path,
            source_extension,
            destination_extension,
            on,
            force,
        )

        if source_file.supports_multi_series and source_file.has_another_series:
            source_file.seek_next_series()

            destination_file.seek_next_series(
                shape=source_file.shape,
                dtype=source_file.dtype,
                metadata=source_file.metadata,
            )


def _split_series(
    source_file: ImageFile,
    source_path: Path,
    destination_path: Path,
    source_extension: str,
    destination_extension: str,
    on: str,
    force: bool,
) -> None:
    split_dimension_size = source_file.shape[
        source_file.dimension_order.value.index(on)
    ]
    if split_dimension_size < 2:
        _module_logger.info(
            f"'{source_path.name}' only has size 1 on the split axis. "
            f"Skipping split."
        )

    destination_order = DimensionOrder(
        source_file.dimension_order.value.replace(on, "")
    )

    all_indices = list(
        generate_indices(
            source_file.dimension_order,
            shape=source_file.shape,
            iteration_order=DimensionOrder(
                source_file.dimension_order.value.replace(on, "") + on
            ),
        )
    )
    for i in range(split_dimension_size):
        current_destination_path = destination_path / source_path.name.replace(
            source_extension, f"_{on}{i}{destination_extension}"
        )
        if current_destination_path.exists() and not force:
            _module_logger.debug(
                f"Skipping '{current_destination_path}' destination path as it already "
                f"exists and 'force' is not on."
            )
            continue

        updated_metadata = source_file.metadata.model_copy(deep=True)
        setattr(updated_metadata, f"Size{on}", 1)
        updated_metadata.DimensionOrder = destination_order
        if on == "C":
            updated_metadata.Channel = updated_metadata.Channel[i : i + 1]

        destination_plugin_class = get_appropriate_plugin_class(
            current_destination_path, mode="w"
        )
        destination_file = destination_plugin_class(
            current_destination_path,
            mode="w",
            dimension_order=destination_order,
            shape=remove_extra_dimensions(
                source_file.shape, source_file.dimension_order, destination_order
            ),
            dtype=source_file.dtype,
            metadata=updated_metadata,
        )

        _split_and_write(
            source_file,
            destination_file,
            all_indices[i::split_dimension_size],
        )

        destination_file.close()


def _split_and_write(
    source_file: ImageFile,
    destination_file: ImageFile,
    indices: Iterable[tuple[slice, ...]],
) -> None:
    for index in indices:
        image = source_file.read_image(index)

        translated_image_axis_order = translate_between_orders(
            list(range(len(image.shape))),
            source_file.dimension_order,
            destination_file.dimension_order,
        )
        # Ensure indices start at 0 and are sequential.
        translated_image_axis_order = tuple(
            sorted(translated_image_axis_order).index(i)
            for i in translated_image_axis_order
        )
        image = image.reshape(
            remove_extra_dimensions(
                image.shape,
                source_file.dimension_order,
                destination_file.dimension_order,
            )
        )
        image = np.transpose(image, translated_image_axis_order)

        destination_file.write_image(
            image,
            remove_extra_dimensions(
                index,
                source_file.dimension_order,
                destination_file.dimension_order,
            ),
        )
