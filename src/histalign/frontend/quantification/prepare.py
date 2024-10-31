# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets

from histalign.backend.models import QuantificationSettings
from histalign.backend.quantification import QuantificationThread
from histalign.backend.workspace import Workspace
from histalign.frontend.common_widgets import (
    ProjectDirectoriesComboBox,
    SelectedStructuresWidget,
)
from histalign.frontend.quantification.measure_widgets import (
    AverageFluorescenceWidget,
    CorticalDepthWidget,
)


class PrepareWidget(QtWidgets.QWidget):
    project_directory: Path

    form_layout: QtWidgets.QFormLayout
    directory_widget: ProjectDirectoriesComboBox
    approach_widget: QtWidgets.QComboBox
    measure_widget: QtWidgets.QComboBox
    structures_widget: SelectedStructuresWidget
    progress_layout: QtWidgets.QHBoxLayout
    run_button: QtWidgets.QPushButton
    progress_bar: QtWidgets.QProgressBar

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        directory_widget = ProjectDirectoriesComboBox()

        self.directory_widget = directory_widget

        #
        measure_widget = QtWidgets.QComboBox()

        measure_widget.addItems(["Average fluorescence", "Cortical depth"])

        measure_widget.currentTextChanged.connect(self.update_layout)

        self.measure_widget = measure_widget

        #
        average_fluorescence_widget = AverageFluorescenceWidget(animated=False)

        # Skip the first animation as this is the default visible widget
        average_fluorescence_widget.show()
        average_fluorescence_widget.animated = True

        average_fluorescence_widget.setMinimumHeight(0)
        average_fluorescence_widget.setMaximumHeight(0)

        self.average_fluorescence_widget = average_fluorescence_widget

        #
        cortical_depth_widget = CorticalDepthWidget()

        cortical_depth_widget.setMinimumHeight(0)
        cortical_depth_widget.setMaximumHeight(0)
        cortical_depth_widget.setHidden(True)

        self.cortical_depth_widget = cortical_depth_widget

        #
        form_layout = QtWidgets.QFormLayout()
        form_layout.addRow("Directory", directory_widget)
        form_layout.addRow("Measure", measure_widget)
        form_layout.addRow(average_fluorescence_widget)
        form_layout.addRow(cortical_depth_widget)

        self.form_layout = form_layout

        #
        run_button = QtWidgets.QPushButton("Run quantification")
        run_button.clicked.connect(self.run_quantification)

        self.run_button = run_button

        #
        progress_bar = QtWidgets.QProgressBar()

        self.progress_bar = progress_bar

        #
        progress_layout = QtWidgets.QHBoxLayout()
        progress_layout.addWidget(run_button)
        progress_layout.addWidget(progress_bar, stretch=1)

        self.progress_layout = progress_layout

        #
        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(form_layout)
        layout.addLayout(progress_layout)
        self.setLayout(layout)

    def parse_project(self, project_directory: Path) -> None:
        self.project_directory = project_directory
        self.directory_widget.parse_project(project_directory)

    def set_quantification_running_state(self, enabled: bool) -> None:
        self.form_layout.setEnabled(not enabled)
        self.run_button.setEnabled(not enabled)

    def toggle_measure_widget(self, widget: QtWidgets.QWidget) -> None:
        widgets_to_hide = [
            self.average_fluorescence_widget,
            self.cortical_depth_widget,
        ]
        if widget not in widgets_to_hide:
            raise ValueError(f"Received unknown widget to toggle ('{widget}').")
        widgets_to_hide.remove(widget)

        for widget_to_hide in widgets_to_hide:
            widget_to_hide.hide()

        widget.show()

    @QtCore.Slot()
    def run_quantification(self) -> None:
        self.set_quantification_running_state(True)

        directory_hash = Workspace.generate_directory_hash(
            self.directory_widget.currentText()
        )

        settings = QuantificationSettings(
            approach=self.approach_widget.currentText(),
            alignment_directory=str(self.project_directory / directory_hash),
            original_directory=self.directory_widget.currentText(),
            quantification_measure="_".join(
                self.measure_widget.currentText().lower().split(" ")
            ),
            structures=list(self.structures_widget.structure_tags_mapping.keys()),
            fast_rescale=True,
            fast_transform=True,
        )

        quantification_thread = QuantificationThread(settings, self)
        quantification_thread.progress_count_computed.connect(
            self.progress_bar.setMaximum
        )
        quantification_thread.progress_changed.connect(self.progress_bar.setValue)
        quantification_thread.results_computed.connect(
            lambda: self.set_quantification_running_state(False)
        )
        quantification_thread.results_computed.connect(
            lambda: self.progress_bar.setMaximum(1)
        )
        quantification_thread.results_computed.connect(self.progress_bar.reset)

        quantification_thread.start()

    @QtCore.Slot()
    def update_layout(self, value: str) -> None:
        match value:
            case "Average fluorescence":
                self.toggle_measure_widget(self.average_fluorescence_widget)
            case "Cortical depth":
                self.toggle_measure_widget(self.cortical_depth_widget)
            case _:
                raise ValueError("Invalid measure.")
