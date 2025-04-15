# SPDX-FileCopyrightText: 2025-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from typing import Optional

import numpy as np
from PySide6 import QtCore

from histalign.backend.models import VolumeBuildingSettings
from histalign.backend.registration.alignment import (
    build_aligned_array,
    interpolate_sparse_3d_array,
)
from histalign.io import load_volume

_module_logger = logging.getLogger(__name__)


class VolumeBuilderThread(QtCore.QThread):
    def __init__(
        self, settings: VolumeBuildingSettings, parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)

        self.settings = settings

    def run(self) -> None:
        # Log here instead of QThread.started as we are only now in the new thread
        _module_logger.debug(
            f"Volume builder thread "
            f"({hex(id(QtCore.QThread.currentThread()))}) started."
        )

        settings = self.settings

        # Build the 3D volume from slices
        # TODO: Potentially make this function a QObject to provide progress feedback
        #       to user. Alternatively, add a callback parameter for reporting.
        build_aligned_array(
            settings.alignment_directory,
            projection_regex=settings.z_stack_regex,
            channel_regex=settings.channel_regex,
            channel_index=settings.channel_index,
            force=True,
        )

        # Log here instead of QThread.finished as we are only now in the new thread
        _module_logger.debug(
            f"Volume builder thread "
            f"({hex(id(QtCore.QThread.currentThread()))}) finished."
        )


class VolumeInterpolatorThread(QtCore.QThread):
    def __init__(
        self, settings: VolumeBuildingSettings, parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)

        self.settings = settings

    def run(self) -> None:
        # Log here instead of QThread.started as we are only now in the new thread
        _module_logger.debug(
            f"Volume interpolator thread "
            f"({hex(id(QtCore.QThread.currentThread()))}) started."
        )

        settings = self.settings

        # Check the 3D array already exists
        aligned_array_path = (
            settings.alignment_directory
            / "volumes"
            / "aligned"
            / f"{settings.alignment_directory.name}.h5"
        )
        if not aligned_array_path.exists():
            _module_logger.error(
                f"Could not find aligned array path for "
                f"'{settings.original_directory}'. Ensure it has been generated before "
                f"interpolating."
            )
            _module_logger.debug(
                f"Volume interpolator thread "
                f"({hex(id(QtCore.QThread.currentThread()))}) aborted."
            )
            return

        # Load the 3D array
        aligned_array = load_volume(aligned_array_path, return_raw_array=True)

        # Ensure the 3D array is not empty
        if not np.any(aligned_array):
            _module_logger.error(
                "Aligned array is empty. Interpolator aborting. Ensure parameters "
                "given to volume builder are valid (e.g., ensure the channel "
                "corresponds to a valid file name)."
            )
            return

        # Interpolate the 3D array
        # TODO: Potentially make this function a QObject to provide progress feedback
        #       to user. Alternatively, add a callback parameter for reporting.
        interpolate_sparse_3d_array(
            aligned_array,
            alignment_directory=settings.alignment_directory,
            resolution=settings.resolution,
            force=True,
        )

        # Log here instead of QThread.finished as we are only now in the new thread
        _module_logger.debug(f"Volume interpolator thread ({hex(id(self))}) finished.")
