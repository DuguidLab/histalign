# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import typing

from PySide6 import QtCore, QtWidgets

from histalign.frontend.registration.HistologySettingsWidget import (
    HistologySettingsWidget,
)
from histalign.frontend.registration.VolumeSettingsWidget import VolumeSettingsWidget


class SettingsDockWidget(QtWidgets.QDockWidget):
    histology_settings_widget: HistologySettingsWidget
    volume_settings_widget: VolumeSettingsWidget

    def __init__(
        self,
        parent: typing.Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)

        self.histology_settings_widget = HistologySettingsWidget()

        self.volume_settings_widget = VolumeSettingsWidget()

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.histology_settings_widget)
        layout.addWidget(self.volume_settings_widget)

        container_widget = QtWidgets.QWidget()
        container_widget.setLayout(layout)

        self.setWidget(container_widget)
