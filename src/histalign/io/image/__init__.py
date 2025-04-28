# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from abc import ABC, abstractmethod
from enum import Enum
import hashlib
import logging
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence, TypeVar

import click
import numpy as np
from PIL import Image

from histalign.language_helpers import classproperty

Extension = str
Format = str
_T = TypeVar("_T")

SUPPORTED_READ_FORMATS: list[Format] = []
SUPPORTED_WRITE_FORMATS: list[Format] = []
PLUGINS: dict[Format, type["ImageFile"]] = {}
EXTENSIONS: dict[Extension, Format] = {}

# A dimension with 4 or fewer size is considered C. Between 5 and 49 (inclusive) is
# considered a Z. Anything 50 and above is considered a Y and then an X (from left to
# right, bias is for Y for be the first dimension then X).
CZ_THRESHOLD = 5
XY_THRESHOLD = 50

THUMBNAIL_DIMENSIONS = (320, 180)  # XY not IJ
THUMBNAIL_ASPECT_RATIO = THUMBNAIL_DIMENSIONS[0] / THUMBNAIL_DIMENSIONS[1]

_module_logger = logging.getLogger(__name__)


@click.command("list", help="List supported formats.")
def list_formats() -> None:
    """Lists the supported formats currently registered."""
    click.echo("Supported file formats for reading:")
    for supported_format in SUPPORTED_READ_FORMATS:
        extensions = (
            extension
            for extension, format in EXTENSIONS.items()
            if format == supported_format
        )
        click.echo(f"\t{supported_format} ({', '.join(extensions)})")

    click.echo("Supported file formats for writing:")
    for supported_format in SUPPORTED_WRITE_FORMATS:
        extensions = (
            extension
            for extension, format in EXTENSIONS.items()
            if format == supported_format
        )
        click.echo(f"\t{supported_format} ({', '.join(extensions)})")


def load_plugins() -> None:
    """Loads image plugins from the 'histalign.io/image' directory."""
    root = __name__
    for file in Path(__file__).parent.iterdir():
        if file.stem.endswith("ImagePlugin"):
            try:
                __import__(f"{root}.{file.stem}", globals(), locals())
            except ImportError as error:
                _module_logger.error(f"Failed to load plugin '{file.stem}'.")
                _module_logger.error(error)


def get_appropriate_plugin_class(
    file_path: Path,
    mode: str,
) -> type["ImageFile"]:
    """Returns appropriate image plugin for `file_path` based on extension and mode."""
    suffixes = file_path.suffixes
    for i in range(len(suffixes)):
        current_combination = "".join(suffixes[i:])

        format = EXTENSIONS.get(current_combination)
        if format is not None:
            break
    else:
        raise UnknownFileFormatError("".join(suffixes))

    if (
        (mode == "r" and format not in SUPPORTED_READ_FORMATS)
        or mode != "r"
        and format not in SUPPORTED_WRITE_FORMATS
    ):
        raise ModeNotSupportedError(format, mode)

    return PLUGINS[format]


def register_plugin(
    format: str,
    plugin: type["ImageFile"],
    extensions: Sequence[str],
    supports_read: bool,
    supports_write: bool,
) -> None:
    """Registers an image plugin as the format for a list of extensions.

    Args:
        format (str): Name of the plugin format.
        plugin (type[ImageFile]): Plugin to use to open and read images of `format`.
        extensions (list[str]): Extensions for which to associate `plugin`.
        supports_read (bool): Whether the plugin supports reading.
        supports_write (bool): Whether the plugin supports writing.
    """
    if supports_read:
        if format in SUPPORTED_READ_FORMATS:
            _module_logger.warning(
                f"Tried registering the '{format}' format for reading multiple times. "
                f"Keeping the latest registration "
                f"(previous plugin: {PLUGINS.get(format)}, new plugin: {plugin})."
            )
        else:
            SUPPORTED_READ_FORMATS.append(format)
    if supports_write:
        if format in SUPPORTED_WRITE_FORMATS:
            _module_logger.warning(
                f"Tried registering the '{format}' format for writing multiple times. "
                f"Keeping the latest registration "
                f"(previous plugin: {PLUGINS.get(format)}, new plugin: {plugin})."
            )
        else:
            SUPPORTED_WRITE_FORMATS.append(format)

    if not supports_read and not supports_write:
        _module_logger.error(
            "Attempted to register plugin which cannot read nor write. Aborting."
        )
        return

    PLUGINS[format] = plugin

    for extension in extensions:
        if extension in EXTENSIONS.keys():
            _module_logger.warning(
                f"Tried registering the '{extension}' extension multiple times. "
                f"Keeping the latest registration "
                f"(previous format: {EXTENSIONS.get(extension)}, new format: {format})."
            )

        EXTENSIONS[extension] = format

    _module_logger.debug(f"Registered '{format}' format.")


class DimensionOrder(Enum):
    """Enum to help ensure only sensible dimension orders can be represented.

    A sensible dimension order always keeps XY together (but X or Y first doesn't
    matter) and can include any permutation with Z and C.

    Legend:
        X: width
        Y: height
        C: channel
        Z: Z-index
    """

    XYCZ = "XYCZ"
    XYZC = "XYZC"
    YXCZ = "YXCZ"
    YXZC = "YXZC"
    CXYZ = "CXYZ"
    CYXZ = "CYXZ"
    CZXY = "CZXY"
    CZYX = "CZYX"
    ZXYC = "ZXYC"
    ZYXC = "ZYXC"
    ZCXY = "ZCXY"
    ZCYX = "ZCYX"
    XYC = "XYC"
    YXC = "YXC"
    CXY = "CXY"
    CYX = "CYX"
    XYZ = "XYZ"
    YXZ = "YXZ"
    ZXY = "ZXY"
    ZYX = "ZYX"
    XY = "XY"
    YX = "YX"


class ImageFile(ABC):
    """ABC for plugins wrapping different file formats on disk with a common interface.

    Attributes:
        format (str): Common name of the plugin format (e.g., PNG, JPEG, TIFF).
        extensions (tuple[str, ...]): Extensions the plugin supports.
        dimension_order (DimensionOrder): Order in which the dimensions are
                                          organised in the image's array.
        index (tuple[slice, ...]): Current index the wrapper can read.
        series_support (int): Level of series support of the plugin. A support of 0
                              means only single images are supported. A support of 1
                              means single series are supported. A support of 2 means
                              multiple series are supported. This is not usually
                              accessed directly but through one of the convenience
                              properties (e.g., 'supports_series').
    """

    format: str
    extensions: tuple[str, ...]

    file_path: Path
    dimension_order: DimensionOrder
    index: tuple[slice, ...]

    series_support: int = 0

    def __init__(
        self,
        file_path: Path,
        mode: str,
        dimension_order: Optional[DimensionOrder],
        metadata: Optional["OmeXml"] = None,
        **kwargs,
    ) -> None:
        self.file_path = file_path

        if dimension_order is None and mode == "w":
            raise ValueError(
                f"Mode 'w' is unsupported with an unknown dimension order."
            )
        self.dimension_order = dimension_order

        self._open(file_path, mode, metadata, **kwargs)

        # Attempt to retrieve dimension order from metadata
        if dimension_order is None:
            dimension_order = self.try_get_dimension_order()
            if dimension_order is not None:
                dimension_order = DimensionOrder(dimension_order)
            # When all else fails, try to to guess dimension order from heuristic
            if dimension_order is None:
                # Allow potentially missing dimension order for probing
                try:
                    dimension_order = attempt_guess_dimension_order(self.shape)

                    if len(dimension_order.value) > 2 and not self.supports_series:
                        raise DimensionOrderNotSupportedError(
                            dimension_order, self.format
                        )
                    self.dimension_order = dimension_order

                    if len(dimension_order.value) != len(self.shape):
                        raise DimensionOrderMismatchError(
                            dimension_order, file_path, self.shape
                        )
                except FailedGuessingDimensionOrderError as error:
                    if kwargs.get("allow_no_dimension_order") is None:
                        raise error
            self.dimension_order = dimension_order

        if self.dimension_order is not None:
            self.reset_index()

    @property
    def hash(self) -> str:
        return generate_file_hash(self.file_path)

    @property
    @abstractmethod
    def shape(self) -> tuple[int, ...]: ...

    @property
    @abstractmethod
    def dtype(self) -> np.dtype: ...

    @property
    def metadata(self) -> "OmeXml":
        return self._extract_metadata()

    @classproperty
    def supports_series(cls) -> bool:
        return cls.series_support > 0

    @classproperty
    def supports_multi_series(cls) -> bool:
        return cls.series_support > 1

    @abstractmethod
    def _open(
        self, file_path: Path, mode: str, metadata: Optional["OmeXml"] = None, **kwargs
    ) -> None: ...

    @abstractmethod
    def load(self) -> np.ndarray: ...

    def close(self) -> None:
        self.file_handle = DeferredError(ValueError("Operation on closed file."))

    def generate_thumbnail(
        self, dimensions: tuple[int, int] = THUMBNAIL_DIMENSIONS
    ) -> np.ndarray:
        """Generates a thumbnail for the current image.

        Args:
            dimensions (tuple[int, int], optional):
                Dimensions of the target thumbnail. The image is padded to fit in this
                aspect ratio.

        Returns:
            np.ndarray: A thumbnail of the current image
        """
        _module_logger.debug(f"Generating thumbnail for '{self.file_path}'.")

        _module_logger.debug(f"Retrieving image for thumbnail.")
        # Retrieve a starting point for thumbnail generation, allowing plugins to
        # optimise how much of an image to load when thumbnail generation is the goal.
        image = self.get_image_for_thumbnail(dimensions)
        # Transpose the image if width is before height as PIL assumes NumPy arrays are
        # using row-major.
        if "XY" in self.dimension_order.value:
            image = image.T

        _module_logger.debug("Resizing image to thumbnail.")
        # Use PIL to resize
        image_pil = Image.fromarray(image)
        image_pil.thumbnail(dimensions, resample=Image.Resampling.NEAREST)

        thumbnail = np.array(image_pil)

        # Pad
        i_padding = dimensions[1] - thumbnail.shape[0]
        j_padding = dimensions[0] - thumbnail.shape[1]

        thumbnail = np.pad(
            thumbnail,
            (
                (i_padding // 2, i_padding // 2 + i_padding % 2),
                (j_padding // 2, j_padding // 2 + j_padding % 2),
            ),
        )

        _module_logger.debug(f"Finished generating thumbnail for '{self.file_path}'.")
        return thumbnail

    def get_image_for_thumbnail(self, dimensions: tuple[int, int]) -> np.ndarray:
        """Loads the current image for thumbnail generation.

        This function uses fancy indexing to limit how much of an image to load to
        generate a thumbnail. Not all plugins can make use of the fancy indexing and
        the whole image will be loaded and then indexed. However, plugins like HDF5
        and TIFF can make use of the fancy indexing to only load the relevant pixels
        of the image.

        Args:
            dimensions (tuple[int, int]): Dimensions of the target thumbnail.

        Returns:
            np.ndarray: The image to thumbnail.
        """
        display_shape = np.array(self.shape)[np.array(self.index) == slice(None)]
        if "YX" in self.dimension_order.value:
            display_shape = display_shape[::-1]

        # Load the smallest image possible while still above thumbnail dimensions
        step = int(np.max(np.array(display_shape) / np.array(dimensions)) // 1)
        index = tuple(
            (
                slice_ if slice_ != slice(None) else slice(None, None, step)
                for slice_ in self.index
            )
        )

        return self.read_image(index).squeeze()

    @abstractmethod
    def try_get_dimension_order(self) -> Optional[DimensionOrder]:
        """Attempts to get the dimension order from metadata.

        Returns:
            Optional[DimensionOrder]:
                The retrieved dimension order or `None` if it could not be determined.
        """

    @abstractmethod
    def read_image(self, index: tuple[slice, ...]) -> np.ndarray: ...

    @abstractmethod
    def write_image(self, image: np.ndarray, index: tuple[slice, ...]) -> None: ...

    def reset_index(self) -> None:
        index = [slice(0, 1)] * len(self.dimension_order.value)
        index[self.dimension_order.value.find("X")] = slice(None)
        index[self.dimension_order.value.find("Y")] = slice(None)
        self.index = tuple(index)

    def iterate_images(self, iteration_order: DimensionOrder) -> Iterator[np.ndarray]:
        for index in generate_indices(
            self.dimension_order, self.shape, iteration_order
        ):
            self.index = index
            yield self.read_image(index)

    @abstractmethod
    def _extract_metadata(self) -> "OmeXml": ...


class MultiSeriesImageFile(ImageFile, ABC):
    """ABC for plugins that can handle multiple series.

    Attributes:
        series_index (int): Index of the current series.
    """

    series_index: int = 0

    @property
    @abstractmethod
    def series_count(self) -> int: ...

    @property
    def has_another_series(self) -> bool:
        return self.series_index < self.series_count - 1

    @abstractmethod
    def create_series(
        self, shape: Sequence[int], dtype: np.dtype, metadata: Optional["OmeXml"] = None
    ) -> None: ...

    def seek_next_series(self, **kwargs) -> None:
        if not self.has_another_series:  # Assume writing mode
            if (shape := kwargs.get("shape")) is None:
                raise ValueError("No shape provided for new series.")
            if (dtype := kwargs.get("dtype")) is None:
                raise ValueError("No dtype provided for new series.")
            metadata = kwargs.get("metadata")

            self.series_index += 1  # Necessary for some types to name new series
            self.create_series(shape=shape, dtype=dtype, metadata=metadata)
            self.series_index -= 1  # Avoid 'else' by subtracting here and resuming flow

        self.series_index += 1

        self.reset_index()


class DimensionOrderMismatchError(BaseException):
    def __init__(
        self, dimension_order: DimensionOrder, file_path: Path, shape: tuple[int, ...]
    ) -> None:
        message = (
            f"Provided dimension order does not match shape on disk for file "
            f"'{file_path.name}' ({dimension_order.value} vs {shape}). "
            f"Ensure all dimensions are included in the dimension order."
        )

        super().__init__(message)


class DimensionOrderNotSupportedError(BaseException):
    def __init__(self, dimension_order: DimensionOrder, format: Format) -> None:
        message = (
            f"Provided dimensions order is not compatible with {format} image "
            f"plugin. Dimension order '{dimension_order}' indicates more than two "
            f"dimensions but plugin only supports single images."
        )

        super().__init__(message)


class FailedGuessingDimensionOrderError(BaseException):
    def __init__(self, step: str, shape: Sequence[_T]) -> None:
        message = (
            f"Failed to guess dimension order from shape '{shape}'. "
            f"Failure happened when trying to guess {step}. "
            f"Try inputting order manually through a command option where possible."
        )

        super().__init__(message)


class ModeNotSupportedError(BaseException):
    def __init__(self, format: Format, mode: str) -> None:
        message = (
            f"A plugin was found for {format} files "
            f"but it does not support mode '{mode}'."
        )

        super().__init__(message)


class UnknownFileFormatError(BaseException):
    def __init__(self, extension: str) -> None:
        message = (
            f"No matching file plugin found for extension '{extension}' or a "
            f"sub-extension. "
            f"Recognised extensions are {','.join(EXTENSIONS.keys())}."
        )

        super().__init__(message)


class DeferredError:
    """A special class to replace file handle with.

    This provides an elegant interface to give feedback to the user when trying to carry
    out operations on a closed file. This provides a much better feedback than some sort
    of NoneType error.

    Heavily inspired from PIL's 'DeferredError'.
    """

    def __init__(self, exception: BaseException) -> None:
        self.exception = exception

    # True signature is "-> Never" but mypy doesn't like it
    def __getitem__(self, _: Any) -> Any:
        raise self.exception

    # True signature is "-> Never" but mypy doesn't like it
    def __getattr__(self, _: Any) -> Any:
        raise self.exception


def generate_file_hash(path: str | Path) -> str:
    path = str(path)
    return hashlib.md5(path.encode("UTF-8")).hexdigest()


def generate_indices(
    dimension_order: DimensionOrder,
    shape: Sequence[int],
    iteration_order: Optional[DimensionOrder] = None,
) -> Iterator[tuple[slice, ...]]:
    """Generates indices into shape in custom order.

    Note that indices for XY are both always `slice(None, None, None)`.

    Args:
        dimension_order (DimensionOrder): Dimension order of `shape`.
        shape (Sequence[int]): Shape for which to generate indices.
        iteration_order (DimensionOrder, optional):
            Order to generate indices in. For example, passing DimensionOrder.CZYX will
            iterate as if using nested loops in order C->Z->XY, while
            DimensionOrder.ZCYX will iterate in order Z->C->YX.

    Returns:
        Iterator[tuple[slice, ...]]: Generator over the indices that index into `shape``
                                     in `iteration_order` order.
    """
    if iteration_order is None:
        iteration_order: DimensionOrder = dimension_order

    if not (len(dimension_order.value) == len(shape) == len(iteration_order.value)):
        raise ValueError(
            f"All of `dimension_order`, `shape`, and `iteration_order` should have the "
            f"same length ({len(dimension_order.value)} vs {len(shape)} "
            f"vs {len(iteration_order.value)})."
        )

    iteration_order: list[str] = list(iteration_order.value)
    iteration_order.remove("X")
    iteration_order.remove("Y")
    order_of_operation = [
        index
        for dimension in iteration_order
        if (index := dimension_order.value.find(dimension)) != -1
    ]

    index_blueprint = [slice(0, 1)] * len(shape)
    index_blueprint[dimension_order.value.find("X")] = slice(None)
    index_blueprint[dimension_order.value.find("Y")] = slice(None)

    yield from _generate_indices(shape, index_blueprint, order_of_operation)


def _generate_indices(
    shape: Sequence[int],
    index_blueprint: list[slice],
    order_of_operations: list[int],
) -> Iterator[tuple[slice, ...]]:
    if not order_of_operations:
        yield tuple(index_blueprint)
        return

    order_of_operation = order_of_operations[0]
    for i in range(shape[order_of_operation]):
        index_blueprint[order_of_operation] = slice(i, i + 1)

        yield from _generate_indices(shape, index_blueprint, order_of_operations[1:])


def translate_between_orders(
    sequence: Sequence[_T],
    from_order: DimensionOrder,
    to_order: DimensionOrder,
) -> tuple[_T, ...]:
    """Translates a sequence between dimension orders, removing dimensions as needed.

    Note that although dimensions can be removed if they are not present in `to_order`,
    they cannot be added.

    Args:
        sequence (Sequence[_T]): Sequence to translate.
        from_order (DimensionOrder): Dimension order of `sequence`.
        to_order (DimensionOrder): Dimension order to translate to.

    Returns:
        tuple[_T, ...]: The translated sequence. This is always a subset of 'sequence'.

    Raises:
        ValueError: When `to_order` has dimensions that are not present in `from_order`.
    """
    pruned_sequence = remove_extra_dimensions(sequence, from_order, to_order)
    pruned_from_order = remove_extra_dimensions(from_order.value, from_order, to_order)

    if len(pruned_from_order) < len(to_order.value):
        raise ValueError(
            f"Cannot translate sequence from "
            f"'{from_order.value}' to '{to_order.value}'. "
            f"Dimensions should not be added (but can be removed)."
        )

    return tuple(
        pruned_sequence[pruned_from_order.index(dimension)]
        for dimension in to_order.value
    )


def remove_extra_dimensions(
    sequence: Sequence[_T],
    from_order: DimensionOrder,
    to_order: DimensionOrder,
) -> tuple[_T, ...]:
    """Prunes `sequence` to only contain values present in `to_order`.

    This does not permutes `sequence` but instead removes items at indices where a
    dimension in `from_order` that does not exist in `to_order` is located.

    Args:
        sequence (Sequence[_T]): Sequence to prune.
        from_order (DimensionOrder): Dimension order of `sequence`.
        to_order (DimensionOrder): Dimension order to prune to.

    Returns:
        tuple[_T, ...]: The pruned sequence.
    """
    if len(sequence) != len(from_order.value):
        raise ValueError(
            f"`sequence` length does not match `from_order` length "
            f"({sequence}: {len(sequence)} "
            f"vs {from_order.value}: {len(from_order.value)})."
        )

    pruned_sequence = ()
    for index, value in enumerate(sequence):
        if from_order.value[index] not in to_order.value:
            continue

        pruned_sequence += (value,)

    return pruned_sequence


def attempt_guess_dimension_order(shape: Sequence[int]) -> DimensionOrder:
    """Attempts to guess `shape`'s dimension order.

    Args:
        shape (Sequence[int]): Shape on which to make a guess.

    Returns:
        DimensionOrder: The dimension order of `shape` as determined by the heuristic.

    Raises:
        FailedGuessingDimensionOrderError:
            Whenever a dimension's position is ambiguous or invalid and a guess cannot
            be determined.
    """
    shape = np.array(shape)
    shape_length = len(shape)

    c_candidates = shape < CZ_THRESHOLD
    if c_candidates.sum() > 1:
        raise FailedGuessingDimensionOrderError("channel", shape)

    z_candidates = (CZ_THRESHOLD <= shape) & (shape < XY_THRESHOLD)
    if z_candidates.sum() > 1:
        raise FailedGuessingDimensionOrderError("z-index", shape)

    xy_candidates = shape >= XY_THRESHOLD
    if xy_candidates.sum() != 2:
        raise FailedGuessingDimensionOrderError("XY", shape)
    xy_coordinates = xy_candidates.nonzero()[0]
    if xy_coordinates[1] - xy_coordinates[0] != 1:
        raise FailedGuessingDimensionOrderError("XY distance", shape)

    # Sanity check, should not be possible
    if np.sum(c_candidates | z_candidates | xy_candidates) != shape_length:
        raise FailedGuessingDimensionOrderError("gathering", shape)

    order = np.where(c_candidates, np.array(["C"] * shape_length), "")
    order = np.where(z_candidates, np.array(["Z"] * shape_length), order)
    # YX order bias as that seems more common from anecdotal evidence
    order[xy_coordinates[0]] = "Y"
    order[xy_coordinates[1]] = "X"

    return DimensionOrder("".join(order))
