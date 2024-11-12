# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
import os
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.ccf.paths import get_annotation_path
from histalign.backend.io import clear_directory
from histalign.backend.maths import (
    apply_offset,
    apply_rotation,
    convert_pixmap_position_to_coordinates,
    convert_volume_coordinates_to_ccf,
)
from histalign.backend.models import ProjectSettings
from histalign.backend.workspace import AnnotationVolume, VolumeLoaderThread, Workspace
from histalign.frontend.common_widgets import (
    BasicApplicationWindow,
    BasicMenuBar,
    DynamicThemeIcon,
    MouseTrackingFilter,
    ShortcutAwareToolButton,
)
from histalign.frontend.dialogs import (
    AtlasProgressDialog,
    ConfirmDeleteDialog,
    InvalidProjectFileDialog,
    NewProjectDialog,
    SaveProjectConfirmationDialog,
)
from histalign.frontend.registration.alignment import AlignmentWidget
from histalign.frontend.registration.alpha import AlphaWidget
from histalign.frontend.registration.helpers import get_dummy_title_bar
from histalign.frontend.registration.settings import SettingsWidget
from histalign.frontend.registration.thumbnails import ThumbnailsWidget


class RegistrationMenuBar(BasicMenuBar):
    action_groups: dict[str, list[QtWidgets.QMenu | QtGui.QAction]]

    new_action: QtGui.QAction
    save_action: QtGui.QAction
    open_directory_action: QtGui.QAction

    new_requested: QtCore.Signal = QtCore.Signal()
    save_requested: QtCore.Signal = QtCore.Signal()
    open_directory_requested: QtCore.Signal = QtCore.Signal()

    lut_change_requested: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        project_required_group = []

        self.action_groups = {"project_required": project_required_group}

        #
        new_action = QtGui.QAction("&New", self.file_menu)

        new_action.setStatusTip("Create a new project")
        new_action.setShortcut(QtGui.QKeySequence("Ctrl+n"))
        new_action.setShortcutContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        new_action.triggered.connect(self.new_requested.emit)

        self.new_action = new_action

        #
        save_action = QtGui.QAction("&Save", self.file_menu)

        save_action.setStatusTip("Save the current project")
        save_action.setShortcut(QtGui.QKeySequence("Ctrl+Shift+s"))
        save_action.setShortcutContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        save_action.triggered.connect(self.save_requested.emit)
        save_action.setEnabled(False)
        project_required_group.append(save_action)

        self.save_action = save_action

        #
        open_directory_action = QtGui.QAction("Open &image directory", self)

        open_directory_action.setStatusTip("Open an image directory for alignment")
        open_directory_action.setShortcut(QtGui.QKeySequence("Ctrl+Shift+o"))
        open_directory_action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        open_directory_action.triggered.connect(self.open_directory_requested.emit)
        open_directory_action.setEnabled(False)
        project_required_group.append(open_directory_action)

        self.open_directory_action = open_directory_action

        #
        self.file_menu.insertAction(self.open_action, new_action)
        self.file_menu.insertAction(self.close_action, save_action)
        self.file_menu.insertSeparator(self.close_action)
        # A bit flaky since separators are in added order which might not match visual
        self.file_menu.insertAction(
            [
                action
                for action in self.file_menu.findChildren(QtGui.QAction)
                if action.isSeparator()
            ][0],
            open_directory_action,
        )

        #
        lut_menu = self.addMenu("&LUT")

        lut_menu.setEnabled(False)
        self.action_groups["project_required"].append(lut_menu)

        #
        lut_group = QtGui.QActionGroup(lut_menu)

        lut_group.triggered.connect(
            lambda action: self.lut_change_requested.emit(action.toolTip().lower())
        )

        grey_lut_action = QtGui.QAction("Gr&ey")
        grey_lut_action.setCheckable(True)
        grey_lut_action.setChecked(True)
        lut_group.addAction(grey_lut_action)
        lut_menu.addAction(grey_lut_action)
        red_lut_action = QtGui.QAction("&Red")
        red_lut_action.setCheckable(True)
        lut_group.addAction(red_lut_action)
        lut_menu.addAction(red_lut_action)
        green_lut_action = QtGui.QAction("&Green")
        green_lut_action.setCheckable(True)
        lut_group.addAction(green_lut_action)
        lut_menu.addAction(green_lut_action)
        blue_lut_action = QtGui.QAction("&Blue")
        blue_lut_action.setCheckable(True)
        lut_group.addAction(blue_lut_action)
        lut_menu.addAction(blue_lut_action)
        cyan_lut_action = QtGui.QAction("&Cyan")
        cyan_lut_action.setCheckable(True)
        lut_group.addAction(cyan_lut_action)
        lut_menu.addAction(cyan_lut_action)
        magenta_lut_action = QtGui.QAction("&Magenta")
        magenta_lut_action.setCheckable(True)
        lut_group.addAction(magenta_lut_action)
        lut_menu.addAction(magenta_lut_action)
        yellow_lut_action = QtGui.QAction("&Yellow")
        yellow_lut_action.setCheckable(True)
        lut_group.addAction(yellow_lut_action)
        lut_menu.addAction(yellow_lut_action)

    def opened_project(self) -> None:
        for action in self.action_groups["project_required"]:
            action.setEnabled(True)


class RegistrationToolBar(QtWidgets.QToolBar):
    save_button: ShortcutAwareToolButton
    load_button: ShortcutAwareToolButton
    delete_button: ShortcutAwareToolButton
    reset_histology_button: ShortcutAwareToolButton
    reset_volume_button: ShortcutAwareToolButton
    apply_auto_threshold_button: ShortcutAwareToolButton
    background_threshold_spin_box: QtWidgets.QSpinBox

    save_requested: QtCore.Signal = QtCore.Signal()
    load_requested: QtCore.Signal = QtCore.Signal()
    delete_requested: QtCore.Signal = QtCore.Signal()
    reset_histology_requested: QtCore.Signal = QtCore.Signal()
    reset_volume_requested: QtCore.Signal = QtCore.Signal()
    apply_auto_threshold_requested: QtCore.Signal = QtCore.Signal()
    background_threshold_changed: QtCore.Signal = QtCore.Signal(int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        save_button = ShortcutAwareToolButton()

        save_button.setShortcut(QtGui.QKeySequence("Ctrl+s"))
        save_button.setToolTip("Save alignment for the current image. ")
        save_button.setStatusTip("Save alignment for the current image.")
        save_button.setIcon(DynamicThemeIcon("resources/icons/file-black-icon.png"))

        save_button.clicked.connect(self.save_requested.emit)

        self.save_button = save_button

        #
        load_button = ShortcutAwareToolButton()

        load_button.setToolTip("Load the saved alignment for the current image.")
        load_button.setStatusTip("Load the saved alignment for the current image.")
        load_button.setIcon(DynamicThemeIcon("resources/icons/upload-arrow-icon.png"))

        load_button.clicked.connect(self.load_requested.emit)
        load_button.setShortcut(QtGui.QKeySequence("Ctrl+l"))

        self.load_button = load_button

        #
        delete_button = ShortcutAwareToolButton()

        delete_button.setToolTip("Delete the saved alignment for the current image.")
        delete_button.setStatusTip("Delete the saved alignment for the current image.")
        delete_button.setIcon(DynamicThemeIcon("resources/icons/recycle-bin-icon.png"))

        delete_button.clicked.connect(self.delete_requested.emit)

        self.delete_button = delete_button

        #
        reset_histology_button = ShortcutAwareToolButton()

        reset_histology_button.setToolTip("Reset the image alignment settings.")
        reset_histology_button.setStatusTip("Reset the image alignment settings.")
        reset_histology_button.setIcon(
            DynamicThemeIcon("resources/icons/forward-restore-icon.png")
        )

        reset_histology_button.clicked.connect(self.reset_histology_requested.emit)
        reset_histology_button.setShortcut(QtGui.QKeySequence("Ctrl+r"))

        self.reset_histology_button = reset_histology_button

        #
        reset_volume_button = ShortcutAwareToolButton()

        reset_volume_button.setToolTip("Reset the atlas alignment settings.")
        reset_volume_button.setStatusTip("Reset the atlas alignment settings.")
        reset_volume_button.setIcon(
            DynamicThemeIcon("resources/icons/forward-restore-icon.png")
        )

        reset_volume_button.clicked.connect(self.reset_volume_requested.emit)
        reset_volume_button.setShortcut(QtGui.QKeySequence("Ctrl+Shift+r"))

        self.reset_volume_button = reset_volume_button

        #
        apply_auto_threshold_button = ShortcutAwareToolButton()

        apply_auto_threshold_button.setToolTip(
            "Apply a pass of ImageJ's brightness/contrast auto-thresholding algorithm."
        )
        apply_auto_threshold_button.setStatusTip(
            "Apply a pass of ImageJ's brightness/contrast auto-thresholding algorithm."
        )
        apply_auto_threshold_button.setIcon(
            DynamicThemeIcon("resources/icons/background-icon.png")
        )

        apply_auto_threshold_button.clicked.connect(
            self.apply_auto_threshold_requested.emit
        )
        apply_auto_threshold_button.setShortcut(QtGui.QKeySequence("Ctrl+Shift+c"))

        self.apply_auto_threshold_button = apply_auto_threshold_button

        #
        background_spin_box_icon = QtWidgets.QToolButton()

        background_spin_box_icon.setIcon(
            DynamicThemeIcon("resources/icons/color-contrast-icon.png")
        )
        background_spin_box_icon.setStyleSheet(
            """
            QToolButton:hover {
                border: none;
            }
            """
        )

        #
        background_spin_box = QtWidgets.QSpinBox()

        background_spin_box.setToolTip("Set the background transparency threshold.")
        background_spin_box.setStatusTip("Set the background transparency threshold.")
        background_spin_box.setMinimum(0)
        background_spin_box.setMaximum(255)
        background_spin_box.setValue(0)
        background_spin_box.valueChanged.connect(
            lambda x: self.background_threshold_changed.emit(x)
        )

        self.background_threshold_spin_box = background_spin_box

        #
        self.addWidget(save_button)
        self.addWidget(load_button)
        self.addWidget(delete_button)
        self.addSeparator()
        self.addWidget(reset_histology_button)
        self.addWidget(reset_volume_button)
        self.addSeparator()
        self.addWidget(apply_auto_threshold_button)
        self.addSeparator()
        self.addWidget(background_spin_box_icon)
        self.addWidget(background_spin_box)

        #
        self.setAllowedAreas(QtCore.Qt.ToolBarArea.TopToolBarArea)
        self.setMovable(False)


class RegistrationMainWindow(BasicApplicationWindow):
    workspace: Optional[Workspace] = None
    workspace_loaded: bool = False
    workspace_dirtied: bool = False

    annotation_volume: Optional[AnnotationVolume] = None

    toolbar: RegistrationToolBar
    alignment_widget: AlignmentWidget
    thumbnails_widget: ThumbnailsWidget
    alpha_widget: AlphaWidget
    settings_widget: SettingsWidget

    project_closed: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        #
        alignment_widget = AlignmentWidget()

        alignment_widget.view.installEventFilter(
            MouseTrackingFilter(
                tracking_callback=self.locate_mouse,
                leaving_callback=self.clear_status,
                watched_type=QtWidgets.QGraphicsView,
                parent=alignment_widget.view,
            )
        )

        self.alignment_widget = alignment_widget

        #
        super().__init__(parent)

        self.logger = logging.getLogger(
            f"{self.__module__}.{self.__class__.__qualname__}"
        )

        #
        thumbnails_widget = ThumbnailsWidget()

        thumbnails_widget.content_area.open_image.connect(self.open_image_in_aligner)

        self.thumbnails_widget = thumbnails_widget

        #
        alpha_widget = AlphaWidget()

        alpha_widget.global_alpha_slider.valueChanged.connect(
            alignment_widget.update_global_alpha
        )

        self.alpha_widget = alpha_widget

        #
        settings_widget = SettingsWidget()

        settings_widget.volume_settings_widget.setEnabled(False)
        settings_widget.volume_settings_widget.values_changed.connect(
            alignment_widget.update_volume_pixmap
        )
        settings_widget.histology_settings_widget.setEnabled(False)
        settings_widget.histology_settings_widget.values_changed.connect(
            alignment_widget.update_histology_pixmap
        )

        alignment_widget.translation_changed.connect(
            settings_widget.histology_settings_widget.handle_outside_translation
        )
        alignment_widget.zoom_changed.connect(
            settings_widget.histology_settings_widget.handle_outside_zoom
        )

        self.settings_widget = settings_widget

        #
        layout = QtWidgets.QHBoxLayout()

        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        layout.addWidget(thumbnails_widget, stretch=1)
        layout.addWidget(alignment_widget, stretch=3)
        layout.addWidget(alpha_widget)
        layout.addWidget(settings_widget, stretch=1)

        #
        central_widget = QtWidgets.QWidget()

        central_widget.setLayout(layout)
        central_widget.statusBar = self.statusBar

        self.setCentralWidget(central_widget)

        #
        toolbar = RegistrationToolBar()

        toolbar.save_button.setEnabled(False)
        toolbar.load_button.setEnabled(False)
        toolbar.delete_button.setEnabled(False)
        toolbar.reset_histology_button.setEnabled(False)
        toolbar.reset_volume_button.setEnabled(False)
        toolbar.apply_auto_threshold_button.setEnabled(False)

        toolbar.save_requested.connect(lambda: toolbar.load_button.setEnabled(True))
        toolbar.save_requested.connect(lambda: toolbar.delete_button.setEnabled(True))
        toolbar.save_requested.connect(
            lambda: toolbar.apply_auto_threshold_button.setEnabled(True)
        )
        toolbar.save_requested.connect(
            lambda: self.thumbnails_widget.content_area.toggle_thumbnail_complete_state(
                self.workspace.current_aligner_image_index
            )
        )

        toolbar.delete_requested.connect(self.show_confirm_delete_alignment_dialog)

        toolbar.background_threshold_changed.connect(
            alignment_widget.update_background_alpha
        )
        toolbar.reset_histology_requested.connect(
            settings_widget.histology_settings_widget.reset_to_defaults
        )
        toolbar.reset_volume_requested.connect(
            settings_widget.volume_settings_widget.reset_to_defaults
        )
        toolbar.apply_auto_threshold_requested.connect(
            self.alignment_widget.apply_auto_contrast
        )

        self.addToolBar(toolbar)
        self.toolbar = toolbar

    def set_up_menu_bar(self) -> None:
        menu_bar = RegistrationMenuBar()

        menu_bar.new_requested.connect(self.show_new_project_dialog)
        menu_bar.open_requested.connect(self.show_open_project_dialog)
        menu_bar.save_requested.connect(self.save_project)
        menu_bar.close_requested.connect(self.close_project)
        menu_bar.open_directory_requested.connect(self.show_open_image_directory_dialog)
        menu_bar.exit_requested.connect(self.exit_application)

        menu_bar.lut_change_requested.connect(self.alignment_widget.update_lut)

        self.setMenuBar(menu_bar)

    def propagate_new_workspace(self) -> None:
        self.connect_workspace()
        self.share_workspace_models()

        # Sync states
        self.alignment_widget.prepare_slicer()
        self.settings_widget.reload_settings()

        for index, slice_ in enumerate(self.workspace._histology_slices):
            if not os.path.exists(
                self.workspace.working_directory + os.sep + slice_.hash + ".json"
            ):
                continue

            self.thumbnails_widget.content_area.toggle_thumbnail_complete_state(index)

    def connect_workspace(self) -> None:
        self.thumbnails_widget.connect_workspace(self.workspace)

        toolbar = self.toolbar

        toolbar.save_requested.connect(self.workspace.save_alignment)
        toolbar.save_requested.connect(
            lambda: self.statusBar().showMessage("Alignment saved", 2000)
        )

        toolbar.load_requested.connect(self.workspace.load_alignment)
        toolbar.load_requested.connect(
            lambda: self.statusBar().showMessage("Alignment loaded", 2000)
        )
        toolbar.load_requested.connect(self.share_workspace_models)
        toolbar.load_requested.connect(self.settings_widget.reload_settings)

    def share_workspace_models(self) -> None:
        alignment_settings = self.workspace.alignment_settings
        volume_settings = self.workspace.alignment_settings.volume_settings
        histology_settings = self.workspace.alignment_settings.histology_settings

        self.alignment_widget.alignment_settings = alignment_settings
        self.alignment_widget.volume_settings = volume_settings
        self.alignment_widget.histology_settings = histology_settings

        self.settings_widget.volume_settings_widget.settings = (
            self.workspace.alignment_settings.volume_settings
        )
        self.settings_widget.histology_settings_widget.settings = histology_settings

    def load_atlas(self) -> None:
        loader_thread = VolumeLoaderThread(self.alignment_widget.volume_slicer.volume)

        dialog = AtlasProgressDialog(self)

        # Sneak the annotation volume in here. It doesn't usually take long but if
        # it turns out to in the future, we can give feedback to the user.
        self.annotation_volume = AnnotationVolume(
            get_annotation_path(self.workspace.resolution),
            self.workspace.resolution,
            lazy=True,
        )
        annotation_loader_thread = VolumeLoaderThread(self.annotation_volume, self)
        annotation_loader_thread.volume_loaded.connect(
            annotation_loader_thread.deleteLater
        )

        # Using terminate rather than exit to avoid waiting for a long download/load
        dialog.canceled.connect(loader_thread.terminate)
        dialog.canceled.connect(loader_thread.wait)

        loader_thread.volume_downloaded.connect(
            lambda: dialog.setLabelText("Loading atlas")
        )
        loader_thread.volume_loaded.connect(dialog.reset)
        loader_thread.volume_loaded.connect(self.open_atlas_in_aligner)

        annotation_loader_thread.start()
        loader_thread.start()
        dialog.exec()

    def dirty_workspace(self) -> None:
        if self.workspace_loaded:
            self.workspace_dirtied = True

    def locate_mouse(self) -> None:
        # Get the position of the cursor relative to the application window
        cursor_global_position = QtGui.QCursor.pos()
        # Convert it to the coordinate system of the alignment scene
        cursor_scene_position = self.alignment_widget.view.mapToScene(
            self.alignment_widget.view.mapFromGlobal(cursor_global_position)
        )

        # Abort and clear status if the cursor is not hovering the volume
        if not isinstance(
            self.alignment_widget.scene.itemAt(
                cursor_scene_position, QtGui.QTransform()
            ),
            QtWidgets.QGraphicsPixmapItem,
        ):
            self.clear_status()
            return

        # Convert the scene position to a volume position in the alignment volume.
        # Note that this is still a position as it is still 2D at this point.
        cursor_volume_position = self.alignment_widget.volume_pixmap.mapFromScene(
            cursor_scene_position
        )
        # Convert the 2D position to 3D by appending an axis with value 0 depending
        # on the orientation.
        cursor_volume_coordinates = convert_pixmap_position_to_coordinates(
            cursor_volume_position,
            self.alignment_widget.volume_settings,
        )

        # Apply rotation to the naive coordinates
        cursor_volume_rotated_coordinates = apply_rotation(
            cursor_volume_coordinates,
            self.alignment_widget.volume_settings,
        )
        # Apply the offset to get the true coordinates of the cursor relative to the
        # volume centre.
        cursor_volume_rotated_coordinates = apply_offset(
            cursor_volume_rotated_coordinates, self.alignment_widget.volume_settings
        )

        # Convert to the CCF coordinate system
        ccf_aligned_coordinates = convert_volume_coordinates_to_ccf(
            cursor_volume_rotated_coordinates,
            self.alignment_widget.volume_settings,
        )

        # Get the name of the structure at those coordinates
        structure_name = self.annotation_volume.get_name_from_voxel(
            ccf_aligned_coordinates
        )
        structure_string = f" ({structure_name})" if structure_name else ""

        # Correct coordinates for resolution
        ccf_aligned_coordinates *= self.workspace.resolution.value

        self.statusBar().showMessage(
            f"CCF coordinates of cursor: "
            f"{', '.join(map(str, map(round, map(int, ccf_aligned_coordinates))))}"
            f"{structure_string}"
        )

    def clear_status(self) -> None:
        self.statusBar().clearMessage()

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
    def show_new_project_dialog(self) -> None:
        if self.workspace is not None and self.workspace_dirtied:
            match SaveProjectConfirmationDialog(self).exec():
                case QtWidgets.QMessageBox.Save:
                    self.save_project()
                case QtWidgets.QMessageBox.Cancel:
                    return None

        dialog = NewProjectDialog(self)
        dialog.submitted.connect(self.create_project)
        dialog.exec()

    @QtCore.Slot()
    def show_open_project_dialog(self) -> None:
        if self.workspace is not None and self.workspace_dirtied:
            match SaveProjectConfirmationDialog(self).exec():
                case QtWidgets.QMessageBox.Save:
                    self.save_project()
                case QtWidgets.QMessageBox.Cancel:
                    return

        super().show_open_project_dialog()

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
            self.thumbnails_widget.content_area.flush_thumbnails()
            self.workspace.parse_image_directory(image_directory)
            self.workspace.start_thumbnail_generation()

    @QtCore.Slot()
    def show_confirm_delete_alignment_dialog(self) -> None:
        dialog = ConfirmDeleteDialog(self)

        if dialog.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
            return

        self.workspace.delete_alignment()
        self.statusBar().showMessage("Deleted alignment", 2000)
        self.thumbnails_widget.content_area.toggle_thumbnail_complete_state(
            self.workspace.current_aligner_image_index
        )

        self.toolbar.load_button.setEnabled(False)
        self.toolbar.delete_button.setEnabled(False)

    @QtCore.Slot()
    def create_project(self, project_settings: ProjectSettings) -> None:
        clear_directory(project_settings.project_path)

        self.workspace = Workspace(project_settings)
        self.propagate_new_workspace()

        self.workspace.start_thumbnail_generation()
        self.load_atlas()

        self.menuBar().opened_project()

        self.workspace_loaded = True
        self.dirty_workspace()

    @QtCore.Slot()
    def open_project(self, project_file_path: str) -> None:
        try:
            self.workspace = Workspace.load(project_file_path)
        except ValueError:
            return InvalidProjectFileDialog(self).open()

        self.propagate_new_workspace()

        self.workspace.start_thumbnail_generation()
        self.load_atlas()

        if self.workspace.current_aligner_image_hash is not None:
            self.open_image_in_aligner(
                self.workspace.current_aligner_image_index, force_open=True
            )

        self.menuBar().opened_project()

        self.workspace_loaded = True
        self.workspace_dirtied = False

    @QtCore.Slot()
    def save_project(self) -> None:
        self.workspace.save()
        self.workspace_dirtied = False

    @QtCore.Slot()
    def open_atlas_in_aligner(self) -> None:
        try:
            self.alignment_widget.update_volume_pixmap()
        except ValueError as error:
            self.logger.error("Could not open atlas volume.")
            self.logger.error(error)
            return

        self.toolbar.reset_volume_button.setEnabled(True)

        self.workspace.alignment_settings.volume_settings.shape = (
            self.alignment_widget.volume_slicer.volume.shape
        )
        self.settings_widget.volume_settings_widget.update_offset_spin_box_limits()
        self.settings_widget.volume_settings_widget.reload_settings()
        self.settings_widget.volume_settings_widget.setEnabled(True)

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

        old_index = self.workspace.current_aligner_image_index

        image = self.workspace.get_image(index)
        if image is None:
            self.logger.error(
                f"Failed retrieving image at index {index}, index out of range."
            )
            return

        self.alignment_widget.update_histological_slice(image)
        self.alignment_widget.update_background_alpha(
            self.toolbar.background_threshold_spin_box.value()
        )
        self.alignment_widget.update_global_alpha(
            self.alpha_widget.global_alpha_slider.value()
        )
        self.toolbar.save_button.setEnabled(True)

        self.toolbar.load_button.setEnabled(
            os.path.exists(self.workspace.build_alignment_path())
        )
        self.toolbar.delete_button.setEnabled(
            os.path.exists(self.workspace.build_alignment_path())
        )

        self.toolbar.reset_histology_button.setEnabled(True)
        self.settings_widget.histology_settings_widget.setEnabled(True)
        self.toolbar.apply_auto_threshold_button.setEnabled(True)

        if old_index is not None:
            self.thumbnails_widget.content_area.toggle_activate_frame(old_index)
        if old_index != index:
            self.thumbnails_widget.content_area.toggle_activate_frame(index)
