# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.frontend.common_widgets import (
    CollapsibleWidget,
    ProjectDirectoriesComboBox,
    SwitchWidgetContainer,
    VerticalSeparator,
)


class PreprocessingCollapsibleWidget(CollapsibleWidget):
    enabled_widget: QtWidgets.QCheckBox

    def __init__(
        self,
        title: str = "",
        animation_duration: int = 500,
        expanded: bool = True,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(title, animation_duration, expanded, parent)

        #
        enabled_widget = QtWidgets.QCheckBox()

        self.enabled_widget = enabled_widget

        #
        self.add_row("Enabled", enabled_widget)
        self.add_row(None, VerticalSeparator())


class BrightSpotRemovalWidget(PreprocessingCollapsibleWidget):
    threshold_widget: QtWidgets.QLineEdit

    def __init__(
        self,
        animation_duration: int = 500,
        expanded: bool = True,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__("Bright spot removal", animation_duration, False, parent)

        #
        threshold_widget = QtWidgets.QLineEdit("0")
        threshold_widget.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        threshold_widget.setValidator(QtGui.QIntValidator(0, 999_999))

        font_metrics = threshold_widget.fontMetrics()
        width = font_metrics.size(QtCore.Qt.TextFlag.TextSingleLine, "0" * 10).width()
        threshold_widget.setFixedWidth(width)

        self.threshold_widget = threshold_widget

        #
        self.add_row("Threshold", threshold_widget)

        #
        self.set_initial_state(expanded)

    @property
    def threshold(self) -> int:
        # TODO: Allow percentage values for a better UX
        # Mask validation should ensure this does not fail
        return int(self.threshold_widget.text())


class BackgroundRemovalWidget(PreprocessingCollapsibleWidget):
    max_intensity_widget: QtWidgets.QLineEdit
    ignore_zero_checkbox: QtWidgets.QCheckBox

    def __init__(
        self,
        animation_duration: int = 500,
        expanded: bool = True,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__("Background removal", animation_duration, False, parent)

        #
        max_intensity_widget = QtWidgets.QLineEdit("0")
        max_intensity_widget.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        max_intensity_widget.setValidator(QtGui.QIntValidator(0, 999_999))

        font_metrics = max_intensity_widget.fontMetrics()
        width = font_metrics.size(QtCore.Qt.TextFlag.TextSingleLine, "0" * 10).width()
        max_intensity_widget.setFixedWidth(width)

        self.max_intensity_widget = max_intensity_widget

        #
        ignore_zero_checkbox = QtWidgets.QCheckBox(checked=True)

        self.ignore_zero_checkbox = ignore_zero_checkbox

        #
        self.add_row("Maximum background intensity", max_intensity_widget)
        self.add_row("Ignore zeros", ignore_zero_checkbox)

        #
        self.set_initial_state(expanded)

    @property
    def ignore_zero(self) -> bool:
        return self.ignore_zero_checkbox.isChecked()

    @property
    def max_intensity(self) -> int:
        return int(self.max_intensity_widget.text())


class AutoContrastWidget(PreprocessingCollapsibleWidget):
    passes_widget: QtWidgets.QLineEdit
    normalise_widget: QtWidgets.QCheckBox

    def __init__(
        self,
        animation_duration: int = 500,
        expanded: bool = True,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__("Auto-contrast", animation_duration, False, parent)

        #
        passes_widget = QtWidgets.QLineEdit("0")
        passes_widget.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        passes_widget.setValidator(QtGui.QIntValidator(0, 99))

        font_metrics = passes_widget.fontMetrics()
        width = font_metrics.size(QtCore.Qt.TextFlag.TextSingleLine, "0" * 10).width()
        passes_widget.setFixedWidth(width)

        self.passes_widget = passes_widget

        #
        normalise_widget = QtWidgets.QCheckBox(checked=True)

        self.normalise_widget = normalise_widget

        #
        self.add_row("Passes", passes_widget)
        self.add_row("Normalise output", normalise_widget)

        #
        self.set_initial_state(expanded)

    @property
    def passes(self) -> int:
        return int(self.passes_widget.text())

    @property
    def normalise(self) -> bool:
        return self.normalise_widget.isChecked()


class PrepareWidget(QtWidgets.QWidget):
    project_directory: Path

    project_directories_combo_box: ProjectDirectoriesComboBox
    preprocessing_switch_container: SwitchWidgetContainer
    run_button: QtWidgets.QPushButton
    progress_bar: QtWidgets.QProgressBar

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        project_directories_combo_box = ProjectDirectoriesComboBox()

        self.project_directories_combo_box = project_directories_combo_box

        #
        preprocessing_container_widget = SwitchWidgetContainer()

        preprocessing_container_widget.add_widget(BrightSpotRemovalWidget())
        preprocessing_container_widget.add_widget(BackgroundRemovalWidget())
        preprocessing_container_widget.add_widget(AutoContrastWidget())

        self.preprocessing_switch_container = preprocessing_container_widget

        #
        run_button = QtWidgets.QPushButton("Run")
        # run_button.clicked.connect(self.run_quantification)

        self.run_button = run_button

        #
        progress_bar = QtWidgets.QProgressBar()

        self.progress_bar = progress_bar

        #
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        top_layout.addWidget(
            QtWidgets.QLabel("Directory"), alignment=QtCore.Qt.AlignmentFlag.AlignLeft
        )
        top_layout.addWidget(project_directories_combo_box, stretch=1)

        #
        bottom_layout = QtWidgets.QHBoxLayout()
        bottom_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignBottom)

        bottom_layout.addWidget(run_button, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        bottom_layout.addWidget(progress_bar)

        #
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addWidget(preprocessing_container_widget, stretch=1)
        main_layout.addLayout(bottom_layout)

        self.setLayout(main_layout)

    def parse_project(self, project_directory: Path) -> None:
        self.project_directory = project_directory
        self.project_directories_combo_box.parse_project(project_directory)
