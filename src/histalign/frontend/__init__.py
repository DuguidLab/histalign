# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

"""This sub-package provides the frontend widgets for the user to interact with."""

import logging
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.models import ProjectSettings, VolumeExportSettings
from histalign.backend.workspace import VolumeExporterThread, Workspace
from histalign.frontend.common_widgets import DynamicThemeIcon
from histalign.frontend.dialogs import (
    ExportVolumeDialog,
    InfiniteProgressDialog,
    InvalidProjectFileDialog,
    NewProjectDialog,
    OpenImagesFolderDialog,
    OpenProjectDialog,
    SaveProjectConfirmationDialog,
)
from histalign.frontend.pyside_helpers import lua_aware_shift
from histalign.frontend.quantification import QuantificationWidget
from histalign.frontend.registration import RegistrationWidget
from histalign.frontend.visualisation import VisualisationWidget
from histalign.frontend.volume_builder import VolumeBuilderWidget
from histalign.io import clear_directory
from histalign.resources import ICONS_ROOT

_module_logger = logging.getLogger(__name__)


class HistalignMainWindow(QtWidgets.QMainWindow):
    """The main application window.

    Args:
        parent (Optional[QtWidgets.QWidget], optional): Parent of this widget.

    Signals:
        project_opened: Emitted when a project has been opened.
        project_closed: Emitted when the current project has been closed.
    """

    project_opened: QtCore.Signal = QtCore.Signal()
    project_closed: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.workspace = None
        self.workspace_is_dirty = False

        # Registration
        registration_tab = RegistrationWidget()
        self.project_opened.connect(registration_tab.project_opened.emit)
        self.project_closed.connect(registration_tab.project_closed.emit)
        self.registration_tab = registration_tab
        # Volume builder
        volume_builder_tab = VolumeBuilderWidget()
        self.project_opened.connect(volume_builder_tab.project_opened.emit)
        self.project_closed.connect(volume_builder_tab.project_closed.emit)
        self.volume_builder_tab = volume_builder_tab
        # Quantification
        quantification_tab = QuantificationWidget()
        self.project_opened.connect(quantification_tab.project_opened.emit)
        self.project_closed.connect(quantification_tab.project_closed.emit)
        self.quantification_tab = quantification_tab
        # Visualisation
        visualisation_tab = VisualisationWidget()
        self.project_opened.connect(visualisation_tab.project_opened.emit)
        self.project_closed.connect(visualisation_tab.project_closed.emit)
        self.visualisation_tab = visualisation_tab

        tab_widget = QtWidgets.QTabWidget()
        tab_widget.addTab(registration_tab, "Registration")
        tab_widget.addTab(volume_builder_tab, "Volume builder")
        tab_widget.addTab(quantification_tab, "Quantification")
        tab_widget.addTab(visualisation_tab, "Visualisation")
        tab_widget.currentChanged.connect(self.reload_project)

        self.setCentralWidget(tab_widget)

        self.build_menu_bar()
        self.build_status_bar()

        self.project_opened.connect(
            lambda: self.reload_project(tab_widget.currentIndex())
        )

        self.setWindowTitle("Histalign")

    def build_menu_bar(self) -> None:
        """Builds the menu bar for this window."""
        menu_bar = self.menuBar()

        project_required_group = []

        # File menu
        file_menu = menu_bar.addMenu("&File")

        # Project actions
        new_project_action = QtGui.QAction(
            DynamicThemeIcon(ICONS_ROOT / "add-note-icon.png"),
            "New Project",
            shortcut=QtGui.QKeySequence("CTRL+N"),
            statusTip="Create a new project",
            parent=file_menu,
        )
        new_project_action.triggered.connect(self.create_project)
        open_project_action = QtGui.QAction(
            DynamicThemeIcon(ICONS_ROOT / "desktop-file-import-icon.png"),
            "Open Project",
            shortcut=QtGui.QKeySequence("CTRL+O"),
            statusTip="Open an existing project",
            parent=file_menu,
        )
        open_project_action.triggered.connect(self.open_project)
        save_project_action = QtGui.QAction(
            DynamicThemeIcon(ICONS_ROOT / "download-to-storage-icon.png"),
            "Save Project",
            enabled=False,
            shortcut=QtGui.QKeySequence("CTRL+S"),
            statusTip="Save the current project",
            parent=file_menu,
        )
        save_project_action.triggered.connect(self.save_project)
        project_required_group.append(save_project_action)
        close_project_action = QtGui.QAction(
            DynamicThemeIcon(ICONS_ROOT / "close-square-line-icon.png"),
            "Close Project",
            enabled=False,
            shortcut=QtGui.QKeySequence("CTRL+W"),
            statusTip="Close the current project",
            parent=file_menu,
        )
        close_project_action.triggered.connect(self.close_project)
        project_required_group.append(close_project_action)

        file_menu.addActions(
            [
                new_project_action,
                open_project_action,
                save_project_action,
                close_project_action,
            ]
        )
        file_menu.addSeparator()

        # Images actions
        open_images_folder_action = QtGui.QAction(
            DynamicThemeIcon(ICONS_ROOT / "folders-icon.png"),
            "Open images folder",
            enabled=False,
            shortcut=QtGui.QKeySequence("CTRL+SHIFT+O"),
            statusTip="Open a folder of images for alignment",
            parent=file_menu,
        )
        open_images_folder_action.triggered.connect(self.open_images_folder)
        project_required_group.append(open_images_folder_action)

        file_menu.addAction(open_images_folder_action)
        file_menu.addSeparator()

        # Volume actions
        export_volume_action = QtGui.QAction(
            DynamicThemeIcon(ICONS_ROOT / "external-link-icon.png"),
            "Export volume",
            enabled=False,
            shortcut=QtGui.QKeySequence("CTRL+E"),
            statusTip="Export a volume from the current project",
            parent=file_menu,
        )
        export_volume_action.triggered.connect(self.export_volume)
        project_required_group.append(export_volume_action)

        file_menu.addAction(export_volume_action)
        file_menu.addSeparator()

        # Application actions
        quit_application_action = QtGui.QAction(
            DynamicThemeIcon(ICONS_ROOT / "logout-line-icon.png"),
            "Quit",
            shortcut=QtGui.QKeySequence("CTRL+Q"),
            statusTip="Quit the application",
            parent=file_menu,
        )
        quit_application_action.triggered.connect(self.quit)

        file_menu.addAction(quit_application_action)

        # View menu
        view_menu = menu_bar.addMenu("&View")

        # LUT - LookUp Table
        lut_menu = view_menu.addMenu("&LUT")
        lut_menu.setIcon(DynamicThemeIcon(ICONS_ROOT / "paint-roller-icon.png"))
        lut_menu.menuAction().setStatusTip("Change the histology lookup table")
        lut_menu.setEnabled(False)
        project_required_group.append(lut_menu)

        lut_action_group = QtGui.QActionGroup(view_menu)
        lut_action_group.triggered.connect(
            lambda x: self.registration_tab.alignment_widget.update_lut(
                x.text().lower()
            )
        )

        grey_lut_action = QtGui.QAction(
            "Grey",
            statusTip="Change the histology lookup table to grey",
            checkable=True,
            checked=True,
            parent=view_menu,
        )
        red_lut_action = QtGui.QAction(
            "Red",
            statusTip="Change the histology lookup table to red",
            checkable=True,
            parent=view_menu,
        )
        green_lut_action = QtGui.QAction(
            "Green",
            statusTip="Change the histology lookup table to green",
            checkable=True,
            parent=view_menu,
        )
        blue_lut_action = QtGui.QAction(
            "Blue",
            statusTip="Change the histology lookup table to blue",
            checkable=True,
            parent=view_menu,
        )
        cyan_lut_action = QtGui.QAction(
            "Cyan",
            statusTip="Change the histology lookup table to cyan",
            checkable=True,
            parent=view_menu,
        )
        magenta_lut_action = QtGui.QAction(
            "Magenta",
            statusTip="Change the histology lookup table to magenta",
            checkable=True,
            parent=view_menu,
        )
        yellow_lut_action = QtGui.QAction(
            "Yellow",
            statusTip="Change the histology lookup table to yellow",
            checkable=True,
            parent=view_menu,
        )

        lut_action_group.addAction(grey_lut_action)
        lut_action_group.addAction(red_lut_action)
        lut_action_group.addAction(green_lut_action)
        lut_action_group.addAction(blue_lut_action)
        lut_action_group.addAction(cyan_lut_action)
        lut_action_group.addAction(magenta_lut_action)
        lut_action_group.addAction(yellow_lut_action)

        lut_menu.addActions(
            [
                grey_lut_action,
                red_lut_action,
                green_lut_action,
                blue_lut_action,
                cyan_lut_action,
                magenta_lut_action,
                yellow_lut_action,
            ]
        )

        # Connect enable/disable logic
        self.project_opened.connect(
            lambda: list(map(lambda x: x.setEnabled(True), project_required_group))
        )
        self.project_closed.connect(
            lambda: list(map(lambda x: x.setEnabled(False), project_required_group))
        )

    def build_status_bar(self) -> None:
        """Builds the status bar for this window."""
        status_bar = self.statusBar()

        # Style it with a top border
        border_colour = lua_aware_shift(status_bar.palette().window().color()).getRgb()
        status_bar.setStyleSheet(
            f"""
            QStatusBar {{ 
                border-top: 1px solid rgba{border_colour};
                margin-top: -1px;
            }}
            """
        )

    def save_guard_project(self) -> bool:
        """Prompts the user for a save/discard/cancel action on closing the project.

        Note the dialog is only shown if the user has modified the workspace (e.g.,
        calling this right after opening a project will always return True).

        Returns:
            bool: True if the user saved/discarded, False if they cancelled.
        """
        if not self.workspace_is_dirty:
            return True

        match SaveProjectConfirmationDialog(self).exec():
            case QtWidgets.QMessageBox.StandardButton.Save:
                self.save_project()
                return True
            case QtWidgets.QMessageBox.StandardButton.Discard:
                return True
            case QtWidgets.QMessageBox.StandardButton.Cancel:
                return False
            case other:
                _module_logger.error(
                    f"Received unexpected result from SaveProjectConfirmationDialog: "
                    f"'{other}'."
                )
                return False

    def prepare_gui_for_new_project(self) -> None:
        """Prepares the GUI for a new project by clearing states."""
        # Update the registration tab
        tab = self.registration_tab

        tab.alignment_widget.reset_volume()
        tab.alignment_widget.reset_histology()

    def switch_workspace(self) -> None:
        """Handles a change in the current workspace.

        Note that when this function is called, the workspace should already have been
        changed.
        """
        # Clear most of the GUI
        self.prepare_gui_for_new_project()

        # Share the workspace with all of the GUI
        self.propagate_workspace()

        # Begin generating thumbnails
        self.workspace.start_thumbnail_generation()

        # Update the registration tab
        tab = self.registration_tab

        tab.load_atlas()

    def propagate_workspace(self) -> None:
        """Ensures workspace models are properly shared with all that rely on it."""
        self.registration_tab.update_workspace(self.workspace)

    # Event handlers
    def closeEvent(self, event: QtGui.QShowEvent) -> None:
        """Handles close events.

        This ensures the user is prompted for a save/discard/cancel action when
        attempting to close the GUI while the workspace is dirty.

        Args:
            event (QtGui.QCloseEvent): Event to handle.
        """
        if self.close_project():
            event.accept()
        else:
            event.ignore()

    # Menu bar actions
    @QtCore.Slot()
    def create_project(self) -> None:
        """Starts the project creation process."""
        _module_logger.debug("Project creation initiated.")

        # Ensure project is saved/changes discarded or action is cancelled
        if not self.save_guard_project():
            _module_logger.debug("Project creation cancelled.")
            return

        # Build dialog pop-up to gather project settings
        dialog = NewProjectDialog(self)
        dialog.submitted.connect(self._create_project)
        dialog.rejected.connect(
            lambda: _module_logger.debug("Project creation cancelled.")
        )
        dialog.rejected.connect(
            lambda x=self.workspace_is_dirty: setattr(self, "workspace_is_dirty", x)
        )
        self.workspace_is_dirty = False
        dialog.open()

    @QtCore.Slot()
    def _create_project(self, settings: ProjectSettings) -> None:
        _module_logger.debug(
            f"Creating project from settings: {settings.model_dump_json()}"
        )

        # Ensure any previous workspace is no longer in use
        _module_logger.debug("Attempting to close previous project.")
        self.close_project()

        # Ensure the project directory is empty
        clear_directory(settings.project_path)

        # Initialise a new workspace
        self.workspace = Workspace(settings)
        self.switch_workspace()

        # Update workspace state
        self.workspace_is_dirty = True

        self.project_opened.emit()

    @QtCore.Slot()
    def open_project(self) -> None:
        """Starts the project opening process."""
        _module_logger.debug("Project opening initiated.")

        # Ensure project is saved/changes discarded or action is cancelled
        if not self.save_guard_project():
            _module_logger.debug("Project opening cancelled.")
            return

        # Build dialog pop-up to get project path
        dialog = OpenProjectDialog(self)
        dialog.submitted.connect(self._open_project)
        dialog.rejected.connect(
            lambda: _module_logger.debug("Project opening cancelled.")
        )
        dialog.rejected.connect(
            lambda x=self.workspace_is_dirty: setattr(self, "workspace_is_dirty", x)
        )
        self.workspace_is_dirty = False
        dialog.open()

    @QtCore.Slot()
    def _open_project(self, path: str | Path) -> None:
        _module_logger.debug(f"Opening project at: {path}")

        # Ensure any previous workspace is no longer in use
        _module_logger.debug("Attempting to close previous project.")
        self.close_project()

        # Initialise a new workspace
        try:
            self.workspace = Workspace.load(path)
        except ValueError as e:
            _module_logger.error(f"Failed to load project from '{path}': {e}")
            return InvalidProjectFileDialog(self).open()
        self.switch_workspace()

        # Restore registration saved state
        tab = self.registration_tab

        if self.workspace.current_aligner_image_hash is not None:
            tab.open_image_in_aligner(self.workspace.current_aligner_image_index)

        # Synchronise with the visualisation tab
        self.volume_builder_tab.open_project(
            self.workspace.project_settings.project_path,
            self.workspace.project_settings.resolution,
        )
        self.visualisation_tab.open_project(
            self.workspace.project_settings.project_path,
            self.workspace.project_settings.resolution,
        )

        self.project_opened.emit()

    @QtCore.Slot()
    def save_project(self) -> None:
        """Saves the current project and marks the workspace as clean."""
        _module_logger.debug("Saving project")

        self.workspace.save()
        self.workspace_is_dirty = False

    @QtCore.Slot()
    def close_project(self) -> bool:
        """Starts the project closing process.

        Returns:
            bool: True if the user saved/discarded the project, False if they cancelled.
        """
        _module_logger.debug("Project closing initiated.")

        # Ensure project is saved/changes discarded or action is cancelled
        if not self.save_guard_project():
            _module_logger.debug("Project closing cancelled.")
            return False

        # Cancel ongoing work
        self.workspace.stop_thumbnail_generation() if self.workspace else None
        self.workspace_is_dirty = False

        # Clear registration tab
        tab = self.registration_tab

        tab.clear_histology_state()
        tab.clear_volume_state()

        _module_logger.debug("Project closed.")
        self.project_closed.emit()
        return True

    @QtCore.Slot()
    def open_images_folder(self) -> None:
        """Starts the image directory opening process."""
        _module_logger.debug("Images folder opening initiated.")

        # Build dialog pop-up to get images folder path
        dialog = OpenImagesFolderDialog(self)
        dialog.submitted.connect(self._open_images_folder)
        dialog.rejected.connect(
            lambda: _module_logger.debug("Images folder opening cancelled.")
        )
        dialog.open()

    @QtCore.Slot()
    def _open_images_folder(self, path: str | Path) -> None:
        _module_logger.debug(f"Opening images folder at: {path}.")

        # Clear the registration tab
        self.registration_tab.clear_histology_state()

        # Process new images
        self.workspace.parse_image_directory(path)
        self.workspace.start_thumbnail_generation()

        # Synchronise with registration thumbnails
        self.registration_tab.update_completed_thumbnails()

        # Update workspace state
        self.workspace_is_dirty = True

    @QtCore.Slot()
    def export_volume(self) -> None:
        """Displays a pop-up to the user enabling them to export built volumes."""
        _module_logger.debug("Volume export initiated.")

        # Build dialog pop-up to export to a specific directory
        dialog = ExportVolumeDialog(self.workspace.project_settings.project_path, self)
        dialog.submitted.connect(self._export_volume)
        dialog.rejected.connect(
            lambda: _module_logger.debug("Volume export cancelled.")
        )
        dialog.open()

    @QtCore.Slot()
    def _export_volume(self, settings: VolumeExportSettings) -> None:
        exporter_thread = VolumeExporterThread(
            self.workspace.project_settings.project_path, settings, self
        )

        dialog = InfiniteProgressDialog("Exporting volume(s)", self)
        exporter_thread.export_finished.connect(dialog.accept)
        exporter_thread.export_finished.connect(exporter_thread.deleteLater)

        dialog.open()
        exporter_thread.start()

    @QtCore.Slot()
    def quit(self) -> None:
        """Starts the application closing process."""
        _module_logger.debug("Quitting initiated.")

        self.close()

        _module_logger.debug("Quitting application.")

    # Miscellaneous slots
    @QtCore.Slot()
    def reload_project(self, index: int) -> None:
        """Reloads the current project for a given tab.

        This is necessary to notify tabs of new alignments, volumes, etc.

        Args:
            index (int): Index of the tab to reload.
        """
        if index < 1 or self.workspace is None:
            return

        if index == 1:
            tab = self.volume_builder_tab
        elif index == 2:
            tab = self.quantification_tab
        elif index == 3:
            tab = self.visualisation_tab
        else:
            return

        tab.open_project(
            self.workspace.project_settings.project_path,
            resolution=self.workspace.project_settings.resolution,
        )
