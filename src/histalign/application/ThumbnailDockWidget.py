# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierDelrée@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.application.ThumbnailScrollArea import ThumbnailScrollArea
from histalign.application.Workspace import Workspace


class ThumbnailDockWidget(QtWidgets.QDockWidget):
    workspace: Optional[Workspace]

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)

        self.workspace = None

    def set_workspace(self, workspace: Workspace) -> None:
        self.workspace = workspace

        thumbnail_scroll_area = ThumbnailScrollArea()
        thumbnail_scroll_area.populate_thumbnails(self.workspace)
        thumbnail_scroll_area.swapped_thumbnails.connect(self.workspace.swap_slices)

        self.setWidget(thumbnail_scroll_area)
