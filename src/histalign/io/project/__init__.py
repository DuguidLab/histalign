# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from collections.abc import Iterable
import logging
from pathlib import Path
import time
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
    UnknownFileFormatError,
)
from histalign.io.image.metadata import OmeXml
from histalign.io.project.projections import (
    get_appropriate_projection_function,
    ProjectionKind,
)

_module_logger = logging.getLogger(__name__)


@click.command(help="Project Z-stacks to a single image.")
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
    "--type",
    "kind",
    type=click.Choice(ProjectionKind.__args__),
    required=True,
    callback=lambda _, __, value: value.lower(),
    help="Type of projection to perform.",
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
def project(
    source: Path,
    destination: Optional[Path],
    kind: ProjectionKind,
    extension: str,
    order: str,
    force: bool,
) -> None:
    if source.is_dir() and not extension:
        raise ValueError(
            "Please provide a source extension when attempting to project a directory."
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

    # Default to HDF5 when projecting a format we can't write to
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
        _module_logger.info(f"Starting projection of '{source_path}'.")
        _project(
            source_path,
            destination,
            extension,
            destination_extension,
            order,
            kind,
            force,
        )


def _project(
    source_path: Path,
    destination_path: Path,
    source_extension: str,
    destination_extension: str,
    source_order: Optional[DimensionOrder],
    kind: ProjectionKind,
    force: bool,
) -> None:
    source_plugin_class = get_appropriate_plugin_class(source_path, mode="r")
    source_file = source_plugin_class(
        source_path, mode="r", dimension_order=source_order
    )
    source_order = source_file.dimension_order

    if "Z" not in source_order.value:
        _module_logger.info(
            f"'{source_path.name}' does not have a Z dimension. Skipping projection."
        )
        return

    destination_path = destination_path / source_path.name.replace(
        source_extension, f"_{kind.lower()}{destination_extension}"
    )
    if destination_path.exists() and not force:
        _module_logger.debug(
            f"Skipping '{destination_path}' destination path as it already exists and "
            f"'force' is not on."
        )
        return

    updated_metadata = _update_metadata(source_file.metadata.model_copy(deep=True))

    destination_order = DimensionOrder(source_order.value.replace("Z", ""))
    destination_plugin_class = get_appropriate_plugin_class(destination_path, mode="w")
    destination_file = destination_plugin_class(
        destination_path,
        mode="w",
        dimension_order=destination_order,
        shape=remove_extra_dimensions(
            source_file.shape, source_order, destination_order
        ),
        dtype=source_file.dtype,
        metadata=updated_metadata,
    )

    for series_index in range(
        source_file.series_count if isinstance(source_file, MultiSeriesImageFile) else 1
    ):
        _module_logger.info(f"Projecting series {series_index + 1}.")
        _project_series(source_file, destination_file, destination_order, kind)

        if source_file.supports_multi_series and source_file.has_another_series:
            source_file.seek_next_series()

            destination_file.seek_next_series(
                shape=source_file.shape,
                dtype=source_file.dtype,
                metadata=source_file.metadata,
            )


def _project_series(
    source_file: ImageFile,
    destination_file: ImageFile,
    destination_order: DimensionOrder,
    kind: ProjectionKind,
) -> None:
    projection_count = np.prod(
        np.array(source_file.shape)[
            np.logical_not(
                np.isin(
                    np.array(list(source_file.dimension_order.value)), ["X", "Y", "Z"]
                )
            )
        ]
    )
    projection_index = 0

    insertion_index = None
    indices = []
    for index in generate_indices(
        source_file.dimension_order,
        shape=source_file.shape,
        iteration_order=DimensionOrder(
            source_file.dimension_order.value.replace("Z", "") + "Z"
        ),
    ):
        if insertion_index is None:
            insertion_index = remove_extra_dimensions(
                index, source_file.dimension_order, destination_order
            )

        z_index = index[source_file.dimension_order.value.index("Z")].start
        if z_index == 0 and len(indices) > 0:
            projection_index += 1
            _module_logger.info(f"Projection {projection_index}/{projection_count}.")
            _project_and_write(
                source_file, destination_file, indices, insertion_index, kind
            )
            indices = [index]
            insertion_index = remove_extra_dimensions(
                index, source_file.dimension_order, destination_order
            )
        else:
            indices.append(index)
    else:
        _module_logger.info(f"Projection {projection_index + 1}/{projection_count}.")
        _project_and_write(
            source_file, destination_file, indices, insertion_index, kind
        )


def _project_and_write(
    source_file: ImageFile,
    destination_file: ImageFile,
    iteration_indices: Iterable[tuple[slice, ...]],
    insertion_index: tuple[slice, ...],
    kind: ProjectionKind,
) -> None:
    start_time = time.perf_counter()
    projection = get_appropriate_projection_function(kind)(
        source_file, iteration_indices
    )
    _module_logger.debug(
        f"Performed '{kind}' projection in "
        f"{convert_seconds_to_string(time.perf_counter() - start_time)}."
    )

    destination_file.write_image(projection, insertion_index)


def _update_metadata(metadata: OmeXml) -> OmeXml:
    metadata.SizeZ = 1

    dimension_order = metadata.DimensionOrder
    dimension_order = dimension_order.replace("Z", "")
    metadata.DimensionOrder = dimension_order

    return metadata


def convert_seconds_to_string(seconds: float) -> str:
    hours, remaining_seconds = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remaining_seconds, 60)

    return f"{hours:.0f}h {minutes:.0f}m {remaining_seconds:.2f}s"
