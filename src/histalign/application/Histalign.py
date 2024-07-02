# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

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
from histalign.application.SettingsDockWidget import SettingsDockWidget
from histalign.application.VolumeSettings import VolumeSettings
from histalign.application.VolumeSettingsWidget import VolumeSettingsWidget


class Histalign(QtWidgets.QMainWindow):
    alignment_parameters: AlignmentParameterAggregator

    def __init__(
        self,
        histology_slice_file_path: str,
        average_volume_file_path: str,
        fullscreen: bool,
        parent: typing.Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("Histalign")

        # Set up alignment widget
        alignment_widget = AlignmentWidget(self)
        alignment_widget.load_volume(average_volume_file_path)
        alignment_widget.load_histological_slice(histology_slice_file_path)

        self.setCentralWidget(alignment_widget)

        # Dock widgets
        self.setCorner(QtCore.Qt.TopRightCorner, QtCore.Qt.RightDockWidgetArea)
        self.setCorner(QtCore.Qt.BottomRightCorner, QtCore.Qt.RightDockWidgetArea)

        # Set up alpha widget
        alpha_dock_widget = AlphaDockWidget(self)
        alpha_dock_widget.alpha_slider.valueChanged.connect(
            alignment_widget.update_histology_alpha
        )
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, alpha_dock_widget)

        # Set up the settings widget
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

        # Set up alignment buttons
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
        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, alignment_button_dock_widget)

        if fullscreen:
            self.showMaximized()

        # Alignment parameters aggregator
        volume_size = alignment_widget.volume_pixmap.pixmap().size()
        histology_size = alignment_widget.histology_pixmap.pixmap().size()
        self.alignment_parameters = AlignmentParameterAggregator(
            volume_file_path=average_volume_file_path,
            volume_pixel_width=volume_size.width(),
            volume_pixel_height=volume_size.height(),
            histology_file_path=histology_slice_file_path,
            histology_pixel_width=histology_size.width(),
            histology_pixel_height=histology_size.height(),
        )

        # These need to be connected after instantiating the `alignment_parameters`
        alignment_widget.volume_scale_ratio_changed.connect(
            lambda x: self.aggregate_settings({"volume_scaling_factor": x})
        )
        alignment_widget.histology_scale_ratio_changed.connect(
            lambda x: self.aggregate_settings({"histology_scaling_factor": x})
        )

    @QtCore.Slot()
    def aggregate_settings(
        self, settings: dict | HistologySettings | VolumeSettings
    ) -> None:
        if not isinstance(settings, dict):
            settings = settings.model_dump()

        new_alignment_parameters = self.alignment_parameters.model_copy(update=settings)

        AlignmentParameterAggregator.model_validate(new_alignment_parameters)
        self.alignment_parameters = new_alignment_parameters

    @QtCore.Slot()
    def save_alignment_parameters(self) -> None:
        print(self.alignment_parameters.model_dump_json())
        with open("registration_parameters.json", "w") as json_handle:
            json_handle.write(self.alignment_parameters.model_dump_json())
