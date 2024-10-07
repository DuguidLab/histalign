# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from functools import cached_property
import json
import os.path
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets
import numpy as np
import vedo

from histalign.backend.ccf.downloads import download_atlas
from histalign.backend.ccf.paths import get_atlas_path
from histalign.backend.io.image_conversions import convert_to_rgb32, mask_off_colour
from histalign.backend.models import (
    Orientation,
    ProjectSettings,
    Resolution,
    VolumeSettings,
)
from histalign.backend.registration.alignment import build_alignment_volume
from histalign.backend.workspace import Volume, VolumeSlicer, Workspace
from histalign.frontend.dialogs import OpenProjectDialog
from histalign.frontend.common_widgets import ProjectDirectoriesComboBox


class ViewerButtons(QtWidgets.QWidget):
    forward_button: QtWidgets.QPushButton
    backward_button: QtWidgets.QPushButton
    reset_button: QtWidgets.QPushButton

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        forward_button = QtWidgets.QPushButton()
        forward_button.setFixedSize(20, 20)
        icon = self.style().standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_TitleBarShadeButton
        )
        forward_button.setIcon(icon)

        self.forward_button = forward_button

        #
        backward_button = QtWidgets.QPushButton()
        backward_button.setFixedSize(20, 20)
        icon = self.style().standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_TitleBarUnshadeButton
        )
        backward_button.setIcon(icon)

        self.backward_button = backward_button

        #
        reset_button = QtWidgets.QPushButton()
        reset_button.setFixedSize(20, 20)
        icon = self.style().standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_BrowserReload
        )
        reset_button.setIcon(icon)

        self.reset_button = reset_button

        #
        layout = QtWidgets.QHBoxLayout()

        layout.addWidget(forward_button)
        layout.addWidget(backward_button)
        layout.addWidget(reset_button)

        self.setLayout(layout)

        #
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum
        )


class VolumeView(QtWidgets.QLabel):
    square_pixmap: QtGui.QPixmap

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setContentsMargins(0, 0, 0, 0)

    def set_image(
        self,
        image: np.ndarray,
        format_: QtGui.QImage.Format = QtGui.QImage.Format.Format_Grayscale8,
    ) -> None:
        larger_dimension = max(image.shape[0], image.shape[1])
        smaller_dimension = min(image.shape[0], image.shape[1])
        constant_values = ((2**8 - 1) << 24, (2**8 - 1) << 24)

        if larger_dimension != smaller_dimension:
            padding = larger_dimension - smaller_dimension

            if larger_dimension == image.shape[0]:
                image = np.pad(
                    image,
                    ((0, 0), (padding // 2, padding // 2 + int(padding % 2))),
                    constant_values=constant_values,
                )
            else:
                image = np.pad(
                    image,
                    ((padding // 2, padding // 2 + int(padding % 2)), (0, 0)),
                    constant_values=constant_values,
                )

        self.square_pixmap = QtGui.QPixmap.fromImage(
            QtGui.QImage(
                image.tobytes(),
                image.shape[1],
                image.shape[0],
                image.shape[1] * image.itemsize,
                format_,
            )
        )

        self.setPixmap(self.square_pixmap)

        self.resize(self.size())

    def resize(self, size: QtCore.QSize) -> None:
        smallest_dimension = min(size.width(), size.height())
        super().resize(smallest_dimension, smallest_dimension)

        self.setPixmap(self.square_pixmap.scaled(self.size()))


class VolumeViewer(QtWidgets.QWidget):
    reference_slicer: VolumeSlicer
    visualisation_slicer: VolumeSlicer
    settings: VolumeSettings

    buttons: ViewerButtons
    volume_view: VolumeView

    max_offset_reached: QtCore.Signal = QtCore.Signal()
    max_offset_left: QtCore.Signal = QtCore.Signal()
    min_offset_reached: QtCore.Signal = QtCore.Signal()
    min_offset_left: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        orientation: Orientation,
        resolution: Optional[Resolution] = Resolution.MICRONS_100,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        #
        dummy_volume = vedo.Volume(np.zeros(shape=(10, 10, 10), dtype=np.uint8))

        self.reference_slicer = VolumeSlicer(volume=dummy_volume)
        self.visualisation_slicer = VolumeSlicer(volume=dummy_volume)
        self.settings = VolumeSettings(
            orientation=orientation,
            resolution=resolution,
            shape=(1, 1, 1),
        )

        #
        buttons = ViewerButtons()

        buttons.forward_button.clicked.connect(self.increase_offset)
        self.max_offset_reached.connect(
            lambda: buttons.forward_button.setEnabled(False)
        )
        self.max_offset_left.connect(lambda: buttons.forward_button.setEnabled(True))
        buttons.backward_button.clicked.connect(self.decrease_offset)
        self.min_offset_reached.connect(
            lambda: buttons.backward_button.setEnabled(False)
        )
        self.min_offset_left.connect(lambda: buttons.backward_button.setEnabled(True))
        buttons.reset_button.clicked.connect(self.reset_offset)

        self.buttons = buttons

        #
        volume_view = VolumeView()
        volume_view.setContentsMargins(0, 0, 0, 0)

        self.volume_view = volume_view

        #
        layout = QtWidgets.QVBoxLayout()

        layout.addWidget(buttons, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(volume_view, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        self.setLayout(layout)

        #
        self.update_slice()

        self.installEventFilter(self)

    @property
    def max_offset(self) -> int:
        match self.settings.orientation:
            case Orientation.CORONAL:
                maximum = (
                    self.settings.shape[0] // 2 + (self.settings.shape[0] % 2 != 0) - 1
                )
            case Orientation.HORIZONTAL:
                maximum = (
                    self.settings.shape[1] // 2 + (self.settings.shape[1] % 2 != 0) - 1
                )
            case Orientation.SAGITTAL:
                maximum = (
                    self.settings.shape[2] // 2 + (self.settings.shape[2] % 2 != 0) - 1
                )
            case _:
                # Should be impossible thanks to pydantic
                raise Exception("Panic: assert not reached")

        return maximum

    @property
    def min_offset(self) -> int:
        match self.settings.orientation:
            case Orientation.CORONAL:
                minimum = -self.settings.shape[0] // 2
            case Orientation.HORIZONTAL:
                minimum = -self.settings.shape[1] // 2
            case Orientation.SAGITTAL:
                minimum = -self.settings.shape[2] // 2
            case _:
                # Should be impossible thanks to pydantic
                raise Exception("Panic: assert not reached")

        return minimum

    def change_reference_volume(self, new_volume: Volume | vedo.Volume) -> None:
        self.reference_slicer.volume = new_volume
        self.visualisation_slicer.volume = vedo.Volume(
            np.zeros(shape=new_volume.shape, dtype=np.uint8)
        )

        self.settings.shape = new_volume.shape
        self.update_slice()

    def change_visualisation_volume(self, new_volume: Volume | vedo.Volume) -> None:
        if np.not_equal(
            np.array(new_volume.shape),
            np.array(self.reference_slicer.volume.shape),
        ).any():
            raise ValueError(
                f"Invalid visualisation volume shape (reference: "
                f"{self.reference_slicer.volume.shape}, received: {new_volume.shape})."
            )

        self.visualisation_slicer.volume = new_volume
        self.update_slice()

    def update_slice(self) -> None:
        array = self.reference_slicer.slice(self.settings)

        reference_array = convert_to_rgb32(array)

        visualisation_array = convert_to_rgb32(
            self.visualisation_slicer.slice(self.settings)
        )
        # Turn to yellow
        visualisation_array = mask_off_colour(visualisation_array, "blue")

        image_array = np.where(
            visualisation_array - ((2**8 - 1) << 24) > 0,
            visualisation_array,
            reference_array,
        )
        # image_array = reference_array

        self.volume_view.set_image(
            image_array, format_=QtGui.QImage.Format.Format_RGB32
        )

    def allocate_space(self, size: QtCore.QSize) -> None:
        available_height = (
            size.height()
            - self.buttons.sizeHint().height()
            - self.layout().contentsMargins().top()
            - self.layout().contentsMargins().bottom()
            - self.layout().spacing()
        )
        self.volume_view.resize(QtCore.QSize(size.width(), available_height))

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent):
        match event.type():
            # Enable scrolling of the view to change the offset
            case QtCore.QEvent.Type.Wheel:
                if isinstance(self.childAt(event.position().toPoint()), VolumeView):
                    if event.angleDelta().y() > 0:  # Scroll up
                        self.increase_offset()
                        return True
                    elif event.angleDelta().y() < 0:  # Scroll down
                        self.decrease_offset()
                        return True

        return super().eventFilter(watched, event)

    @QtCore.Slot()
    def increase_offset(self) -> None:
        if self.settings.offset < self.max_offset:
            if self.settings.offset == self.min_offset:
                self.min_offset_left.emit()

            self.settings.offset += 1

            if self.settings.offset >= self.max_offset:
                self.max_offset_reached.emit()

            self.update_slice()

    @QtCore.Slot()
    def decrease_offset(self) -> None:
        if self.settings.offset > self.min_offset:
            if self.settings.offset == self.max_offset:
                self.max_offset_left.emit()

            self.settings.offset -= 1

            if self.settings.offset <= self.min_offset:
                self.min_offset_reached.emit()

            self.update_slice()

    @QtCore.Slot()
    def reset_offset(self) -> None:
        if self.settings.offset == 0:
            return

        self.settings.offset = 0

        self.max_offset_left.emit()
        self.min_offset_left.emit()

        self.update_slice()


class FMRIViewer(QtWidgets.QWidget):
    volume_viewers: tuple[VolumeViewer, VolumeViewer, VolumeViewer]

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        volume_viewers = (
            VolumeViewer(orientation=Orientation.CORONAL, parent=self),
            VolumeViewer(orientation=Orientation.HORIZONTAL, parent=self),
            VolumeViewer(orientation=Orientation.SAGITTAL, parent=self),
        )

        self.volume_viewers = volume_viewers

        #
        layout = QtWidgets.QGridLayout()

        layout.addWidget(volume_viewers[0], 0, 0, 1, 1)
        layout.addWidget(volume_viewers[1], 0, 1, 1, 1)
        layout.addWidget(volume_viewers[2], 1, 0, 1, 1)

        self.setLayout(layout)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        grid_size = QtCore.QSize(
            (
                self.size().width()
                - self.layout().contentsMargins().left()
                - self.layout().contentsMargins().right()
                - self.layout().spacing()
            )
            // 2,
            (
                self.size().height()
                - self.layout().contentsMargins().top()
                - self.layout().contentsMargins().bottom()
                - self.layout().spacing()
            )
            // 2,
        )
        grid_size = QtCore.QSize(
            min(grid_size.width(), grid_size.height()),
            min(grid_size.width(), grid_size.height()),
        )

        for viewer in self.volume_viewers:
            viewer.allocate_space(grid_size)


class VisualiseControls(QtWidgets.QWidget):
    directories_combo_box: ProjectDirectoriesComboBox
    visualise_button: QtWidgets.QPushButton

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        directories_combo_box = ProjectDirectoriesComboBox()

        self.directories_combo_box = directories_combo_box

        #
        form_layout = QtWidgets.QFormLayout()
        form_layout.addRow("Directory", directories_combo_box)

        #
        visualise_button = QtWidgets.QPushButton("Visualise")

        self.visualise_button = visualise_button

        #
        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(form_layout)
        layout.addWidget(
            visualise_button,
            alignment=QtCore.Qt.AlignmentFlag.AlignTop
            | QtCore.Qt.AlignmentFlag.AlignRight,
        )

        self.setLayout(layout)


class MainMenuBar(QtWidgets.QMenuBar):
    open_project_requested: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        file_menu = self.addMenu("&File")

        open_project_action = QtGui.QAction("Open p&roject", self)
        open_project_action.triggered.connect(self.open_project_requested.emit)

        file_menu.addAction(open_project_action)


class VisualisationMainWindow(QtWidgets.QMainWindow):
    project_directory: Path

    project_loaded: bool = False

    controls: VisualiseControls
    fmri_viewer: FMRIViewer

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        main_menu_bar = MainMenuBar()
        main_menu_bar.open_project_requested.connect(self.show_open_project_dialog)

        self.setMenuBar(main_menu_bar)

        #
        controls = VisualiseControls()

        controls.visualise_button.clicked.connect(self.visualise)

        self.controls = controls

        #
        fmri_viewer = FMRIViewer()

        self.fmri_viewer = fmri_viewer

        #
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(controls, alignment=QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addWidget(fmri_viewer)

        #
        central_widget = QtWidgets.QWidget()
        central_widget.setLayout(layout)
        central_widget.setEnabled(False)

        self.setCentralWidget(central_widget)

    @QtCore.Slot()
    def visualise(self) -> None:
        directory_hash = f"{Workspace.generate_directory_hash(self.controls.directories_combo_box.currentText())}"

        alignment_directory = f"{self.project_directory}{os.sep}{directory_hash}"

        alignment_volume = build_alignment_volume(alignment_directory)
        for viewer in self.fmri_viewer.volume_viewers:
            viewer.change_visualisation_volume(alignment_volume)

    @QtCore.Slot()
    def show_open_project_dialog(self) -> None:
        dialog = OpenProjectDialog(self)
        dialog.submitted.connect(self.open_project)
        dialog.open()

    @QtCore.Slot()
    def open_project(self, project_file_path: str) -> None:
        self.project_directory = Path(project_file_path).parent

        self.controls.directories_combo_box.parse_project(self.project_directory)

        with open(project_file_path) as handle:
            contents = json.load(handle)

        resolution = ProjectSettings(**contents["project_settings"]).resolution

        reference_path = get_atlas_path(resolution)
        if not os.path.exists(reference_path):
            download_atlas(reference_path)

        reference_volume = Volume(
            file_path=reference_path, resolution=resolution, convert_dtype=np.uint8
        )

        for viewer in self.fmri_viewer.volume_viewers:
            viewer.change_reference_volume(reference_volume)

        self.centralWidget().setEnabled(True)
        self.project_loaded = True
