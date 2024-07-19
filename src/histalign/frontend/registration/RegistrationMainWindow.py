# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
import typing

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.ccf.allen_downloads import get_atlas_path
from histalign.backend.models import AlignmentParameterAggregator
from histalign.backend.workspace import Workspace
from histalign.frontend.registration.AlignmentButtonDockWidget import (
    AlignmentButtonDockWidget,
)
from histalign.frontend.registration.AlignmentWidget import AlignmentWidget
from histalign.frontend.registration.AlphaDockWidget import AlphaDockWidget
from histalign.frontend.registration.dialogs import (
    NoActiveProjectDialog,
    ProjectCreateDialog,
)
from histalign.frontend.registration.MainMenuBar import MainMenuBar
from histalign.frontend.registration.SettingsDockWidget import SettingsDockWidget
from histalign.frontend.registration.ThumbnailDockWidget import ThumbnailDockWidget


class RegistrationMainWindow(QtWidgets.QMainWindow):
    alignment_parameters: AlignmentParameterAggregator
    workspace: typing.Optional[Workspace]

    thumbnail_dock_widget: ThumbnailDockWidget
    settings_dock_widget: SettingsDockWidget

    def __init__(
        self,
        fullscreen: bool,
        parent: typing.Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)

        self.setWindowTitle("Histalign - Registration")

        # Menu bar
        menu_bar = MainMenuBar()
        menu_bar.create_project_request.connect(self.show_project_create_dialog)
        menu_bar.open_project.connect(self.open_project)
        menu_bar.open_image_directory.connect(self.open_image_directory)
        menu_bar.open_atlas.connect(self.open_atlas_volume)
        self.setMenuBar(menu_bar)

        self.workspace = None

        # Set up alignment widget
        alignment_widget = AlignmentWidget(self)

        self.setCentralWidget(alignment_widget)

        # Dock widgets
        self.setCorner(QtCore.Qt.TopLeftCorner, QtCore.Qt.LeftDockWidgetArea)
        self.setCorner(QtCore.Qt.BottomLeftCorner, QtCore.Qt.LeftDockWidgetArea)
        self.setCorner(QtCore.Qt.TopRightCorner, QtCore.Qt.RightDockWidgetArea)
        self.setCorner(QtCore.Qt.BottomRightCorner, QtCore.Qt.RightDockWidgetArea)

        # Set up thumbnail widget (left)
        self.thumbnail_dock_widget = ThumbnailDockWidget(self)

        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.thumbnail_dock_widget)

        # Set up alpha widget (top)
        alpha_dock_widget = AlphaDockWidget(self)
        alpha_dock_widget.alpha_slider.valueChanged.connect(
            alignment_widget.update_histology_alpha
        )
        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, alpha_dock_widget)

        # Set up the settings widget (right)
        self.settings_dock_widget = SettingsDockWidget()
        self.settings_dock_widget.volume_settings_widget.values_changed.connect(
            alignment_widget.reslice_volume
        )
        self.settings_dock_widget.histology_settings_widget.values_changed.connect(
            alignment_widget.update_histology_pixmap
        )

        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.settings_dock_widget)

        # Set up alignment buttons (bottom)
        alignment_button_dock_widget = AlignmentButtonDockWidget()
        alignment_button_dock_widget.save_button.setEnabled(False)
        alignment_button_dock_widget.reset_volume.clicked.connect(
            self.settings_dock_widget.volume_settings_widget.reset_to_defaults
        )
        alignment_button_dock_widget.reset_histology.clicked.connect(
            self.settings_dock_widget.histology_settings_widget.reset_to_defaults
        )
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, alignment_button_dock_widget)

        if fullscreen:
            self.showMaximized()

    @QtCore.Slot()
    def show_project_create_dialog(self) -> None:
        dialog = ProjectCreateDialog(self)
        dialog.submitted.connect(self.create_project)
        dialog.open()

    @QtCore.Slot()
    def create_project(self, project_settings: dict) -> None:
        workspace = Workspace(
            project_settings["resolution"], project_settings["directory"]
        )
        self.workspace = workspace
        self.connect_workspace()

        self.open_atlas_volume(get_atlas_path(project_settings["resolution"]))

        self.thumbnail_dock_widget.widget().open_image.connect(
            self.open_image_in_aligner
        )

    @QtCore.Slot()
    def open_project(self, project_path: str) -> None:
        try:
            self.workspace = Workspace.load(project_path)
            self.connect_workspace()
        except ValueError:
            message_box = QtWidgets.QMessageBox(self)
            message_box.setText(f"Invalid project file.")
            message_box.open()
            return

        self.thumbnail_dock_widget.widget().open_image.connect(
            self.open_image_in_aligner
        )

    @QtCore.Slot()
    def open_image_directory(self, image_directory: str) -> None:
        if not self.ensure_workspace("open an image directory"):
            return

        self.thumbnail_dock_widget.widget().flush_thumbnails()
        self.workspace.parse_image_directory(image_directory)
        self.thumbnail_dock_widget.update_thumbnails(self.workspace)

    @QtCore.Slot()
    def open_atlas_volume(self, volume_path: str) -> None:
        try:
            self.centralWidget().load_volume(volume_path)
        except ValueError:
            self.logger.error("Could not open atlas volume.")
            return

        self.findChild(AlignmentWidget).volume_scale_ratio_changed.connect(
            lambda x: self.workspace.aggregate_settings({"volume_scaling_factor": x})
        )
        self.settings_dock_widget.volume_settings_widget.set_offset_spin_box_limits(
            minimum=-self.centralWidget().volume_manager.shape[2] // 2,
            maximum=self.centralWidget().volume_manager.shape[2] // 2,
        )
        self.centralWidget().resizeEvent(
            QtGui.QResizeEvent(self.centralWidget().size(), self.centralWidget().size())
        )

    @QtCore.Slot()
    def open_image_in_aligner(self, index: int) -> None:
        array = self.workspace.get_image(index)
        if array is not None:
            self.centralWidget().update_histological_slice(array)
            self.findChild(AlignmentWidget).histology_scale_ratio_changed.connect(
                lambda x: self.workspace.aggregate_settings(
                    {"histology_scaling_factor": x}
                )
            )
            self.findChild(AlignmentButtonDockWidget).save_button.setEnabled(True)
        else:
            self.logger.error(
                f"Failed getting image at index {index} from the workspace."
            )

    @QtCore.Slot()
    def save_project(self) -> None:
        self.workspace.save()

    def update_aggregator(self, updates: dict[str, typing.Any]) -> None:
        new_aggregator = self.alignment_parameters.model_copy(update=updates)
        AlignmentParameterAggregator.model_validate(new_aggregator)
        self.alignment_parameters = new_aggregator

    def ensure_workspace(self, action: str) -> bool:
        if self.workspace is None:
            dialog = NoActiveProjectDialog(action, self)
            dialog.open()
            return False
        return True

    def connect_workspace(self) -> None:
        alignment_button_widget = self.findChild(AlignmentButtonDockWidget)
        alignment_button_widget.save_button.clicked.connect(
            self.workspace.save_alignment
        )

        settings_widget = self.findChild(SettingsDockWidget)
        settings_widget.volume_settings_widget.values_changed.connect(
            self.workspace.aggregate_settings
        )
        settings_widget.histology_settings_widget.values_changed.connect(
            self.workspace.aggregate_settings
        )

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.workspace is not None:
            self.save_project()
