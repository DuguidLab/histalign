# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path
from typing import Optional

import click
import numpy as np

from histalign.io.convert import extract_file_extension
from histalign.io.image import (
    DimensionOrder,
    EXTENSIONS,
    get_appropriate_plugin_class,
    ImageFile,
    SUPPORTED_WRITE_FORMATS,
    UnknownFileFormatError,
)
from histalign.io.image.metadata import OmeXml
from histalign.io.transform.transforms import (
    get_appropriate_transform_function,
    Transform,
)

_module_logger = logging.getLogger(__name__)


@click.command(help="Apply a transform on each image.")
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
    "-t",
    "--transform",
    type=click.Choice(Transform.__args__),
    required=True,
    callback=lambda _, __, value: value.lower(),
    help="Type of transform to perform.",
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
@click.option(
    "--downscaling-factor",
    type=int,
    required=False,
    default=4,
    help=(
        "Factor to use when downscaling the image. This is ignored if 'TRANSFORM' is "
        "not downscaling."
    ),
)
@click.option(
    "--downscaling-order",
    type=int,
    required=False,
    default=3,
    help=(
        "Order to use when downscaling the image. This is ignored if 'TRANSFORM' is "
        "not downscaling. 0: Nearest neighbour. 1: Bilinear. 2: Biquadric. 3: Bicubic. "
        "4: Biquartic. 5: Biquintic."
    ),
)
def transform(
    source: Path,
    destination: Optional[Path],
    transform: Transform,
    extension: str,
    order: str,
    force: bool,
    **kwargs,
) -> None:
    if source.is_dir() and not extension:
        raise ValueError(
            "Please provide a source extension when attempting to transform a "
            "directory."
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

    order = DimensionOrder(order.upper()) if order else None

    # Default to HDF5 when transforming a format we can't write to
    if (format := EXTENSIONS[extension]) not in SUPPORTED_WRITE_FORMATS:
        _module_logger.warning(
            f"'{format}' does not support writing. Defaulting to HDF5 for output format."
        )
        destination_extension = ".h5"
    else:
        destination_extension = extension

    source_paths = (
        [source] if source.is_file() else list(source.glob(f"[!.]*{extension}"))
    )
    for source_path in source_paths:
        _module_logger.info(f"Starting transformation of '{source_path}'.")
        _transform(
            source_path,
            destination,
            extension,
            destination_extension,
            order,
            transform,
            force,
            **kwargs,
        )


def _transform(
    source_path: Path,
    destination_path: Path,
    source_extension: str,
    destination_extension: str,
    source_order: Optional[DimensionOrder],
    transform: Transform,
    force: bool,
    **kwargs,
) -> None:
    source_plugin_class = get_appropriate_plugin_class(source_path, mode="r")
    source_file = source_plugin_class(
        source_path, mode="r", dimension_order=source_order
    )

    destination_path = destination_path / source_path.name.replace(
        source_extension, f"_{transform.lower()}{destination_extension}"
    )
    if destination_path.exists() and not force:
        _module_logger.debug(
            f"Skipping '{destination_path}' destination path as it already exists and "
            f"'force' is not on."
        )
        return

    # Delegate the opening of the file to when writing the first image since we don't
    # know the final shape. If we're downscaling, the shape needs to be determined from
    # the first transformed image of each series.
    destination_file = [destination_path]
    seek_first = False
    for series_index in range(
        source_file.series_count if source_file.supports_multi_series else 1
    ):
        _module_logger.info(f"Transforming series {series_index + 1}.")
        _transform_series(
            source_file, destination_file, transform, seek_first, **kwargs
        )

        if source_file.supports_multi_series and source_file.has_another_series:
            source_file.seek_next_series()
            seek_first = True  # Delegate seeking next series to _transform_series


def _transform_series(
    source_file: ImageFile,
    destination_file: list[Path | ImageFile],
    transform: Transform,
    seek_first: bool = False,
    **kwargs,
) -> None:
    transform_count = np.prod(
        np.array(source_file.shape)[
            np.logical_not(
                np.isin(np.array(list(source_file.dimension_order.value)), ["X", "Y"])
            )
        ]
    )
    transform_index = 0

    transform_function = get_appropriate_transform_function(transform)
    for image in source_file.iterate_images(source_file.dimension_order):
        _module_logger.info(f"Transform {transform_index}/{transform_count}.")

        transformed_image = transform_function(image, **kwargs)

        if isinstance(destination_file[0], Path) or seek_first:
            order = source_file.dimension_order

            x_position = order.value.index("X")
            y_position = order.value.index("Y")

            shape = transformed_image.shape
            new_x = shape[x_position]
            new_y = shape[y_position]

            transformed_shape = list(source_file.shape)
            transformed_shape[x_position] = new_x
            transformed_shape[y_position] = new_y

            updated_metadata = update_metadata(source_file.metadata, transformed_shape)

            if seek_first:
                # Writing the first image of a new series
                destination_file[0].seek_next_series(
                    shape=transformed_shape,
                    dtype=source_file.dtype,
                    metadata=updated_metadata,
                )
                seek_first = False
            else:
                destination_plugin_class = get_appropriate_plugin_class(
                    destination_file[0], mode="w"
                )
                destination_file[0] = destination_plugin_class(
                    destination_file[0],
                    mode="w",
                    dimension_order=order,
                    shape=transformed_shape,
                    dtype=source_file.dtype,
                    metadata=updated_metadata,
                )

        destination_file[0].write_image(transformed_image, source_file.index)


def update_metadata(metadata: OmeXml, transformed_shape: list[int]) -> OmeXml:
    updated_metadata = metadata.model_copy(deep=True)

    x_position = updated_metadata.DimensionOrder.index("X")
    y_position = updated_metadata.DimensionOrder.index("Y")

    new_x = transformed_shape[x_position]
    new_y = transformed_shape[y_position]

    new_x_scaling = updated_metadata.PhysicalSizeX * (updated_metadata.SizeX / new_x)
    new_y_scaling = updated_metadata.PhysicalSizeY * (updated_metadata.SizeY / new_y)

    updated_metadata.SizeX = transformed_shape[x_position]
    updated_metadata.SizeY = transformed_shape[y_position]

    updated_metadata.PhysicalSizeX = new_x_scaling
    updated_metadata.PhysicalSizeY = new_y_scaling

    return updated_metadata
