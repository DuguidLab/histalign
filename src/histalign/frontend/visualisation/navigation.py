# SPDX-FileCopyrightText: 2025-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.io import (
    ALIGNMENT_FILE_NAME_PATTERN,
    load_alignment_settings,
    RESOURCES_ROOT,
)
from histalign.backend.workspace import HistologySlice
from histalign.frontend.common_widgets import (
    FileWidget,
    HASHED_DIRECTORY_NAME_PATTERN,
    HoverButton,
    StackWidget,
)
from histalign.frontend.pyside_helpers import connect_single_shot_slot
from histalign.frontend.registration.thumbnails import (
    ThumbnailsContainerWidget,
    ThumbnailWidget,
)

_module_logger = logging.getLogger(__name__)


class NavigationWidget(QtWidgets.QWidget):
    project_root: Path | None = None

    open_image_requested: QtCore.Signal = QtCore.Signal(Path)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        #
        header = NavigationHeader()

        self.header = header

        #
        area = NavigationArea()

        header.back_requested.connect(area.go_back)
        header.forward_requested.connect(area.go_forward)

        area.layer_put.connect(header.expand)
        header.back_requested.connect(area.layer_popped.emit)

        area.open_image_requested.connect(self.open_image_requested.emit)

        self.area = area

        #
        layout = QtWidgets.QVBoxLayout()

        layout.addWidget(header)
        layout.addWidget(area)

        self.setLayout(layout)

    def set_project_root(self, path: Path) -> None:
        self.project_root = path
        self.area.project_root = path


class NavigationHeader(QtWidgets.QWidget):
    back_requested: QtCore.Signal = QtCore.Signal()
    forward_requested: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        #
        self._length = 0
        self._parts = []

        #
        back_button = HoverButton(
            icon_path=RESOURCES_ROOT / "icons" / "thin-arrow-left-icon.png"
        )

        back_button.clicked.connect(self.reduce)
        back_button.clicked.connect(self.back_requested.emit)

        back_button.setEnabled(False)

        self.back_button = back_button

        #
        forward_button = HoverButton(
            icon_path=RESOURCES_ROOT / "icons" / "thin-arrow-right-icon.png"
        )

        forward_button.clicked.connect(self.expand)
        forward_button.clicked.connect(self.forward_requested.emit)

        forward_button.setEnabled(False)

        self.forward_button = forward_button

        #
        label = QtWidgets.QLabel()

        label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.label = label

        #
        layout = QtWidgets.QHBoxLayout()

        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(back_button)
        layout.addWidget(forward_button)
        layout.addWidget(label, stretch=1)

        self.setLayout(layout)

    def update_title(self) -> None:
        title = "/".join(self._parts[: self._length])

        self.label.setText(title)

    @QtCore.Slot()
    def expand(self, text: str) -> None:
        if text:
            self._parts[self._length :] = [text]
        self._length += 1

        self.back_button.setEnabled(True)
        if self._length >= len(self._parts):
            self.forward_button.setEnabled(False)

        self.update_title()

    @QtCore.Slot()
    def reduce(self) -> None:
        self._length -= 1

        if self._length < 1:
            self.back_button.setEnabled(False)
        if len(self._parts) > 0:
            self.forward_button.setEnabled(True)

        self.update_title()


class NavigationArea(QtWidgets.QScrollArea):
    project_root: Optional[Path] = None
    parsed_slice: bool = False
    parsed_brain: bool = False

    layer_put: QtCore.Signal = QtCore.Signal(str)
    layer_popped: QtCore.Signal = QtCore.Signal()
    open_image_requested: QtCore.Signal = QtCore.Signal(Path)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        #
        dimension_picker_container = DimensionPickerContainer()

        dimension_picker_container.slices_requested.connect(self.parse_slice_folders)
        dimension_picker_container.slices_requested.connect(self.show_slice_folders)

        dimension_picker_container.brains_requested.connect(self.parse_brain_files)
        dimension_picker_container.brains_requested.connect(self.show_brain_files)

        self.dimension_picker_widget = dimension_picker_container

        #
        slice_folder_container = SliceFolderContainer()

        self.slice_folder_container = slice_folder_container

        #
        brain_file_container = BrainFileContainer()

        self.brain_file_container = brain_file_container

        #
        self.thumbnails_widget = None

        #
        stack_widget = StackWidget()

        stack_widget.put(dimension_picker_container)

        self.setWidget(stack_widget)

        self.stack_widget = stack_widget

        #
        self.setWidgetResizable(True)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        self.widget().setFixedWidth(self.viewport().width())

    @QtCore.Slot()
    def blow_up_folder(self, path: Path, user_friendly_path: Path) -> None:
        widget = ThumbnailsContainerWidget()

        self.stack_widget.put(widget)
        self.layer_put.emit(user_friendly_path.name)

        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        connect_single_shot_slot(
            self.layer_popped,
            lambda: self.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
            ),
        )

        index = 0
        for child_path in path.iterdir():
            if re.fullmatch(ALIGNMENT_FILE_NAME_PATTERN, child_path.name) is None:
                continue

            thumbnail = self._get_thumbnail(child_path)

            widget.layout().replaceAt(index, thumbnail)

            index += 1

        self.thumbnails_widget = widget

    @QtCore.Slot()
    def go_back(self) -> None:
        self.widget().previous()

    @QtCore.Slot()
    def go_forward(self) -> None:
        self.widget().next()

    @QtCore.Slot()
    def parse_slice_folders(self) -> None:
        if self.parsed_slice or self.project_root is None:
            return

        for path in self.project_root.iterdir():
            if re.fullmatch(HASHED_DIRECTORY_NAME_PATTERN, path.name) is None:
                continue

            with (path / "metadata.json").open() as handle:
                contents = json.load(handle)

            try:
                user_friendly_path = contents["directory_path"]
            except KeyError:
                _module_logger.error(
                    f"Could not parse original directory name from metadata.json file "
                    f"in '{path}'."
                )
                return
            user_friendly_path = Path(user_friendly_path)

            widget = self.slice_folder_container.add_folder(user_friendly_path)

            widget.clicked.connect(
                lambda x=path, y=user_friendly_path: self.blow_up_folder(x, y)
            )

        self.parsed_slice = True

    @QtCore.Slot()
    def parse_brain_files(self) -> None:
        pass

    @QtCore.Slot()
    def show_slice_folders(self) -> None:
        if self.stack_widget.in_stack(self.slice_folder_container):
            self.stack_widget.next()
        else:
            self.stack_widget.put(self.slice_folder_container)
            self.slice_folder_container.show()

        self.layer_put.emit("2D slices")

    @QtCore.Slot()
    def show_brain_files(self) -> None:
        if self.stack_widget.in_stack(self.brain_file_container):
            self.stack_widget.next()
        else:
            self.stack_widget.put(self.brain_file_container)

        self.layer_put.emit("3D volumes")

    def _get_thumbnail(self, alignment_path: Path) -> ThumbnailWidget:
        alignment_settings = load_alignment_settings(alignment_path)
        histology_path = alignment_settings.histology_path

        # TODO: Thread this in case the thumbnail cache was cleared since registration
        thumbnail_path = HistologySlice(str(histology_path)).generate_thumbnail(
            str(alignment_path.parent)
        )

        widget = ThumbnailWidget(thumbnail_path, histology_path.name)

        widget.double_clicked.connect(
            lambda: self.open_image_requested.emit(alignment_path)
        )

        return widget


class DimensionPickerContainer(QtWidgets.QWidget):
    slices_requested: QtCore.Signal = QtCore.Signal()
    brains_requested: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        #
        button_2d = HoverButton(
            icon_path=RESOURCES_ROOT / "icons" / "2d-label-icon.svg"
        )

        button_2d.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        button_2d.clicked.connect(self.slices_requested.emit)

        self.button_2d = button_2d

        #
        button_3d = HoverButton(
            icon_path=RESOURCES_ROOT / "icons" / "3d-label-icon.svg"
        )

        button_3d.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        button_3d.clicked.connect(self.brains_requested.emit)

        self.button_3d = button_3d

        #
        layout = QtWidgets.QVBoxLayout()

        layout.addWidget(button_2d)
        layout.addWidget(button_3d)

        self.setLayout(layout)


class SliceFolderContainer(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        #
        layout = QtWidgets.QVBoxLayout()

        layout.addStretch(1)

        self.setLayout(layout)

    def add_folder(self, path: Path) -> FileWidget:
        widget = FileWidget(path=path, is_folder=True)

        self.layout().insertWidget(self.layout().count() - 1, widget)

        return widget


class BrainFileContainer(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
