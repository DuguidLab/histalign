# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets

from histalign.backend.models import (
    MeasureSettings,
    QuantificationMeasure,
    QuantificationSettings,
)
from histalign.backend.quantification import QuantificationThread
from histalign.backend.workspace import Workspace
from histalign.frontend.common_widgets import (
    AnimatedCheckBox,
    ProjectDirectoriesComboBox,
    StructureFinderDialog,
    StructureTagHolderWidget,
    TitleFrame,
)
from histalign.frontend.quantification.analysis_parameters_widgets import (
    AnalysisParametersWidget,
    AverageFluorescenceAnalysisParametersWidget,
    CorticalDepthAnalysisParametersWidget,
)


class ZStackFrame(TitleFrame):
    def __init__(
        self,
        title: str = "Z stacks",
        bold: bool = False,
        italic: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(title, bold, italic, parent)

        #
        check_box = AnimatedCheckBox()

        check_box.checkStateChanged.connect(
            lambda x: self.regex_line_edit.setEnabled(x == QtCore.Qt.CheckState.Checked)
        )

        self.check_box = check_box

        #
        # setFormAlignment doesn't work for right-aligned so make sub-layout
        check_box_layout = QtWidgets.QHBoxLayout()

        check_box_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        check_box_layout.addWidget(check_box)

        #
        regex_line_edit = QtWidgets.QLineEdit()

        regex_line_edit.setEnabled(False)

        self.regex_line_edit = regex_line_edit

        #
        layout = QtWidgets.QFormLayout()

        layout.addRow("Are images Z stacks?", check_box_layout)
        layout.addRow("Z stack regex", regex_line_edit)

        self.setLayout(layout)

        #
        self.setContentsMargins(
            1, self.contentsMargins().top(), 1, self.contentsMargins().bottom()
        )


class ChannelFrame(TitleFrame):
    def __init__(
        self,
        title: str = "Multichannel images",
        bold: bool = False,
        italic: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(title, bold, italic, parent)

        #
        check_box = AnimatedCheckBox()

        check_box.checkStateChanged.connect(
            lambda x: self.regex_line_edit.setEnabled(x == QtCore.Qt.CheckState.Checked)
        )
        check_box.checkStateChanged.connect(
            lambda x: self.quantification_channel_line_edit.setEnabled(
                x == QtCore.Qt.CheckState.Checked
            )
        )

        self.check_box = check_box

        #
        # setFormAlignment doesn't work for right-aligned so make sub-layout
        check_box_layout = QtWidgets.QHBoxLayout()

        check_box_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        check_box_layout.addWidget(check_box)

        #
        regex_line_edit = QtWidgets.QLineEdit()

        regex_line_edit.setEnabled(False)

        self.regex_line_edit = regex_line_edit

        #
        quantification_channel_line_edit = QtWidgets.QLineEdit()

        quantification_channel_line_edit.setEnabled(False)

        self.quantification_channel_line_edit = quantification_channel_line_edit

        #
        layout = QtWidgets.QFormLayout()

        layout.addRow("Are images multichannel?", check_box_layout)
        layout.addRow("Channel regex", regex_line_edit)
        layout.addRow("Quantification channel", quantification_channel_line_edit)

        self.setLayout(layout)

        #
        self.setContentsMargins(
            1, self.contentsMargins().top(), 1, self.contentsMargins().bottom()
        )


class QuantificationParametersFrame(TitleFrame):
    def __init__(
        self,
        title: str = "Quantification parameters",
        bold: bool = True,
        italic: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(title, bold, italic, parent)

        #
        directory_widget = ProjectDirectoriesComboBox()

        self.directory_widget = directory_widget

        #
        z_stack_frame = ZStackFrame()

        self.z_stack_frame = z_stack_frame

        #
        multichannel_frame = ChannelFrame()

        self.multichannel_frame = multichannel_frame

        #
        layout = QtWidgets.QGridLayout()

        layout.setContentsMargins(15, 15, 15, 15)

        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(1, 1)
        layout.setHorizontalSpacing(20)

        layout.addWidget(QtWidgets.QLabel("Alignment directory"), 0, 0)
        layout.addWidget(directory_widget, 0, 1)

        layout.addWidget(z_stack_frame, 1, 0, 1, -1)

        layout.addWidget(multichannel_frame, 2, 0, 1, -1)

        self.setLayout(layout)


class AnalysisParametersFrame(TitleFrame):
    def __init__(
        self,
        title: str = "Analysis parameters",
        bold: bool = True,
        italic: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(title, bold, italic, parent)

        #
        self.current_analysis_widget = None
        self._analysis_widgets = []

        #
        measure_label = QtWidgets.QLabel("Measure")

        self.measure_label = measure_label

        #
        measure_widget = QtWidgets.QComboBox()

        measure_widget.addItems(["Average fluorescence", "Cortical depth"])

        measure_widget.currentTextChanged.connect(self.update_analysis_widget)

        self.measure_widget = measure_widget

        #
        layout = QtWidgets.QGridLayout()

        layout.setContentsMargins(15, 15, 15, 15)

        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(1, 1)
        layout.setHorizontalSpacing(20)

        layout.addWidget(measure_label, 0, 0)
        layout.addWidget(measure_widget, 0, 1)

        self.setLayout(layout)

        #
        measure_widget.currentTextChanged.emit(measure_widget.currentText())

    def get_analysis_widget(
        self, widget_type: type[AnalysisParametersWidget]
    ) -> AnalysisParametersWidget:
        for analysis_widget in self._analysis_widgets:
            if isinstance(analysis_widget, widget_type):
                return analysis_widget

        analysis_widget = widget_type()
        analysis_widget.layout().setContentsMargins(0, 0, 0, 0)
        analysis_widget.layout().setHorizontalSpacing(20)
        analysis_widget.layout().setColumnStretch(1, 1)
        self._analysis_widgets.append(analysis_widget)
        return analysis_widget

    def replace_analysis_widget(self, widget: AnalysisParametersWidget) -> None:
        if self.current_analysis_widget is not None:
            current_widget_index = self.layout().indexOf(self.current_analysis_widget)
            self.layout().takeAt(current_widget_index).widget().hide()

        self.layout().addWidget(widget, 1, 0, -1, -1)
        self.current_analysis_widget = widget
        widget.show()

    def update_label_column_width(self) -> None:
        column_width = max(
            self.measure_label.sizeHint().width(),
            self.current_analysis_widget.get_column_width(),
        )
        self.layout().setColumnMinimumWidth(0, column_width)
        self.current_analysis_widget.layout().setColumnMinimumWidth(0, column_width)

    @QtCore.Slot()
    def update_analysis_widget(self, name: str) -> None:
        if name == "Average fluorescence":
            widget_type = AverageFluorescenceAnalysisParametersWidget
        elif name == "Cortical depth":
            widget_type = CorticalDepthAnalysisParametersWidget
        else:
            raise Exception("ASSERT NOT REACHED")

        widget = self.get_analysis_widget(widget_type)
        self.replace_analysis_widget(widget)

        self.update_label_column_width()


class StructureFrame(TitleFrame):
    def __init__(
        self,
        title: str = "Structures",
        bold: bool = True,
        italic: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(title, bold, italic, parent)

        #
        pop_up = StructureFinderDialog(self)

        self.pop_up = pop_up

        #
        structures_button = QtWidgets.QPushButton("Add/remove structures")

        structures_button.clicked.connect(lambda: self.pop_up.resize(self.size()))
        structures_button.clicked.connect(self.pop_up.exec)

        self.structures_button = structures_button

        #
        structure_tag_holder = StructureTagHolderWidget()

        model = pop_up.finder_widget.tree_view.model()
        model.item_checked.connect(structure_tag_holder.add_tag_from_index)
        model.item_unchecked.connect(structure_tag_holder.remove_tag_from_index)

        self.structure_tag_holder = structure_tag_holder

        #
        layout = QtWidgets.QGridLayout()

        layout.addWidget(structures_button, 0, 0, 1, -1)
        layout.addWidget(structure_tag_holder, 1, 0, 1, -1)

        self.setLayout(layout)


class PrepareWidget(QtWidgets.QWidget):
    project_directory: Path

    analysis_parameters_frame: AnalysisParametersFrame
    quantification_parameters_frame: QuantificationParametersFrame
    parameters_layout: QtWidgets.QHBoxLayout()
    progress_bar: QtWidgets.QProgressBar
    run_button: QtWidgets.QPushButton
    structures_frame: StructureFrame

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        quantification_parameters_frame = QuantificationParametersFrame()

        self.quantification_parameters_frame = quantification_parameters_frame

        #
        analysis_parameters_frame = AnalysisParametersFrame()

        self.analysis_parameters_frame = analysis_parameters_frame

        #
        structures_frame = StructureFrame()

        self.structures_frame = structures_frame

        #
        left_column_layout = QtWidgets.QVBoxLayout()

        left_column_layout.setContentsMargins(0, 0, 0, 0)

        left_column_layout.addWidget(quantification_parameters_frame)
        left_column_layout.addWidget(analysis_parameters_frame)

        #
        parameters_layout = QtWidgets.QHBoxLayout()

        parameters_layout.setContentsMargins(0, 0, 0, 0)

        parameters_layout.addLayout(left_column_layout)
        parameters_layout.addWidget(structures_frame)

        self.parameters_layout = parameters_layout

        #
        run_button = QtWidgets.QPushButton("Run")

        run_button.clicked.connect(self.run_quantification)

        self.run_button = run_button

        #
        progress_bar = QtWidgets.QProgressBar()

        self.progress_bar = progress_bar

        #
        progress_layout = QtWidgets.QHBoxLayout()

        progress_layout.setContentsMargins(
            quantification_parameters_frame.contentsMargins().left() - 1,
            0,
            quantification_parameters_frame.contentsMargins().right() - 1,
            0,
        )

        progress_layout.addWidget(run_button)
        progress_layout.addWidget(progress_bar, stretch=1)

        #
        layout = QtWidgets.QVBoxLayout()

        layout.addLayout(parameters_layout)
        layout.addLayout(progress_layout)

        self.setLayout(layout)

    def parse_project(self, project_directory: Path) -> None:
        self.project_directory = project_directory
        self.quantification_parameters_frame.directory_widget.parse_project(
            project_directory
        )

    def set_quantification_running_state(self, enabled: bool) -> None:
        self.parameters_layout.setEnabled(not enabled)
        self.run_button.setEnabled(not enabled)

    def collect_quantification_settings(self) -> MeasureSettings:
        settings = self.analysis_parameters_frame.current_analysis_widget.settings

        if self.analysis_parameters_frame.current_analysis_widget.includes_structures:
            model = self.structures_frame.pop_up.finder_widget.tree_view.model()
            structures = [node.name for node in model.get_checked_items()]
            settings.structures = structures

        return settings

    @QtCore.Slot()
    def run_quantification(self) -> None:
        self.set_quantification_running_state(True)

        self.progress_bar.resetFormat()

        directory_hash = Workspace.generate_directory_hash(
            self.quantification_parameters_frame.directory_widget.currentText()
        )

        quantification_settings = QuantificationSettings(
            alignment_directory=str(self.project_directory / directory_hash),
            original_directory=self.quantification_parameters_frame.directory_widget.currentText(),
            quantification_measure=QuantificationMeasure(
                "_".join(
                    self.analysis_parameters_frame.measure_widget.currentText()
                    .lower()
                    .split(" ")
                )
            ),
            fast_rescale=True,
            fast_transform=True,
            measure_settings=self.collect_quantification_settings(),
        )

        quantification_thread = QuantificationThread(quantification_settings, self)
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
        quantification_thread.results_computed.connect(
            self.display_finished_progress_bar
        )

        quantification_thread.start()

    @QtCore.Slot()
    def display_finished_progress_bar(self) -> None:
        self.progress_bar.setMaximum(1_000_000)
        self.progress_bar.setValue(999_999)
        self.progress_bar.setFormat("Done")
