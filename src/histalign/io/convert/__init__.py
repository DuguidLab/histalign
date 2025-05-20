# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from collections.abc import Iterable, Sequence
import logging
from pathlib import Path
from typing import Optional

import click
import numpy as np

from histalign.io.image import (
    DimensionOrder,
    DimensionOrderNotSupportedError,
    EXTENSIONS,
    generate_indices,
    get_appropriate_plugin_class,
    MultiSeriesImageFile,
    remove_extra_dimensions,
    translate_between_orders,
    UnknownFileFormatError,
)
from histalign.io.image.metadata import prune_metadata

_module_logger = logging.getLogger(__name__)


@click.command(help="Convert files to a different format.")
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
    "--from",
    "source_extension",
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
    "--to",
    "destination_extension",
    type=str,
    required=True,
    callback=lambda _, __, value: value.lower(),
    help="Extension to convert to.",
)
@click.option(
    "--from-order",
    type=str,
    required=False,
    default="",
    callback=lambda _, __, value: value.upper(),
    help="Dimension order of the 'SOURCE'.",
)
@click.option(
    "--to-order",
    type=str,
    required=False,
    default="",
    callback=lambda _, __, value: value.upper(),
    help="Dimension of the destination. If not provided, reuses --from-order.",
)
@click.option(
    "--override-series-support",
    "series_support_override",
    type=click.Choice(["0", "1", "2"]),
    required=False,
    default="2",
    callback=lambda _, __, value: int(value) if isinstance(value, str) else None,
    help=(
        "Override the support status of the destination type. 0 converts 'SOURCE' as "
        "if the destination format only supports single image. 1 converts 'SOURCE' as "
        "if the destination format supports single series only. 2 converts 'SOURCE' "
        "as if the destination supports multiple series. This cannot override support "
        "to something not supported by the destination format."
    ),
)
@click.option(
    "--force",
    is_flag=True,
    help="Whether to overwrite destination files if they already exist.",
)
def convert(
    source: Path,
    destination: Optional[Path],
    source_extension: str,
    destination_extension: str,
    from_order: str,
    to_order: str,
    series_support_override: int,
    force: bool,
) -> None:
    """Converts from `source` to `destination` as determined by extensions.

    Args:
        source (Path): Path to the source file or directory to convert. If a file, that
                       single file is converted.
        destination (Optional[Path], optional):
            Directory to output converted files in. If not provided, this defaults to
            `source` if it is a file or its parent otherwise.
        source_extension (str): Extension to glob `source` with when it is a directory.
                                This is ignored when `source` is a file.
        destination_extension (str): Extension to use when converting to the new format.
                                     This dictates which plugin to use.
        from_order (str): Order of the dimensions of `source`. If `source` is a
                          directory, all files should have the same order.
        to_order (str): Order to use for the converted files. Pass an empty string to
                        use `from_order` as the default.
        series_support_override (int): Override the level of support of the destination
                                       format.
        force (bool): Whether to overwrite files during conversion if they already
                      exist.
    """
    if source.is_dir() and not source_extension:
        raise ValueError(
            "Please provide a source extension when attempting to convert a directory."
        )

    if not source_extension:
        try:
            source_extension = extract_file_extension(source, EXTENSIONS.keys())
        except ValueError:
            raise UnknownFileFormatError("".join(source.suffixes))

    if source_extension and source_extension[0] != ".":
        source_extension = "." + source_extension
    if destination_extension[0] != ".":
        destination_extension = "." + destination_extension

    from_order: Optional[DimensionOrder] = (
        DimensionOrder(from_order.upper()) if from_order else None
    )
    if not to_order:
        to_order: Optional[DimensionOrder] = from_order
    else:
        to_order: DimensionOrder = DimensionOrder(to_order.upper())

    for source_path, destination_path in generate_jobs(
        source, destination, source_extension, destination_extension
    ):
        _module_logger.info(f"Starting conversion of '{source_path}'.")
        _convert(
            source_path,
            destination_path,
            from_order,
            to_order,
            series_support_override,
            force,
        )


def _convert(
    source_path: Path,
    destination_path: Path,
    source_order: Optional[DimensionOrder],
    destination_order: Optional[DimensionOrder],
    series_support_override: int,
    force: bool,
) -> None:
    source_plugin_class = get_appropriate_plugin_class(source_path, mode="r")
    source_file = source_plugin_class(
        source_path, mode="r", dimension_order=source_order
    )
    source_order = source_file.dimension_order
    current_destination_order = destination_order

    destination_file = None
    destination_plugin_class = get_appropriate_plugin_class(destination_path, mode="w")

    destination_supports_multi_series = (
        min(destination_plugin_class.series_support, series_support_override) > 1
    )
    destination_supports_series = (
        min(destination_plugin_class.series_support, series_support_override) > 0
    )
    if (
        not destination_supports_series
        and current_destination_order is not None
        and len(current_destination_order.value) > 2
    ):
        raise DimensionOrderNotSupportedError(
            current_destination_order, destination_plugin_class.format
        )

    cached_destination_path = None
    for series_index in range(
        source_file.series_count if isinstance(source_file, MultiSeriesImageFile) else 1
    ):
        for image_number, image_index in enumerate(
            generate_indices(source_order, source_file.shape, source_order)
        ):
            if destination_file is None:
                # Determine destination dimension order
                current_destination_order = destination_order
                if current_destination_order is None:
                    if destination_supports_series:
                        current_destination_order = source_order
                    else:
                        current_destination_order = (
                            DimensionOrder.YX
                            if "YX" in source_order.value
                            else DimensionOrder.XY
                        )

                # Devise an appropriate name to split (or not) the destination file
                # properly.
                if destination_supports_multi_series and (
                    len(current_destination_order.value) != 2
                    or source_order == current_destination_order
                ):
                    appended_destination_path = destination_path
                elif (
                    hasattr(source_file, "has_another_series")
                    and source_file.has_another_series
                ) or series_index != 0:
                    appended_destination_path = append_to_stem(
                        destination_path, f"series{series_index}"
                    )
                else:
                    appended_destination_path = destination_path

                if (
                    not destination_supports_multi_series
                    and not destination_supports_series
                ) or (
                    len(current_destination_order.value) == 2
                    and np.prod(source_file.shape)
                    / (source_file.metadata.SizeX * source_file.metadata.SizeY)
                    > 1
                ):
                    appended_destination_path = append_to_stem(
                        appended_destination_path, f"image{image_number}"
                    )

                # Make sure to not overwrite files if not enabled
                if appended_destination_path.exists() and not force:
                    # Put a guard here to avoid spamming debug
                    if cached_destination_path != appended_destination_path:
                        _module_logger.debug(
                            f"Skipping '{appended_destination_path}' destination path "
                            f"as it already exists and 'force' is not on."
                        )

                        if destination_supports_multi_series:
                            return
                        elif destination_supports_series:
                            break

                    cached_destination_path = appended_destination_path
                    continue

                # Pass over the metadata
                metadata = source_file.metadata
                metadata = prune_metadata(metadata, current_destination_order)

                _module_logger.debug(
                    f"Opening destination path '{appended_destination_path}'."
                )
                destination_file = destination_plugin_class(
                    appended_destination_path,
                    mode="w",
                    dimension_order=current_destination_order,
                    metadata=metadata,
                    shape=translate_between_orders(
                        source_file.shape, source_order, current_destination_order
                    ),
                    dtype=source_file.dtype,
                )

            # Translate variables from source order to destination order
            translated_index = translate_between_orders(
                image_index, source_order, current_destination_order
            )

            image = source_file.read_image(image_index)
            translated_image_axis_order = translate_between_orders(
                list(range(len(image.shape))),
                source_order,
                current_destination_order,
            )
            # Ensure indices start at 0 and are sequential.
            translated_image_axis_order = tuple(
                sorted(translated_image_axis_order).index(i)
                for i in translated_image_axis_order
            )

            # Translate (reshape and transpose) image as appropriate for destination
            # Remove extra dimensions without completely squeezing (some 1-size
            # dimensions might need to be kept).
            image = image.reshape(
                remove_extra_dimensions(
                    image.shape, source_order, current_destination_order
                )
            )
            image = np.transpose(image, translated_image_axis_order)

            destination_file.write_image(image, translated_index)

            if (not destination_supports_series and destination_file is not None) or (
                current_destination_order is not None
                and len(current_destination_order.value) == 2
                and source_order != current_destination_order
            ):
                destination_file.close()
                destination_file = None

        if source_file.supports_multi_series and source_file.has_another_series:
            source_file.seek_next_series()

            if destination_file is not None:
                if not destination_supports_multi_series or (
                    current_destination_order is not None
                    and len(current_destination_order.value) == 2
                    and source_order != current_destination_order
                ):
                    destination_file.close()
                    destination_file = None
                else:
                    metadata = source_file.metadata
                    metadata = prune_metadata(metadata, current_destination_order)

                    destination_file.seek_next_series(
                        shape=translate_between_orders(
                            source_file.shape, source_order, current_destination_order
                        ),
                        dtype=source_file.dtype,
                        metadata=metadata,
                    )

    if destination_supports_multi_series and destination_file is not None:
        destination_file.close()


def extract_file_extension(
    file_path: Path,
    allowed_extensions: Iterable[str],
) -> str:
    """Returns the longest extension that matches one of `allowed_extensions`.

    Note that any extension not starting with a period in `allowed_extensions` will
    never be matched.

    Args:
        file_path (Path): Path to extract the extension from.
        allowed_extensions (Sequence[str]): Sequence of extensions to look for.

    Returns:
        str: The longest extension from `allowed_extensions` found in `file_path`.

    Raises:
        ValueError: When none of the allowed extensions are found in the path.
        ValueError: When `file_path` is a directory.
    """
    if file_path.is_dir():
        raise ValueError("Cannot extract an extension from a directory.")

    file_suffixes = file_path.suffixes
    while file_suffixes:
        current_combination = "".join(file_suffixes)
        for suffixes in allowed_extensions:
            if current_combination == suffixes:
                return current_combination

        file_suffixes = file_suffixes[1:]

    raise ValueError(
        "None of the allowed extensions could be matched with a sub-extension of "
        f"'{file_path.name}'."
    )


def generate_jobs(
    source: Path,
    destination: Optional[Path],
    source_extension: str,
    destination_extension: str,
) -> list[tuple[Path, Path]]:
    """Generates pairs of source-destination paths with proper extensions.

    Args:
        source (Path): Path to use as the basis for jobs. If this is a file, a single
                       pair is generated. If this is a directory, all files with
                       `source_extension` will generate their own pair.
        destination (Optional[Path]): Path to use as the output root. If this is `None`,
                                      `source` is used if it is a file, its parent
                                      otherwise.
        source_extension (str): Extension to use when globbing `source` when it is a
                                file. This is ignore otherwise.
        destination_extension (str): Extension to set on the destination files.

    Returns:
        list[tuple[Path, Path]]: A list of (source, destination) path tuples.
    """
    source_extension = source_extension.lower()
    destination_extension = destination_extension.lower()

    if destination is None:
        destination = source if source.is_dir() else source.parent
    elif destination.is_file():
        raise ValueError("Expected `None` or directory for `destination`. Got file.")

    if source.is_file():
        return [
            (
                source,
                destination
                # Only replace the last occurrence
                / source.name[::-1].replace(
                    source_extension[::-1], destination_extension[::-1], 1
                )[::-1],
            )
        ]
    else:
        jobs = []
        for file_path in source.glob(f"[!.]*{source_extension}"):
            jobs.extend(
                generate_jobs(
                    file_path, destination, source_extension, destination_extension
                )
            )
        return jobs


def append_to_stem(path: Path, string: str, separator: str = "_") -> Path:
    return path.with_stem(path.stem + separator + string)
