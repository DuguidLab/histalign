# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from contextlib import suppress
import logging
import os
from typing import Optional

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.ccf.paths import get_annotation_path
from histalign.backend.io import RESOURCES_ROOT
from histalign.backend.maths import apply_rotation, compute_centre, compute_origin
from histalign.backend.models import Orientation
from histalign.backend.workspace import AnnotationVolume, VolumeLoaderThread, Workspace
from histalign.frontend.common_widgets import (
    CollapsibleWidgetArea,
    MouseTrackingFilter,
    PreferentialSplitter,
    ShortcutAwareToolButton,
)
from histalign.frontend.dialogs import (
    AtlasProgressDialog,
    ConfirmDeleteDialog,
)
from histalign.frontend.pyside_helpers import lua_aware_shift, try_show_status_message
from histalign.frontend.registration.alignment import (
    AlignmentWidget,
    LandmarkRegistrationWindow,
)
from histalign.frontend.registration.alpha import AlphaWidget
from histalign.frontend.registration.settings import SettingsWidget
from histalign.frontend.registration.thumbnails import ThumbnailsWidget

_module_logger = logging.getLogger(__name__)


class RegistrationWidget(QtWidgets.QWidget):
    workspace: Optional[Workspace] = None
    annotation_volume: Optional[AnnotationVolume] = None

    alignment_widget: AlignmentWidget
    thumbnails_widget: ThumbnailsWidget
    settings_widget: SettingsWidget
    alpha_widget: AlphaWidget
    background_alpha_spin_box: QtWidgets.QSpinBox

    project_opened: QtCore.Signal = QtCore.Signal()
    project_closed: QtCore.Signal = QtCore.Signal()
    volume_opened: QtCore.Signal = QtCore.Signal()
    histology_opened: QtCore.Signal = QtCore.Signal()
    alignment_saved: QtCore.Signal = QtCore.Signal()
    alignment_loaded: QtCore.Signal = QtCore.Signal()
    alignment_deleted: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        # Create the central alignment widget
        alignment_widget = AlignmentWidget()

        # Track user mouse over atlas to display status info about CCF coordinates
        alignment_widget.view.installEventFilter(
            MouseTrackingFilter(
                tracking_callback=self.locate_mouse,
                leaving_callback=self.clear_status,
                watched_type=QtWidgets.QGraphicsView,
                parent=alignment_widget.view,
            )
        )

        self.alignment_widget = alignment_widget

        # Create left menu to display thumbnails
        thumbnails_widget = ThumbnailsWidget()

        thumbnails_widget.thumbnail_activated.connect(self.open_image_in_aligner)

        self.thumbnails_widget = thumbnails_widget

        # Create histology alpha slider that sits on the right of the alignment view
        alpha_widget = AlphaWidget()

        alpha_widget.global_alpha_slider.valueChanged.connect(
            alignment_widget.update_global_alpha
        )

        alpha_widget.setContentsMargins(0, 8, 0, 0)

        self.alpha_widget = alpha_widget

        # Create settings widget to control histology and atlas parameters
        settings_widget = SettingsWidget()

        settings_widget.volume_settings_widget.setEnabled(False)
        settings_widget.volume_settings_widget.values_changed.connect(
            alignment_widget.update_volume_pixmap
        )
        self.volume_opened.connect(
            lambda: settings_widget.volume_settings_widget.setEnabled(True)
        )
        self.project_closed.connect(
            lambda: settings_widget.volume_settings_widget.setEnabled(False)
        )
        settings_widget.histology_settings_widget.setEnabled(False)
        settings_widget.histology_settings_widget.values_changed.connect(
            alignment_widget.update_histology_pixmap
        )
        self.histology_opened.connect(
            lambda: settings_widget.histology_settings_widget.setEnabled(True)
        )
        self.project_closed.connect(
            lambda: settings_widget.histology_settings_widget.setEnabled(False)
        )

        alignment_widget.translation_changed.connect(
            settings_widget.histology_settings_widget.handle_outside_translation
        )
        alignment_widget.rotation_changed.connect(
            settings_widget.histology_settings_widget.handle_outside_rotation
        )
        alignment_widget.zoom_changed.connect(
            settings_widget.histology_settings_widget.handle_outside_zoom
        )

        settings_widget.setContentsMargins(0, 10, 5, 0)

        self.settings_widget = settings_widget

        # Merge alpha slider and settings widgets to allow fitting main widgets into
        # a single PreferentialSplitter.
        right_composite_layout = QtWidgets.QHBoxLayout()

        right_composite_layout.addWidget(alpha_widget)
        right_composite_layout.addWidget(settings_widget)

        right_composite_layout.setContentsMargins(0, 0, 0, 0)

        right_composite_widget = QtWidgets.QWidget()

        right_composite_widget.setLayout(right_composite_layout)

        # Create left collapsible menu
        left = CollapsibleWidgetArea()

        left.add_widget(thumbnails_widget)

        # Create right collapsible menu
        right = CollapsibleWidgetArea("right_to_left")

        right.add_widget(right_composite_widget)

        # Create main splitter widget
        splitter = PreferentialSplitter()

        splitter.add_widgets([left, alignment_widget, right])

        # Build the tool bar to interact with the alignment view
        toolbar = self.build_tool_bar()

        # Finalise the GUI
        layout = QtWidgets.QVBoxLayout()

        layout.addWidget(toolbar)
        layout.addWidget(splitter)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.setLayout(layout)

    def build_tool_bar(self) -> QtWidgets.QToolBar:
        """Builds the main registration tool bar.

        Returns:
            QtWidgets.QToolBar: The built tool bar, already connected to relevant slots.
        """

        def disable_all(tool_bar: QtWidgets.QToolBar) -> None:
            for widget in tool_bar.children():
                widget.setEnabled(False)

        tool_bar = QtWidgets.QToolBar()
        tool_bar.setEnabled(False)

        self.project_opened.connect(lambda: tool_bar.setEnabled(True))
        self.project_closed.connect(lambda: tool_bar.setEnabled(False))
        self.project_closed.connect(lambda: disable_all(tool_bar))

        save_alignment_button = ShortcutAwareToolButton(
            enabled=False,
            icon_path=RESOURCES_ROOT / "icons" / "file-black-icon.png",
            shortcut=QtGui.QKeySequence("CTRL+SHIFT+S"),
            tool_tip="Save alignment for the current image.",
        )
        save_alignment_button.clicked.connect(self.save_alignment)
        self.histology_opened.connect(lambda: save_alignment_button.setEnabled(True))
        tool_bar.addWidget(save_alignment_button)

        load_alignment_button = ShortcutAwareToolButton(
            enabled=False,
            icon_path=RESOURCES_ROOT / "icons" / "upload-arrow-icon.png",
            shortcut=QtGui.QKeySequence("CTRL+L"),
            tool_tip="Load the saved alignment for the current image.",
        )
        load_alignment_button.clicked.connect(lambda: self.workspace.load_alignment())
        load_alignment_button.clicked.connect(self.load_alignment)
        self.histology_opened.connect(
            lambda: load_alignment_button.setEnabled(
                os.path.exists(self.workspace.build_alignment_path())
            )
        )
        self.alignment_saved.connect(lambda: load_alignment_button.setEnabled(True))
        self.alignment_deleted.connect(lambda: load_alignment_button.setEnabled(False))
        tool_bar.addWidget(load_alignment_button)

        delete_alignment_button = ShortcutAwareToolButton(
            enabled=False,
            icon_path=RESOURCES_ROOT / "icons" / "recycle-bin-icon.png",
            tool_tip="Delete the saved alignment for the current image.",
        )
        delete_alignment_button.clicked.connect(self.delete_alignment)
        self.histology_opened.connect(
            lambda: delete_alignment_button.setEnabled(
                os.path.exists(self.workspace.build_alignment_path())
            )
        )
        self.alignment_saved.connect(lambda: delete_alignment_button.setEnabled(True))
        self.alignment_deleted.connect(
            lambda: delete_alignment_button.setEnabled(False)
        )
        tool_bar.addWidget(delete_alignment_button)

        reset_histology_button = ShortcutAwareToolButton(
            enabled=False,
            icon_path=RESOURCES_ROOT / "icons" / "forward-restore-icon.png",
            tool_tip="Reset the image alignment settings.",
        )
        reset_histology_button.clicked.connect(
            self.settings_widget.histology_settings_widget.reset_to_defaults
        )
        self.histology_opened.connect(lambda: reset_histology_button.setEnabled(True))
        tool_bar.addWidget(reset_histology_button)

        reset_volume_button = ShortcutAwareToolButton(
            enabled=False,
            icon_path=RESOURCES_ROOT / "icons" / "forward-restore-icon.png",
            tool_tip="Reset the atlas alignment settings.",
        )
        reset_volume_button.clicked.connect(
            self.settings_widget.volume_settings_widget.reset_to_defaults
        )
        self.volume_opened.connect(lambda: reset_volume_button.setEnabled(True))
        tool_bar.addWidget(reset_volume_button)

        apply_auto_threshold_button = ShortcutAwareToolButton(
            enabled=False,
            icon_path=RESOURCES_ROOT / "icons" / "background-icon.png",
            shortcut=QtGui.QKeySequence("CTRL+SHIFT+C"),
            tool_tip="Apply a pass of ImageJ's auto-contrasting algorithm.",
        )
        apply_auto_threshold_button.clicked.connect(
            self.alignment_widget.apply_auto_contrast
        )
        self.histology_opened.connect(
            lambda: apply_auto_threshold_button.setEnabled(True)
        )
        tool_bar.addWidget(apply_auto_threshold_button)

        background_alpha_spin_box_icon = ShortcutAwareToolButton(
            enabled=False,
            icon_path=RESOURCES_ROOT / "icons" / "color-contrast-icon.png",
        )
        background_alpha_spin_box_icon.setStyleSheet(
            """
            QToolButton:hover {
                border: none;
            }
            """
        )
        self.histology_opened.connect(
            lambda: background_alpha_spin_box_icon.setEnabled(True)
        )
        tool_bar.addWidget(background_alpha_spin_box_icon)

        background_alpha_spin_box = QtWidgets.QSpinBox(minimum=0, maximum=255, value=0)
        background_alpha_spin_box.valueChanged.connect(
            self.alignment_widget.update_background_alpha
        )
        background_alpha_spin_box.setToolTip(
            "Set the background transparency threshold."
        )
        background_alpha_spin_box.setStatusTip(
            "Set the background transparency threshold."
        )
        self.histology_opened.connect(
            lambda: background_alpha_spin_box.setEnabled(True)
        )
        self.background_alpha_spin_box = background_alpha_spin_box
        tool_bar.addWidget(background_alpha_spin_box)

        landmark_registration_button = ShortcutAwareToolButton(
            icon_path=RESOURCES_ROOT / "icons" / "interactivity-icon.png",
            tool_tip="Start the landmark registration process.",
        )
        self.histology_opened.connect(
            lambda: landmark_registration_button.setEnabled(True)
        )
        tool_bar.addWidget(landmark_registration_button)

        # Style it with a bottom border
        border_colour = lua_aware_shift(tool_bar.palette().window().color()).getRgb()
        tool_bar.setStyleSheet(
            f"QToolBar {{ border-bottom: 1px solid rgba{border_colour}; }}"
        )

        return tool_bar

    def clear_histology_state(self) -> None:
        """Clears any histology on the GUI."""
        self.alignment_widget.update_histological_slice(None)
        self.thumbnails_widget.flush_thumbnails()

    def clear_status(self) -> None:
        """Clears the temporary message on the status bar."""
        with suppress(AttributeError):
            self.window().statusBar().clearMessage()

    def clear_volume_state(self) -> None:
        """Clears any atlas on the GUI."""
        self.alignment_widget.reset_volume()

    def load_atlas(self) -> int:
        """Loads the atlas and annotations volumes."""
        _module_logger.debug("Loading atlas and annotations.")

        # Gather the volumes.
        # Sneak the annotation volume in here. It doesn't usually take long but if
        # it turns out to in the future, we can give feedback to the user.
        annotation_volume = AnnotationVolume(
            get_annotation_path(self.workspace.resolution),
            self.workspace.resolution,
            lazy=True,
        )
        annotation_volume.loaded.connect(
            lambda: _module_logger.debug("Annotations loaded.")
        )
        self.annotation_volume = annotation_volume
        atlas_volume = self.alignment_widget.volume_slicer.volume

        # Set up the dialog and loader threads
        dialog = AtlasProgressDialog(self)
        annotation_loader_thread = VolumeLoaderThread(annotation_volume)
        atlas_loader_thread = VolumeLoaderThread(atlas_volume)

        atlas_volume.downloaded.connect(
            lambda: dialog.setLabelText("Loading atlas"),
            type=QtCore.Qt.ConnectionType.QueuedConnection,
        )
        atlas_volume.loaded.connect(lambda: _module_logger.debug("Atlas loaded."))
        atlas_volume.loaded.connect(
            dialog.accept, type=QtCore.Qt.ConnectionType.QueuedConnection
        )
        atlas_volume.loaded.connect(
            self.open_atlas_in_aligner, type=QtCore.Qt.ConnectionType.QueuedConnection
        )

        # Start dialog and threads
        annotation_loader_thread.start()
        atlas_loader_thread.start()

        result = dialog.exec()  # Blocking

        # Ensure we wait for the threads to be destroyed
        annotation_loader_thread.wait()
        atlas_loader_thread.wait()

        return result

    def locate_mouse(self) -> None:
        if self.annotation_volume is None:
            return

        widget = self.alignment_widget
        orientation = widget.volume_settings.orientation
        pitch = widget.volume_settings.pitch
        yaw = widget.volume_settings.yaw

        # Get global cursor position
        global_position = QtGui.QCursor.pos()

        # Convert it to a view position
        view_position = widget.view.mapFromGlobal(global_position)

        # Convert it to a scene position
        scene_position = widget.view.mapToScene(view_position)

        # Convert it to a pixmap position
        pixmap_position = widget.volume_pixmap.mapFromScene(scene_position).toTuple()
        # NOTE: there is no need to flip the X coordinate of the pixmap position even
        #       though the image undergoes `np.fliplr` when slicing. That is because
        #       pixmap coordinates increase from left to right which is correct for
        #       volume coordinates.

        # Compute position of pixmap centre
        pixmap_centre_position = widget.volume_pixmap.pixmap().size().toTuple()
        pixmap_centre_position = np.array(pixmap_centre_position) // 2

        # Compute relative cursor pixmap position from centre
        relative_pixmap_position = pixmap_position - pixmap_centre_position
        relative_pixmap_position = relative_pixmap_position  # X x Y not I x J

        # Convert to non-rotated coordinates
        match orientation:
            case Orientation.CORONAL:
                pixmap_coordinates = [
                    0,
                    relative_pixmap_position[1],
                    relative_pixmap_position[0],
                ]
            case Orientation.HORIZONTAL:
                pixmap_coordinates = [
                    relative_pixmap_position[1],
                    0,
                    relative_pixmap_position[0],
                ]
            case Orientation.SAGITTAL:
                pixmap_coordinates = [
                    relative_pixmap_position[0],
                    relative_pixmap_position[1],
                    0,
                ]
            case other:
                raise Exception(f"ASSERT NOT REACHED: {other}")
        pixmap_coordinates = np.array(pixmap_coordinates)

        # Apply rotation
        rotated_coordinates = apply_rotation(pixmap_coordinates, widget.volume_settings)

        # Add to slicing plane origin
        volume_centre = compute_centre(widget.volume_settings.shape)
        volume_origin = compute_origin(volume_centre, widget.volume_settings)

        volume_coordinates = volume_origin + rotated_coordinates
        volume_coordinates = np.array(list(map(int, volume_coordinates)))

        # Get the name of the structure at coordinates
        structure_name = self.annotation_volume.get_name_from_voxel(volume_coordinates)
        structure_string = f" ({structure_name})" if structure_name else ""

        # Convert volume coordinates to CCF coordinates
        ccf_coordinates = volume_coordinates * widget.volume_settings.resolution.value

        # Display output in status bar
        try_show_status_message(
            self.window(),
            f"CCF coordinates of cursor: "
            f"{', '.join(map(str, map(round, map(int, ccf_coordinates))))}"
            f"{structure_string}",
            0,
        )

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

    def update_workspace(self, workspace: Workspace) -> None:
        self.workspace = workspace

        # Sync states
        self.share_workspace_models()
        self.thumbnails_widget.connect_workspace(self.workspace)
        self.alignment_widget.prepare_slicer()

        # Block signals for improved responsiveness
        self.settings_widget.volume_settings_widget.blockSignals(True)
        self.settings_widget.histology_settings_widget.blockSignals(True)
        self.settings_widget.reload_settings()
        self.settings_widget.volume_settings_widget.blockSignals(False)
        self.settings_widget.histology_settings_widget.blockSignals(False)

        for index, slice_ in enumerate(self.workspace._histology_slices):
            if not os.path.exists(
                self.workspace.working_directory + os.sep + slice_.hash + ".json"
            ):
                continue

            self.thumbnails_widget.set_thumbnail_completed(index, True)

    # Tool bar slots
    @QtCore.Slot()
    def save_alignment(self) -> None:
        _module_logger.debug("Saving alignment.")

        self.workspace.save_alignment()
        try_show_status_message(self.window(), "Alignment saved.")
        self.thumbnails_widget.set_thumbnail_completed(
            self.workspace.current_aligner_image_index, True
        )

        self.alignment_saved.emit()

    @QtCore.Slot()
    def load_alignment(self) -> None:
        _module_logger.debug("Loading alignment.")

        self.workspace.load_alignment()
        try_show_status_message(self.window(), "Alignment loaded.")
        self.share_workspace_models()
        self.settings_widget.reload_settings()

    @QtCore.Slot()
    def delete_alignment(self) -> None:
        _module_logger.debug("Alignment deletion initiated.")

        # Build dialog pop-up to ask for confirmation
        dialog = ConfirmDeleteDialog(self)
        dialog.accepted.connect(self._delete_alignment)
        dialog.rejected.connect(
            lambda: _module_logger.debug("Alignment deletion cancelled.")
        )
        dialog.open()

    @QtCore.Slot()
    def _delete_alignment(self) -> None:
        _module_logger.debug(
            f"Deleting alignment for: {self.workspace.current_aligner_image_hash}"
        )

        self.workspace.delete_alignment()
        try_show_status_message(self.window(), "Deleted alignment", 2000)
        self.thumbnails_widget.set_thumbnail_completed(
            self.workspace.current_aligner_image_index, False
        )

        self.alignment_deleted.emit()

    @QtCore.Slot()
    def begin_landmark_registration(self) -> None:
        window = LandmarkRegistrationWindow(self)

        match self.workspace.alignment_settings.volume_settings.orientation:
            case Orientation.CORONAL:
                general_zoom = 2.0
            case Orientation.HORIZONTAL:
                general_zoom = 1.5
            case Orientation.SAGITTAL:
                general_zoom = 1.7
            case _:
                raise Exception("ASSERT NOT REACHED")

        window.update_reference_pixmap(
            self.alignment_widget.volume_pixmap, general_zoom
        )
        window.update_histology_pixmap(self.alignment_widget.histology_pixmap)

        window.resize(
            QtCore.QSize(
                round(self.width() * 0.95),
                round(self.height() * 0.95),
            )
        )
        window.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)

        window.applied.connect(
            self.alignment_widget.update_alignment_from_landmark_registration
        )
        window.applied.connect(self.settings_widget.reload_settings)

        window.show()

    # General slots
    @QtCore.Slot()
    def open_atlas_in_aligner(self) -> None:
        _module_logger.debug("Opening atlas.")

        # noinspection PyTypeChecker
        self.workspace.alignment_settings.volume_settings.shape = (
            self.alignment_widget.volume_slicer.volume.shape
        )

        try:
            self.alignment_widget.update_volume_pixmap(rescale=True)
        except ValueError as error:
            _module_logger.error("Could not open atlas volume.")
            _module_logger.error(error)
            return

        self.settings_widget.volume_settings_widget.update_offset_spin_box_limits()
        self.settings_widget.volume_settings_widget.reload_settings()
        self.settings_widget.volume_settings_widget.setEnabled(True)

        # Easiest way to trigger scale ratio calculations
        self.alignment_widget.resizeEvent(
            QtGui.QResizeEvent(
                self.alignment_widget.size(), self.alignment_widget.size()
            )
        )

        self.volume_opened.emit()

    @QtCore.Slot()
    def open_image_in_aligner(self, index: int) -> None:
        _module_logger.debug("Opening histology.")

        old_index = self.workspace.current_aligner_image_index

        image = self.workspace.get_image(index)
        if image is None:
            if len(self.workspace._histology_slices) > 0:
                _module_logger.error(
                    f"Failed retrieving image at index {index}, index out of range."
                )
            return

        self.alignment_widget.update_histological_slice(image)
        self.alignment_widget.update_background_alpha(
            self.background_alpha_spin_box.value()
        )
        self.alignment_widget.update_global_alpha(
            self.alpha_widget.global_alpha_slider.value()
        )

        self.settings_widget.histology_settings_widget.setEnabled(True)

        if old_index is not None:
            self.thumbnails_widget.make_thumbnail_at_active(old_index)
        if old_index != index:
            self.thumbnails_widget.make_thumbnail_at_active(index)

        self.histology_opened.emit()
