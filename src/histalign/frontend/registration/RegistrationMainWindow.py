# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
import os
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.models import ProjectSettings
from histalign.backend.workspace import AtlasHandler, Workspace
from histalign.frontend.registration.AlignmentButtonDockWidget import (
    AlignmentButtonDockWidget,
)
from histalign.frontend.registration.AlignmentWidget import AlignmentWidget
from histalign.frontend.registration.AlphaDockWidget import AlphaDockWidget
from histalign.frontend.registration.dialogs import (
    AtlasChangeDialog,
    AtlasProgressDialog,
    InvalidProjectFileDialog,
    ProjectCreateDialog,
    SaveProjectConfirmationDialog,
)
from histalign.frontend.registration.MainMenuBar import MainMenuBar
from histalign.frontend.registration.SettingsDockWidget import SettingsDockWidget
from histalign.frontend.registration.ThumbnailDockWidget import ThumbnailDockWidget


class RegistrationMainWindow(QtWidgets.QMainWindow):
    workspace: Optional[Workspace] = None

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)

        self.setWindowTitle("Histalign - Registration")

        # Menu bar
        menu_bar = MainMenuBar()
        menu_bar.create_project_requested.connect(self.show_project_create_dialog)
        menu_bar.open_project_requested.connect(self.show_project_open_dialog)
        menu_bar.change_atlas_requested.connect(
            self.show_change_atlas_resolution_dialog
        )
        menu_bar.open_image_directory_requested.connect(
            self.show_open_image_directory_dialog
        )

        self.setMenuBar(menu_bar)

        # Central widget (AlignmentWidget)
        alignment_widget = AlignmentWidget()

        self.setCentralWidget(alignment_widget)

        # Left dock widget (ThumbnailDockWidget)
        thumbnail_dock_widget = ThumbnailDockWidget()
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, thumbnail_dock_widget)

        # Top dock widget (AlphaDockWidget)
        alpha_dock_widget = AlphaDockWidget()
        alpha_dock_widget.alpha_slider.valueChanged.connect(
            alignment_widget.update_histology_alpha
        )

        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, alpha_dock_widget)

        # Right dock widget (SettingsDockWidget)
        settings_dock_widget = SettingsDockWidget()
        settings_dock_widget.volume_settings_widget.setEnabled(False)
        settings_dock_widget.volume_settings_widget.values_changed.connect(
            alignment_widget.reslice_volume
        )
        settings_dock_widget.histology_settings_widget.setEnabled(False)
        settings_dock_widget.histology_settings_widget.values_changed.connect(
            alignment_widget.update_histology_pixmap
        )

        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, settings_dock_widget)

        # Bottom dock widget (AlignmentButtonDockWidget)
        alignment_button_dock_widget = AlignmentButtonDockWidget()
        alignment_button_dock_widget.save_button.setEnabled(False)
        alignment_button_dock_widget.reset_volume.setEnabled(False)
        alignment_button_dock_widget.reset_volume.clicked.connect(
            settings_dock_widget.volume_settings_widget.reset_to_defaults
        )
        alignment_button_dock_widget.reset_histology.setEnabled(False)
        alignment_button_dock_widget.reset_histology.clicked.connect(
            settings_dock_widget.histology_settings_widget.reset_to_defaults
        )

        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, alignment_button_dock_widget)

        # Dock widget areas
        self.setCorner(QtCore.Qt.TopLeftCorner, QtCore.Qt.LeftDockWidgetArea)
        self.setCorner(QtCore.Qt.BottomLeftCorner, QtCore.Qt.LeftDockWidgetArea)
        self.setCorner(QtCore.Qt.TopRightCorner, QtCore.Qt.RightDockWidgetArea)
        self.setCorner(QtCore.Qt.BottomRightCorner, QtCore.Qt.RightDockWidgetArea)

    def connect_workspace(self) -> None:
        # TODO: Also connect reset button logic
        save_button = self.findChild(AlignmentButtonDockWidget).save_button
        save_button.clicked.connect(self.workspace.save_alignment)

        self.centralWidget().volume_scale_ratio_changed.connect(
            lambda x: self.workspace.aggregate_settings({"volume_scaling_factor": x})
        )
        self.centralWidget().histology_scale_ratio_changed.connect(
            lambda x: self.workspace.aggregate_settings({"histology_scaling_factor": x})
        )

        settings_widget = self.findChild(SettingsDockWidget)
        settings_widget.volume_settings_widget.values_changed.connect(
            self.workspace.aggregate_settings
        )
        settings_widget.histology_settings_widget.values_changed.connect(
            self.workspace.aggregate_settings
        )

    def handle_atlas(self, atlas_resolution: int) -> None:
        handler = AtlasHandler(atlas_resolution, self.centralWidget().volume_manager)

        thread = QtCore.QThread()
        thread.started.connect(handler.handle_atlas)
        handler.atlas_loaded.connect(thread.quit)

        dialog = AtlasProgressDialog(self)
        dialog.canceled.connect(thread.exit)
        handler.atlas_downloaded.connect(lambda: dialog.setLabelText("Loading atlas"))
        handler.atlas_loaded.connect(dialog.close)
        handler.atlas_loaded.connect(self.open_atlas_in_aligner)

        handler.moveToThread(thread)

        thread.start()
        dialog.exec()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.workspace is not None:
            match SaveProjectConfirmationDialog(self).exec():
                case QtWidgets.QMessageBox.Save:
                    self.workspace.save()
                    event.accept()
                case QtWidgets.QMessageBox.Discard:
                    event.accept()
                case QtWidgets.QMessageBox.Cancel:
                    event.ignore()

            self.workspace.stop()

    @QtCore.Slot()
    def show_project_create_dialog(self) -> None:
        if self.workspace is not None:
            match SaveProjectConfirmationDialog(self).exec():
                case QtWidgets.QMessageBox.Save:
                    self.workspace.save()
                case QtWidgets.QMessageBox.Cancel:
                    return

        dialog = ProjectCreateDialog(self)
        dialog.submitted.connect(self.create_project)
        dialog.open()

    @QtCore.Slot()
    def show_project_open_dialog(self) -> None:
        if self.workspace is not None:
            match SaveProjectConfirmationDialog(self).exec():
                case QtWidgets.QMessageBox.Save:
                    self.workspace.save()
                case QtWidgets.QMessageBox.Cancel:
                    return

        project_file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select a project file",
            os.getcwd(),
            "Project (project.json)",
            options=QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )

        if project_file != "":
            self.open_project(project_file)

    @QtCore.Slot()
    def show_change_atlas_resolution_dialog(self) -> None:
        dialog = AtlasChangeDialog(self.workspace.atlas_resolution, self)
        dialog.submitted.connect(self.change_atlas_resolution)
        dialog.open()

    @QtCore.Slot()
    def show_open_image_directory_dialog(self) -> None:
        image_directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select an image directory",
            os.getcwd(),
            options=QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )

        if image_directory != "":
            self.open_image_directory(image_directory)

    @QtCore.Slot()
    def create_project(self, project_settings: dict) -> None:
        project_settings = ProjectSettings(**project_settings)

        self.workspace = Workspace(project_settings)
        self.connect_workspace()

        self.handle_atlas(self.workspace.atlas_resolution)

        self.menuBar().opened_project()

    @QtCore.Slot()
    def open_project(self, project_path: str) -> None:
        try:
            self.workspace = Workspace.load(project_path)
        except ValueError:
            return InvalidProjectFileDialog(self).open()

        self.connect_workspace()

        self.handle_atlas(self.workspace.atlas_resolution)

        if self.workspace.last_parsed_directory is not None:
            self.open_image_directory(self.workspace.last_parsed_directory)

        if self.workspace.current_aligner_image_hash is not None:
            self.open_image_in_aligner(
                self.workspace.current_aligner_image_index, force_open=True
            )

        self.menuBar().opened_project()

    @QtCore.Slot()
    def change_atlas_resolution(self, resolution: int) -> None:
        old_resolution = self.workspace.atlas_resolution
        old_offset = self.workspace.alignment_parameters.offset

        self.workspace.update_atlas_resolution(resolution)

        self.handle_atlas(self.workspace.atlas_resolution)

        settings_widget = self.findChild(SettingsDockWidget).volume_settings_widget
        settings_widget.settings.origin = None
        settings_widget.offset_spin_box.setValue(
            int(round(old_offset * (old_resolution / resolution)))
        )

    @QtCore.Slot()
    def open_image_directory(self, image_directory_path: str) -> None:
        thumbnail_widget = self.findChild(ThumbnailDockWidget)
        thumbnail_widget.update_thumbnails(self.workspace)
        thumbnail_widget.widget().flush_thumbnails()
        thumbnail_widget.widget().open_image.connect(self.open_image_in_aligner)

        self.workspace.parse_image_directory(image_directory_path)

    @QtCore.Slot()
    def open_atlas_in_aligner(self) -> None:
        try:
            self.centralWidget().update_volume_pixmap()
        except ValueError as error:
            self.logger.error("Could not open atlas volume.")
            self.logger.error(error)
            return

        self.findChild(AlignmentButtonDockWidget).reset_volume.setEnabled(True)

        settings_widget = self.findChild(SettingsDockWidget).volume_settings_widget
        settings_widget.setEnabled(True)
        # TODO: Use the right shape index based on slice orientation
        settings_widget.set_offset_spin_box_limits(
            minimum=-self.centralWidget().volume_manager.shape[2] // 2,
            maximum=self.centralWidget().volume_manager.shape[2] // 2,
        )

        # Easiest way to trigger scale ratio calculations
        self.centralWidget().resizeEvent(
            QtGui.QResizeEvent(self.centralWidget().size(), self.centralWidget().size())
        )

    @QtCore.Slot()
    def open_image_in_aligner(self, index: int, force_open: bool = False) -> None:
        if self.workspace.current_aligner_image_index == index and not force_open:
            return

        image = self.workspace.get_image(index)
        if image is None:
            self.logger.error(
                f"Failed retrieving image at index {index}, index out of range."
            )
            return

        self.centralWidget().update_histological_slice(image)
        self.centralWidget().update_histology_alpha(
            self.findChild(AlphaDockWidget).alpha_slider.value()
        )
        self.findChild(AlignmentButtonDockWidget).save_button.setEnabled(True)
        self.findChild(AlignmentButtonDockWidget).reset_histology.setEnabled(True)
        self.findChild(SettingsDockWidget).histology_settings_widget.setEnabled(True)
