# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierDelrée@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.application.ThumbnailScrollArea import ThumbnailScrollArea
from histalign.application.Workspace import Workspace


class ThumbnailDockWidget(QtWidgets.QDockWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)

        self.setWidget(ThumbnailScrollArea())

    def update_thumbnails(self, workspace: Workspace) -> None:
        self.widget().populate_thumbnails(workspace)
        self.widget().swapped_thumbnails.connect(workspace.swap_slices)
