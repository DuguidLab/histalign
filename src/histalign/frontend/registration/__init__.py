# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
import os
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.models import ProjectSettings
from histalign.backend.workspace import VolumeLoaderThread, Workspace
from histalign.frontend.dialogs import (
    AtlasProgressDialog,
    CreateProjectDialog,
    InvalidProjectFileDialog,
    OpenProjectDialog,
    SaveProjectConfirmationDialog,
)
from histalign.frontend.registration.alignment import (
    AlignmentButtonDockWidget,
    AlignmentWidget,
)
from histalign.frontend.registration.alpha import AlphaDockWidget
from histalign.frontend.registration.helpers import get_dummy_title_bar
from histalign.frontend.registration.settings import SettingsDockWidget
from histalign.frontend.registration.thumbnails import ThumbnailDockWidget


class MainMenuBar(QtWidgets.QMenuBar):
    create_project_requested: QtCore.Signal = QtCore.Signal()
    open_project_requested: QtCore.Signal = QtCore.Signal()
    save_project_requested: QtCore.Signal = QtCore.Signal()
    close_project_requested: QtCore.Signal = QtCore.Signal()
    open_image_directory_requested: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.action_groups = {"project_required": []}

        file_menu = self.addMenu("&File")

        create_project_action = QtGui.QAction("Create &project", self)
        create_project_action.triggered.connect(self.create_project_requested.emit)

        open_project_action = QtGui.QAction("Open p&roject", self)
        open_project_action.triggered.connect(self.open_project_requested.emit)

        save_project_action = QtGui.QAction("&Save project", self)
        save_project_action.setEnabled(False)
        save_project_action.setShortcut(QtGui.QKeySequence("Ctrl+s"))
        save_project_action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        save_project_action.triggered.connect(self.save_project_requested.emit)
        self.action_groups["project_required"].append(save_project_action)

        close_project_action = QtGui.QAction("Close pro&ject", self)
        close_project_action.triggered.connect(self.close_project_requested.emit)

        open_image_directory_action = QtGui.QAction("&Open image directory", self)
        open_image_directory_action.setEnabled(False)
        open_image_directory_action.setShortcut(QtGui.QKeySequence("Ctrl+o"))
        open_image_directory_action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        open_image_directory_action.triggered.connect(
            self.open_image_directory_requested.emit
        )
        self.action_groups["project_required"].append(open_image_directory_action)

        file_menu.addAction(create_project_action)
        file_menu.addAction(open_project_action)
        file_menu.addAction(save_project_action)
        file_menu.addAction(close_project_action)
        file_menu.addSeparator()
        file_menu.addAction(open_image_directory_action)

    def opened_project(self) -> None:
        for action in self.action_groups["project_required"]:
            action.setEnabled(True)

    def closed_project(self) -> None:
        for action in self.action_groups["project_required"]:
            action.setEnabled(False)


class RegistrationMainWindow(QtWidgets.QMainWindow):
    workspace: Optional[Workspace] = None
    workspace_loaded: bool = False
    workspace_dirtied: bool = False

    menu_bar: MainMenuBar

    alignment_widget: AlignmentWidget
    thumbnail_dock_widget: ThumbnailDockWidget
    alpha_dock_widget: AlphaDockWidget
    settings_dock_widget: SettingsDockWidget
    alignment_button_dock_widget: AlignmentButtonDockWidget

    project_closed: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)

        # Menu bar
        menu_bar = MainMenuBar()
        menu_bar.create_project_requested.connect(self.show_create_project_dialog)
        menu_bar.open_project_requested.connect(self.show_open_project_dialog)
        menu_bar.save_project_requested.connect(self.save_project)
        menu_bar.close_project_requested.connect(self.close_project)
        menu_bar.open_image_directory_requested.connect(
            self.show_open_image_directory_dialog
        )

        self.setMenuBar(menu_bar)

        self.menu_bar = menu_bar

        # Central widget (AlignmentWidget)
        alignment_widget = AlignmentWidget()

        self.setCentralWidget(alignment_widget)

        self.alignment_widget = alignment_widget

        # Left dock widget (ThumbnailDockWidget)
        thumbnail_dock_widget = ThumbnailDockWidget()
        thumbnail_dock_widget.widget().open_image.connect(self.open_image_in_aligner)

        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, thumbnail_dock_widget)

        self.thumbnail_dock_widget = thumbnail_dock_widget

        # Top dock widget (AlphaDockWidget)
        alpha_dock_widget = AlphaDockWidget()
        alpha_dock_widget.alpha_slider.valueChanged.connect(
            alignment_widget.update_histology_alpha
        )

        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, alpha_dock_widget)

        self.alpha_dock_widget = alpha_dock_widget

        # Right dock widget (SettingsDockWidget)
        settings_dock_widget = SettingsDockWidget()
        settings_dock_widget.volume_settings_widget.setEnabled(False)
        settings_dock_widget.volume_settings_widget.values_changed.connect(
            alignment_widget.update_volume_pixmap
        )
        settings_dock_widget.histology_settings_widget.setEnabled(False)
        settings_dock_widget.histology_settings_widget.values_changed.connect(
            alignment_widget.update_histology_pixmap
        )

        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, settings_dock_widget)

        self.settings_dock_widget = settings_dock_widget

        # Bottom dock widget (AlignmentButtonDockWidget)
        alignment_button_dock_widget = AlignmentButtonDockWidget()
        alignment_button_dock_widget.save_button.setEnabled(False)
        alignment_button_dock_widget.load_button.setEnabled(False)
        alignment_button_dock_widget.save_button.clicked.connect(
            lambda: alignment_button_dock_widget.load_button.setEnabled(True)
        )
        alignment_button_dock_widget.reset_volume.setEnabled(False)
        alignment_button_dock_widget.reset_volume.clicked.connect(
            settings_dock_widget.volume_settings_widget.reset_to_defaults
        )
        alignment_button_dock_widget.reset_histology.setEnabled(False)
        alignment_button_dock_widget.reset_histology.clicked.connect(
            settings_dock_widget.histology_settings_widget.reset_to_defaults
        )

        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, alignment_button_dock_widget)

        self.alignment_button_dock_widget = alignment_button_dock_widget

        # Dock widget areas
        self.setCorner(QtCore.Qt.TopLeftCorner, QtCore.Qt.LeftDockWidgetArea)
        self.setCorner(QtCore.Qt.BottomLeftCorner, QtCore.Qt.LeftDockWidgetArea)
        self.setCorner(QtCore.Qt.TopRightCorner, QtCore.Qt.RightDockWidgetArea)
        self.setCorner(QtCore.Qt.BottomRightCorner, QtCore.Qt.RightDockWidgetArea)

    def propagate_new_workspace(self) -> None:
        self.connect_workspace()
        self.share_workspace_models()

        # Sync states
        self.alignment_widget.prepare_slicer()
        self.settings_dock_widget.reload_settings()

    def connect_workspace(self) -> None:
        self.thumbnail_dock_widget.connect_workspace(self.workspace)

        self.alignment_button_dock_widget.save_button.clicked.connect(
            self.workspace.save_alignment
        )

        load_button = self.alignment_button_dock_widget.load_button
        load_button.clicked.connect(self.workspace.load_alignment)
        load_button.clicked.connect(self.share_workspace_models)
        load_button.clicked.connect(self.settings_dock_widget.reload_settings)

    def share_workspace_models(self) -> None:
        alignment_settings = self.workspace.alignment_settings
        volume_settings = self.workspace.alignment_settings.volume_settings
        histology_settings = self.workspace.alignment_settings.histology_settings

        self.alignment_widget.alignment_settings = alignment_settings
        self.alignment_widget.volume_settings = volume_settings
        self.alignment_widget.histology_settings = histology_settings

        # self.settings_dock_widget.volume_settings_widget.settings = volume_settings
        self.settings_dock_widget.volume_settings_widget.settings = (
            self.workspace.alignment_settings.volume_settings
        )
        self.settings_dock_widget.histology_settings_widget.settings = (
            histology_settings
        )

    def load_atlas(self) -> None:
        loader_thread = VolumeLoaderThread(self.alignment_widget.volume_slicer.volume)

        dialog = AtlasProgressDialog(self)

        # Using terminate rather than exit to avoid waiting for a long download/load
        dialog.canceled.connect(loader_thread.terminate)
        dialog.canceled.connect(loader_thread.wait)

        loader_thread.volume_downloaded.connect(
            lambda: dialog.setLabelText("Loading atlas")
        )
        loader_thread.volume_loaded.connect(dialog.reset)
        loader_thread.volume_loaded.connect(self.open_atlas_in_aligner)

        loader_thread.start()
        dialog.exec()

    def dirty_workspace(self) -> None:
        if self.workspace_loaded:
            self.workspace_dirtied = True

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.workspace is not None:
            if not self.workspace_dirtied:
                event.accept()
                return

            match SaveProjectConfirmationDialog(self).exec():
                case QtWidgets.QMessageBox.Save:
                    self.save_project()
                    event.accept()
                case QtWidgets.QMessageBox.Discard:
                    event.accept()
                case QtWidgets.QMessageBox.Cancel:
                    event.ignore()

            self.workspace.stop_thumbnail_generation()

    @QtCore.Slot()
    def show_create_project_dialog(self) -> Optional[CreateProjectDialog]:
        if self.workspace is not None and self.workspace_dirtied:
            match SaveProjectConfirmationDialog(self).exec():
                case QtWidgets.QMessageBox.Save:
                    self.save_project()
                case QtWidgets.QMessageBox.Cancel:
                    return None

        dialog = CreateProjectDialog(self)
        dialog.submitted.connect(self.create_project)
        dialog.open()

        return dialog

    @QtCore.Slot()
    def show_open_project_dialog(self) -> None:
        if self.workspace is not None and self.workspace_dirtied:
            match SaveProjectConfirmationDialog(self).exec():
                case QtWidgets.QMessageBox.Save:
                    self.save_project()
                case QtWidgets.QMessageBox.Cancel:
                    return

        dialog = OpenProjectDialog(self)
        dialog.submitted.connect(self.open_project)
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
            self.dirty_workspace()
            self.alignment_widget.update_histological_slice(None)
            self.thumbnail_dock_widget.widget().flush_thumbnails()
            self.workspace.parse_image_directory(image_directory)
            self.workspace.start_thumbnail_generation()

    @QtCore.Slot()
    def create_project(self, project_settings: ProjectSettings) -> None:
        self.workspace = Workspace(project_settings)
        self.propagate_new_workspace()

        self.workspace.start_thumbnail_generation()
        self.load_atlas()

        self.menu_bar.opened_project()

        self.workspace_loaded = True
        self.dirty_workspace()

    @QtCore.Slot()
    def open_project(self, project_path: str) -> None:
        try:
            self.workspace = Workspace.load(project_path)
        except ValueError:
            return InvalidProjectFileDialog(self).open()

        self.propagate_new_workspace()

        self.workspace.start_thumbnail_generation()
        self.load_atlas()

        if self.workspace.current_aligner_image_hash is not None:
            self.open_image_in_aligner(
                self.workspace.current_aligner_image_index, force_open=True
            )

        self.menu_bar.opened_project()

        self.workspace_loaded = True
        self.workspace_dirtied = False

    @QtCore.Slot()
    def save_project(self) -> None:
        self.workspace.save()
        self.workspace_dirtied = False

    @QtCore.Slot()
    def close_project(self) -> None:
        # if self.workspace is not None and self.workspace_dirtied:
        #     match SaveProjectConfirmationDialog(self).exec():
        #         case QtWidgets.QMessageBox.Save:
        #             self.save_project()
        #         case QtWidgets.QMessageBox.Cancel:
        #             return

        event = QtGui.QCloseEvent()
        self.closeEvent(event)

        if event.isAccepted():
            self.parent().open_centralised_window()

    @QtCore.Slot()
    def open_atlas_in_aligner(self) -> None:
        try:
            self.alignment_widget.update_volume_pixmap()
        except ValueError as error:
            self.logger.error("Could not open atlas volume.")
            self.logger.error(error)
            return

        self.alignment_button_dock_widget.reset_volume.setEnabled(True)

        self.workspace.alignment_settings.volume_settings.shape = (
            self.alignment_widget.volume_slicer.volume.shape
        )
        self.settings_dock_widget.volume_settings_widget.update_offset_spin_box_limits()
        self.settings_dock_widget.volume_settings_widget.setEnabled(True)

        # Easiest way to trigger scale ratio calculations
        self.alignment_widget.resizeEvent(
            QtGui.QResizeEvent(
                self.alignment_widget.size(), self.alignment_widget.size()
            )
        )

    @QtCore.Slot()
    def open_image_in_aligner(self, index: int, force_open: bool = False) -> None:
        if self.workspace.current_aligner_image_index == index and not force_open:
            return

        self.dirty_workspace()

        image = self.workspace.get_image(index)
        if image is None:
            self.logger.error(
                f"Failed retrieving image at index {index}, index out of range."
            )
            return

        self.alignment_widget.update_histological_slice(image)
        self.alignment_widget.update_histology_alpha(
            self.alpha_dock_widget.alpha_slider.value()
        )
        self.alignment_button_dock_widget.save_button.setEnabled(True)

        self.alignment_button_dock_widget.load_button.setEnabled(
            os.path.exists(self.workspace.build_alignment_path())
        )

        self.alignment_button_dock_widget.reset_histology.setEnabled(True)
        self.settings_dock_widget.histology_settings_widget.setEnabled(True)
