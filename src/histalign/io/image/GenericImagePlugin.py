# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from histalign.io import DimensionOrder
from histalign.io.image import ImageFile, register_plugin
from histalign.io.image.metadata import OmeXml

# Allow fie sizes up to 1 GiB
Image.MAX_IMAGE_PIXELS = 1024**3


class GenericImagePlugin(ImageFile):
    format: str = "MISC"
    extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg")

    series_support = 0

    @property
    def shape(self) -> tuple[int, ...]:
        return self.read_image(tuple()).shape

    @property
    def dtype(self) -> np.dtype:
        return self.read_image(tuple()).dtype

    def _open(
        self, file_path: Path, mode: str, metadata: Optional[OmeXml] = None, **kwargs
    ) -> None:
        self._file_path = file_path
        self._cache = None
        if mode == "r":
            self.file_handle = Image.open(file_path, mode="r")
        else:
            if (shape := kwargs.get("shape")) is None:
                raise ValueError("No shape provided for new file in writing mode.")
            if (dtype := kwargs.get("dtype")) is None:
                raise ValueError("No dtype provided for new file in writing mode.")

            self.file_handle = Image.fromarray(np.zeros(shape=shape, dtype=dtype))

    def load(self) -> np.ndarray:
        return self.read_image(tuple())

    def try_get_dimension_order(self) -> Optional[DimensionOrder]:
        return DimensionOrder("YX")

    def read_image(self, index: tuple[slice, ...]) -> np.ndarray:
        if self._cache is None:
            self._cache = np.array(self.file_handle)

        return self._cache

    def write_image(self, image: np.ndarray, index: tuple[slice, ...]) -> None:
        self.file_handle = Image.fromarray(image)
        self.file_handle.save(self._file_path, format="PNG")

    def _extract_metadata(self) -> OmeXml:
        return OmeXml(
            DimensionOrder=self.dimension_order,
            SizeX=self.shape[self.dimension_order.value.index("X")],
            SizeY=self.shape[self.dimension_order.value.index("Y")],
            Type=self.dtype,
            Channel=[],
        )


register_plugin(
    format=GenericImagePlugin.format,
    plugin=GenericImagePlugin,
    extensions=GenericImagePlugin.extensions,
    supports_read=True,
    supports_write=True,
)
