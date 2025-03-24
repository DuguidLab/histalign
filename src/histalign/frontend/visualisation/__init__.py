# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.io import RESOURCES_ROOT
from histalign.frontend.common_widgets import (
    BasicApplicationWindow,
    CollapsibleWidgetArea,
    VisibleHandleSplitter,
)
from histalign.frontend.visualisation.information import InformationWidget
from histalign.frontend.visualisation.navigation import NavigationWidget
from histalign.frontend.visualisation.views import SliceViewer


class VisualisationMainWindow(BasicApplicationWindow):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        #
        self._saved_left_size = -1
        self._saved_right_size = -1

        self._pixmap_item = None

        #
        central_view = SliceViewer()

        self.central_view = central_view

        #
        navigation_widget = NavigationWidget()

        navigation_widget.open_image_requested.connect(self.central_view.open_image)

        self.navigation_widget = navigation_widget

        #
        information_widget = InformationWidget()

        information_widget.structures_widget.structure_checked.connect(
            central_view.contour_structure
        )
        information_widget.structures_widget.structure_unchecked.connect(
            central_view.remove_contours
        )

        self.information_widget = information_widget

        #
        left_tools_widget = CollapsibleWidgetArea("left_to_right")

        left_tools_widget.collapsed.connect(self.left_collapsed)
        left_tools_widget.expanded.connect(self.left_expanded)

        left_tools_widget.add_widget(
            navigation_widget, RESOURCES_ROOT / "icons" / "folder-icon.png"
        )

        self.left_tools_widget = left_tools_widget

        #
        right_tools_widget = CollapsibleWidgetArea("right_to_left")

        right_tools_widget.collapsed.connect(self.right_collapsed)
        right_tools_widget.expanded.connect(self.right_expanded)

        right_tools_widget.add_widget(
            information_widget,
            RESOURCES_ROOT / "icons" / "three-horizontal-lines-icon.png",
        )

        self.right_tools_widget = right_tools_widget

        #
        splitter = VisibleHandleSplitter()

        splitter.addWidget(left_tools_widget)
        splitter.addWidget(central_view)
        splitter.addWidget(right_tools_widget)

        self.setCentralWidget(splitter)

    def get_baseline_splitter_sizes(self) -> list[int]:
        width = (
            self.centralWidget().width()
            - self.centralWidget().count() * self.centralWidget().handleWidth()
        )
        unit = width // 5  # Split the view in 1-3-1, i.e. multiples of 5ths

        return [unit, 3 * unit, unit]

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)

        sizes = self.get_baseline_splitter_sizes()

        left_collapsible_width = min(sizes[0], self.left_tools_widget.maximumWidth())
        right_collapsible_width = min(sizes[2], self.right_tools_widget.maximumWidth())

        difference = (
            sizes[0] - left_collapsible_width + sizes[2] - right_collapsible_width
        )
        sizes[1] += difference

        self.centralWidget().setSizes(sizes)

    @QtCore.Slot()
    def open_project(self, project_file_path: str) -> None:
        project_path = Path(project_file_path).parent

        self.navigation_widget.set_project_root(project_path)

    @QtCore.Slot()
    def left_collapsed(self) -> None:
        sizes = self.centralWidget().sizes()
        self._saved_left_size = sizes[0]

        difference = sizes[0] - self.left_tools_widget.width()

        sizes[0] = self.left_tools_widget.width()
        sizes[1] += difference

        self.centralWidget().setSizes(sizes)

    @QtCore.Slot()
    def right_collapsed(self) -> None:
        sizes = self.centralWidget().sizes()
        self._saved_right_size = sizes[2]

        difference = sizes[2] - self.right_tools_widget.width()

        sizes[2] = self.right_tools_widget.width()
        sizes[1] += difference

        self.centralWidget().setSizes(sizes)

    @QtCore.Slot()
    def left_expanded(self) -> None:
        sizes = self.centralWidget().sizes()

        difference = self._saved_left_size - sizes[0]

        sizes[0] = self._saved_left_size
        sizes[1] -= difference

        self.centralWidget().setSizes(sizes)

    @QtCore.Slot()
    def right_expanded(self) -> None:
        sizes = self.centralWidget().sizes()

        difference = self._saved_right_size - sizes[2]

        sizes[2] = self._saved_right_size
        sizes[1] -= difference

        self.centralWidget().setSizes(sizes)
