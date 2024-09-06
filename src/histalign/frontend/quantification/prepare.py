# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import os
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.models import QuantificationSettings
from histalign.backend.workspace import QuantificationThread, Workspace
from histalign.frontend.common_widgets import (
    ProjectDirectoriesComboBox,
    SelectedStructuresWidget,
)


class QuantificationMeasuresComboBox(QtWidgets.QComboBox):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.addItems(
            [
                "Average fluorescence",
                "Cell count",
            ]
        )


class PrepareWidget(QtWidgets.QWidget):
    project_directory: str

    project_directories_combo_box: ProjectDirectoriesComboBox
    quantification_measures_combo_box: QuantificationMeasuresComboBox
    selected_structures_widget: SelectedStructuresWidget
    fast_rescale_checkbox: QtWidgets.QCheckBox
    fast_transform_checkbox: QtWidgets.QCheckBox
    run_button: QtWidgets.QPushButton
    progress_bar: QtWidgets.QProgressBar

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        # Instantiating first to use as row height
        selected_structures_widget = SelectedStructuresWidget()

        self.selected_structures_widget = selected_structures_widget

        #
        project_directories_combo_box = ProjectDirectoriesComboBox()
        project_directories_combo_box.setFixedHeight(
            selected_structures_widget.layout().sizeHint().height()
        )

        self.project_directories_combo_box = project_directories_combo_box

        #
        quantification_methods_combo_box = QuantificationMeasuresComboBox()
        quantification_methods_combo_box.setFixedHeight(
            selected_structures_widget.layout().sizeHint().height()
        )

        self.quantification_measures_combo_box = quantification_methods_combo_box

        #
        fast_rescale_checkbox = QtWidgets.QCheckBox()
        fast_rescale_checkbox.setChecked(True)
        fast_rescale_checkbox.setFixedHeight(
            selected_structures_widget.layout().sizeHint().height()
        )

        self.fast_rescale_checkbox = fast_rescale_checkbox

        #
        fast_transform_checkbox = QtWidgets.QCheckBox()
        fast_transform_checkbox.setChecked(True)
        fast_transform_checkbox.setFixedHeight(
            selected_structures_widget.layout().sizeHint().height()
        )

        self.fast_transform_checkbox = fast_transform_checkbox

        #
        # Could not accomplish alignment properly with QFormLayout...
        configuration_layout = QtWidgets.QGridLayout()

        configuration_layout.addWidget(QtWidgets.QLabel("Directory"), 0, 0)
        configuration_layout.addWidget(project_directories_combo_box, 0, 1)

        configuration_layout.addWidget(QtWidgets.QLabel("Measure"), 1, 0)
        configuration_layout.addWidget(quantification_methods_combo_box, 1, 1)

        configuration_layout.addWidget(QtWidgets.QLabel("Structures"), 2, 0)
        configuration_layout.addWidget(selected_structures_widget, 2, 1)

        configuration_layout.addWidget(QtWidgets.QLabel("Fast rescale"), 3, 0)
        configuration_layout.addWidget(
            fast_rescale_checkbox,
            3,
            1,
            alignment=QtCore.Qt.AlignmentFlag.AlignRight,
        )

        configuration_layout.addWidget(QtWidgets.QLabel("Fast transform"), 4, 0)
        configuration_layout.addWidget(
            fast_transform_checkbox,
            4,
            1,
            alignment=QtCore.Qt.AlignmentFlag.AlignRight,
        )

        #
        run_button = QtWidgets.QPushButton("Run")
        run_button.clicked.connect(self.run_quantification)

        self.run_button = run_button

        #
        progress_bar = QtWidgets.QProgressBar()

        self.progress_bar = progress_bar

        #
        bottom_layout = QtWidgets.QHBoxLayout()
        bottom_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignBottom)

        bottom_layout.addWidget(run_button, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        bottom_layout.addWidget(progress_bar)

        #
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(configuration_layout)
        main_layout.addLayout(bottom_layout)

        #
        self.setLayout(main_layout)

    def run_quantification(self) -> None:
        self.run_button.setEnabled(False)

        directory_hash = f"{Workspace.generate_directory_hash(self.project_directories_combo_box.currentText())}"

        settings = QuantificationSettings(
            alignment_directory=f"{self.project_directory}{os.sep}{directory_hash}",
            original_directory=self.project_directories_combo_box.currentText(),
            quantification_measure="_".join(
                self.quantification_measures_combo_box.currentText().lower().split(" ")
            ),
            structures=list(
                self.selected_structures_widget.structure_tags_mapping.keys()
            ),
            fast_rescale=self.fast_rescale_checkbox.isChecked(),
            fast_transform=self.fast_transform_checkbox.isChecked(),
        )

        quantification_thread = QuantificationThread(settings, self)

        quantification_thread.progress_count_computed.connect(
            self.progress_bar.setMaximum
        )
        quantification_thread.progress_changed.connect(self.progress_bar.setValue)
        quantification_thread.results_computed.connect(self.run_button.setEnabled(True))

        quantification_thread.results_computed.connect(
            lambda: self.progress_bar.setMaximum(1)
        )
        quantification_thread.results_computed.connect(self.progress_bar.reset)

        quantification_thread.start()

    def parse_project(self, project_path: str) -> None:
        self.project_directory = str(Path(project_path).parent)
        self.project_directories_combo_box.parse_project(project_path)
