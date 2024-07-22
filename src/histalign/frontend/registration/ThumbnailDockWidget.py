# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierDelrée@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtWidgets

from histalign.frontend.registration.ThumbnailScrollArea import ThumbnailScrollArea
from histalign.backend.workspace.Workspace import Workspace


class ThumbnailDockWidget(QtWidgets.QDockWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)

        self.setWidget(ThumbnailScrollArea())

    def update_thumbnails(self, workspace: Workspace) -> None:
        workspace.thumbnail_generated.connect(self.widget().update_thumbnail)
        self.widget().swapped_thumbnails.connect(workspace.swap_slices)
