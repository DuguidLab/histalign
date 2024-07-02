# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import time
import typing

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.application.AlignmentButtonDockWidget import AlignmentButtonDockWidget
from histalign.application.AlignmentWidget import AlignmentWidget
from histalign.application.AlphaDockWidget import AlphaDockWidget
from histalign.application.HistologySettingsWidget import HistologySettingsWidget
from histalign.application.SettingsDockWidget import SettingsDockWidget
from histalign.application.VolumeSettingsWidget import VolumeSettingsWidget


class Histalign(QtWidgets.QMainWindow):
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
        settings_dock_widget.histology_settings_widget.values_changed.connect(
            alignment_widget.update_histology_pixmap
        )
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, settings_dock_widget)

        # Set up alignment buttons
        alignment_button_dock_widget = AlignmentButtonDockWidget()
        alignment_button_dock_widget.reset_volume.clicked.connect(
            settings_dock_widget.volume_settings_widget.reset_to_defaults
        )
        alignment_button_dock_widget.reset_histology.clicked.connect(
            settings_dock_widget.histology_settings_widget.reset_to_defaults
        )
        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, alignment_button_dock_widget)

        if fullscreen:
            self.showMaximized()
