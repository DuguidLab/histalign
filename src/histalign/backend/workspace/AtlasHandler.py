# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from typing import Optional

import numpy as np
from PySide6 import QtCore

from histalign.backend.ccf.allen_downloads import get_atlas_path
from histalign.backend.workspace.VolumeManager import VolumeManager


class AtlasHandler(QtCore.QObject):
    atlas_downloaded: QtCore.Signal = QtCore.Signal()
    atlas_loaded: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        atlas_resolution: int,
        volume_manager: VolumeManager,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)

        self.atlas_resolution = atlas_resolution
        self.volume_manager = volume_manager

    @QtCore.Slot()
    def handle_atlas(self) -> None:
        atlas_file_path = get_atlas_path(self.atlas_resolution)
        self.atlas_downloaded.emit()

        try:
            self.volume_manager.load_volume(atlas_file_path, np.uint8)
            self.atlas_loaded.emit()
        except FileNotFoundError:
            self.logger.error(
                f"Could not load atlas. File not found ('{atlas_file_path}'.)"
            )
