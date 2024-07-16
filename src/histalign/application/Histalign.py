# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
import time
import typing

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.application.AlignmentButtonDockWidget import AlignmentButtonDockWidget
from histalign.application.AlignmentParameterAggregator import (
    AlignmentParameterAggregator,
)
from histalign.application.AlignmentWidget import AlignmentWidget
from histalign.application.AlphaDockWidget import AlphaDockWidget
from histalign.application.HistologySettings import HistologySettings
from histalign.application.HistologySettingsWidget import HistologySettingsWidget
from histalign.application.MainMenuBar import MainMenuBar
from histalign.application.SettingsDockWidget import SettingsDockWidget
from histalign.application.ThumbnailDockWidget import ThumbnailDockWidget
from histalign.application.VolumeSettings import VolumeSettings
from histalign.application.VolumeSettingsWidget import VolumeSettingsWidget
from histalign.application.Workspace import Workspace


class Histalign(QtWidgets.QMainWindow):
    alignment_parameters: AlignmentParameterAggregator
    workspace: typing.Optional[Workspace]

    thumbnail_dock_widget: ThumbnailDockWidget

    def __init__(
        self,
        average_volume_file_path: str,
        fullscreen: bool,
        parent: typing.Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)

        self.setWindowTitle("Histalign")
        menu_bar = MainMenuBar()
        menu_bar.create_project.connect(self.create_project)
        menu_bar.open_project.connect(self.open_project)
        menu_bar.open_image_directory.connect(self.open_image_directory)
        self.setMenuBar(menu_bar)

        self.workspace = None

        # Set up alignment widget
        alignment_widget = AlignmentWidget(self)
        alignment_widget.load_volume(average_volume_file_path)

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
        settings_dock_widget = SettingsDockWidget()
        settings_dock_widget.volume_settings_widget.set_offset_spin_box_limits(
            minimum=-alignment_widget.volume_manager.shape[2] // 2,
            maximum=alignment_widget.volume_manager.shape[2] // 2,
        )
        settings_dock_widget.volume_settings_widget.values_changed.connect(
            alignment_widget.reslice_volume
        )
        settings_dock_widget.volume_settings_widget.values_changed.connect(
            self.aggregate_settings
        )
        settings_dock_widget.histology_settings_widget.values_changed.connect(
            alignment_widget.update_histology_pixmap
        )
        settings_dock_widget.histology_settings_widget.values_changed.connect(
            self.aggregate_settings
        )
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, settings_dock_widget)

        # Set up alignment buttons (bottom)
        alignment_button_dock_widget = AlignmentButtonDockWidget()
        alignment_button_dock_widget.save_button.clicked.connect(
            self.save_alignment_parameters
        )
        alignment_button_dock_widget.reset_volume.clicked.connect(
            settings_dock_widget.volume_settings_widget.reset_to_defaults
        )
        alignment_button_dock_widget.reset_histology.clicked.connect(
            settings_dock_widget.histology_settings_widget.reset_to_defaults
        )
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, alignment_button_dock_widget)

        if fullscreen:
            self.showMaximized()

        # Alignment parameters aggregator
        volume_size = alignment_widget.volume_pixmap.pixmap().size()
        self.alignment_parameters = AlignmentParameterAggregator(
            volume_file_path=average_volume_file_path,
            volume_pixel_width=volume_size.width(),
            volume_pixel_height=volume_size.height(),
        )

        # These need to be connected after instantiating the `alignment_parameters`
        alignment_widget.volume_scale_ratio_changed.connect(
            lambda x: self.aggregate_settings({"volume_scaling_factor": x})
        )
        alignment_widget.histology_scale_ratio_changed.connect(
            lambda x: self.aggregate_settings({"histology_scaling_factor": x})
        )

    @QtCore.Slot()
    def create_project(self, project_directory: str) -> None:
        workspace = Workspace(project_directory)
        self.workspace = workspace

        # self.thumbnail_dock_widget.set_workspace(self.workspace)
        self.thumbnail_dock_widget.widget().open_image.connect(
            self.open_image_in_aligner
        )

    @QtCore.Slot()
    def open_project(self, project_path: str) -> None:
        pass

    @QtCore.Slot()
    def open_image_directory(self, image_directory: str) -> None:
        if not self.ensure_workspace("open an image directory"):
            return

        self.thumbnail_dock_widget.widget().flush_thumbnails()
        self.workspace.parse_image_directory(image_directory)
        self.thumbnail_dock_widget.update_thumbnails(self.workspace)

    @QtCore.Slot()
    def open_image_in_aligner(self, index: int) -> None:
        array = self.workspace.get_image(index)
        if array is not None:
            self.centralWidget().update_histological_slice(array)
            self.update_aggregator(
                updates={
                    "histology_file_path": self.workspace.get_slice(index).file_path,
                }
            )
        else:
            self.logger.error(
                f"Failed getting image at index {index} from the workspace."
            )

    @QtCore.Slot()
    def aggregate_settings(
        self, settings: dict | HistologySettings | VolumeSettings
    ) -> None:
        if not isinstance(settings, dict):
            settings = settings.model_dump()

        self.update_aggregator(settings)

    @QtCore.Slot()
    def save_alignment_parameters(self) -> None:
        # TODO: Disable save button when not histology is open
        # Don't save settings if there aren't any open images
        if self.centralWidget().histology_pixmap.pixmap().isNull():
            return

        print(self.alignment_parameters.model_dump_json())
        with open("registration_parameters.json", "w") as json_handle:
            json_handle.write(self.alignment_parameters.model_dump_json())

    def update_aggregator(self, updates: dict[str, typing.Any]) -> None:
        new_aggregator = self.alignment_parameters.model_copy(update=updates)
        AlignmentParameterAggregator.model_validate(new_aggregator)
        self.alignment_parameters = new_aggregator

    def ensure_workspace(self, action: str) -> bool:
        if self.workspace is None:
            message_box = QtWidgets.QMessageBox(self)
            message_box.setText(f"You must have a project open in order to {action}.")
            message_box.open()
            return False
        return True
