# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtWidgets
from scipy.ndimage import gaussian_filter

from histalign.backend.ccf.downloads import download_structure_mask
from histalign.backend.ccf.paths import get_structure_mask_path
from histalign.backend.io import load_volume, RESOURCES_ROOT
from histalign.backend.models import Resolution
from histalign.backend.preprocessing import normalise_array
from histalign.frontend.common_widgets import (
    CollapsibleWidgetArea,
    NavigationWidget,
    PreferentialSplitter,
)
from histalign.frontend.visualisation.information import InformationWidget
from histalign.frontend.visualisation.views import SliceViewer, VolumeViewer

_module_logger = logging.getLogger(__name__)


class VisualisationWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        #
        self.project_root = None
        self.resolution = None

        self._saved_left_size = -1
        self._saved_right_size = -1

        self._pixmap_item = None

        #
        central_view = SliceViewer()

        self.central_view = central_view

        #
        navigation_widget = NavigationWidget()

        navigation_widget.open_image_requested.connect(self.open_image)
        navigation_widget.open_volume_requested.connect(self.open_volume)
        navigation_widget.setEnabled(False)

        self.navigation_widget = navigation_widget

        #
        information_widget = InformationWidget()

        information_widget.structures_widget.structure_checked.connect(
            central_view.contour_structure
        )
        information_widget.structures_widget.structure_unchecked.connect(
            central_view.remove_contours
        )
        information_widget.structures_widget.setEnabled(False)

        self.information_widget = information_widget

        #
        left_tools_widget = CollapsibleWidgetArea("left_to_right")

        left_tools_widget.add_widget(
            navigation_widget, RESOURCES_ROOT / "icons" / "folders-icon.svg"
        )

        self.left_tools_widget = left_tools_widget

        #
        right_tools_widget = CollapsibleWidgetArea("right_to_left")

        right_tools_widget.add_widget(
            information_widget,
            RESOURCES_ROOT / "icons" / "three-horizontal-lines-icon.png",
        )

        self.right_tools_widget = right_tools_widget

        #
        splitter = PreferentialSplitter()

        splitter.add_widgets([left_tools_widget, central_view, right_tools_widget])

        self.splitter = splitter

        #
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(splitter)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def get_baseline_splitter_sizes(self) -> list[int]:
        width = (
            self.splitter.width() - self.splitter.count() * self.splitter.handleWidth()
        )
        unit = width // 5  # Split the view in 1-3-1, i.e. multiples of 5ths

        return [unit, 3 * unit, unit]

    @QtCore.Slot()
    def open_project(
        self, project_root: str | Path, resolution: Resolution, *args, **kwargs
    ) -> None:
        path = Path(project_root)

        self.project_root = path
        self.resolution = resolution
        self.navigation_widget.parse_project(path)
        self.navigation_widget.setEnabled(True)

    @QtCore.Slot()
    def open_image(self, path: Path) -> None:
        old_view = self.central_view
        new_view = old_view

        if isinstance(old_view, SliceViewer):
            new_view.open_image(path)
        else:
            new_view = SliceViewer()

        if old_view is not new_view:
            self.central_view = new_view
            self.splitter.replaceWidget(1, new_view)
            old_view.deleteLater()

        self.information_widget.structures_widget.setEnabled(True)

    @QtCore.Slot()
    def open_volume(self, path: Path) -> None:
        old_view = self.central_view
        new_view = old_view

        volume = load_volume(path, normalise_dtype=np.uint16, return_raw_array=True)

        # Preprocessing would have been done beforehand
        volume = gaussian_filter(volume, sigma=5, radius=20)
        volume = normalise_array(volume, dtype=np.uint8)
        volume = np.digitize(volume, np.linspace(0, 255, 25)).astype(np.uint8)
        volume = normalise_array(volume, dtype=np.uint16)

        mask_path = get_structure_mask_path("root", self.resolution)
        if not Path(mask_path).exists():
            download_structure_mask("root", self.resolution)
        mask = load_volume(mask_path, return_raw_array=True)
        volume = np.where(mask, volume, 0)

        if isinstance(old_view, VolumeViewer):
            new_view.set_overlay_volume(volume)
        else:
            new_view = VolumeViewer(resolution=self.resolution, overlay_volume=volume)

        if old_view is not new_view:
            self.central_view = new_view
            self.splitter.replaceWidget(1, new_view)
            old_view.deleteLater()

        self.information_widget.structures_widget.setEnabled(False)
