# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Any, Optional

from PySide6 import QtCore, QtWidgets
import numpy as np
import pandas as pd

from histalign.backend.models import QuantificationResults
from histalign.frontend.common_widgets import (
    Canvas,
    OneHeaderFrameLayout,
    ProjectDirectoriesComboBox,
    SliceNamesComboBox,
    TableWidget,
)


class SliceResultsSummaryWidget(QtWidgets.QFrame):
    def __init__(
        self,
        file_name: str,
        data: dict[str, Any],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        #
        main_layout = OneHeaderFrameLayout(file_name)

        #
        table_widget = TableWidget(len(data), ["Structure", "Measure"])
        for i, (structure, measure) in enumerate(data.items()):
            table_widget.setItem(i, 0, QtWidgets.QTableWidgetItem(structure))
            table_widget.setItem(i, 1, QtWidgets.QTableWidgetItem(str(measure)))

        main_layout.add_widget(table_widget)

        self.setLayout(main_layout)

        self.setFrameStyle(QtWidgets.QFrame.Shape.Box | QtWidgets.QFrame.Shadow.Plain)
        self.setLineWidth(2)


class ResultsSummaryWidget(QtWidgets.QFrame):
    def __init__(
        self, results: QuantificationResults, parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)

        #
        main_layout = OneHeaderFrameLayout(str(results.settings.original_directory))

        #
        table_layout = QtWidgets.QGridLayout()

        table_layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMaximumSize)
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.setHorizontalSpacing(20)
        table_layout.setVerticalSpacing(10)

        for index, (file_name, result) in enumerate(results.data.items()):
            slice_summary = SliceResultsSummaryWidget(file_name, result)

            table_layout.addWidget(slice_summary, *divmod(index, 2))

        main_layout.add_layout(table_layout)

        self.setLayout(main_layout)

        self.setFrameStyle(QtWidgets.QFrame.Shape.Box | QtWidgets.QFrame.Shadow.Plain)
        self.setLineWidth(2)


class StatisticWidget(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        minimum_line_edit = QtWidgets.QLineEdit()

        minimum_line_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        self.minimum_line_edit = minimum_line_edit

        #
        maximum_line_edit = QtWidgets.QLineEdit()

        maximum_line_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        self.maximum_line_edit = maximum_line_edit

        #
        mean_line_edit = QtWidgets.QLineEdit()

        mean_line_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        self.mean_line_edit = mean_line_edit

        #
        median_line_edit = QtWidgets.QLineEdit()

        median_line_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        self.median_line_edit = median_line_edit

        #
        observations_line_edit = QtWidgets.QLineEdit()

        observations_line_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        self.observations_line_edit = observations_line_edit

        #
        layout = QtWidgets.QVBoxLayout()

        layout.setSpacing(2)

        layout.addWidget(QtWidgets.QLabel("Minimum"))
        layout.addWidget(minimum_line_edit)
        layout.addSpacing(10)
        layout.addWidget(QtWidgets.QLabel("Maximum"))
        layout.addWidget(maximum_line_edit)
        layout.addSpacing(10)
        layout.addWidget(QtWidgets.QLabel("Mean"))
        layout.addWidget(mean_line_edit)
        layout.addSpacing(10)
        layout.addWidget(QtWidgets.QLabel("Median"))
        layout.addWidget(median_line_edit)
        layout.addSpacing(10)
        layout.addWidget(QtWidgets.QLabel("Observations"))
        layout.addWidget(observations_line_edit)
        layout.addSpacing(10)

        self.setLayout(layout)

    def process_data(self, data: np.ndarray) -> None:
        if data.size == 0:
            self.minimum_line_edit.setText("0")
            self.maximum_line_edit.setText("0")
            self.mean_line_edit.setText("0")
            self.median_line_edit.setText("0")
            self.observations_line_edit.setText("0")
            return

        self.minimum_line_edit.setText(f"{np.min(data):.3f}")
        self.maximum_line_edit.setText(f"{np.max(data):.3f}")
        self.mean_line_edit.setText(f"{np.mean(data):.3f}")
        self.median_line_edit.setText(f"{np.median(data):.3f}")
        self.observations_line_edit.setText(f"{len(data)}")


class CorticalDepthVisualiser(QtWidgets.QWidget):
    canvas: Canvas

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        #
        self._dataframe = None
        self._canvases_count = 0
        self._canvas_index = 0
        self._structure_pairs = []
        self._current_data = None
        self._current_display_data = None

        #
        directories_combo_box = ProjectDirectoriesComboBox()

        directories_combo_box.currentTextChanged.connect(
            self._populate_slices_combo_box
        )
        directories_combo_box.currentTextChanged.connect(self._invalidate_current_data)

        self.directories_combo_box = directories_combo_box

        #
        include_all_directories_check_box = QtWidgets.QCheckBox(
            "Include all directories"
        )

        self._include_all_directories = False

        include_all_directories_check_box.checkStateChanged.connect(
            self._set_include_all_directories
        )

        self.include_all_directories_check_box = include_all_directories_check_box

        #
        slice_names_combo_box = SliceNamesComboBox()

        slice_names_combo_box.currentTextChanged.connect(self._invalidate_current_data)

        self.slice_names_combo_box = slice_names_combo_box

        #
        include_all_slices_checkbox = QtWidgets.QCheckBox("Include all slices")

        self._include_all_slices = False

        include_all_slices_checkbox.checkStateChanged.connect(
            self._set_include_all_slices
        )

        self.include_all_slices_checkbox = include_all_slices_checkbox

        #
        canvas = Canvas()

        self.canvas = canvas

        #
        previous_button = QtWidgets.QPushButton("Previous")

        previous_button.clicked.connect(self._decrement_index)
        previous_button.setEnabled(False)

        self.previous_button = previous_button

        #
        next_button = QtWidgets.QPushButton("Next")

        next_button.clicked.connect(self._increment_index)
        next_button.setEnabled(False)

        self.next_button = next_button

        #
        overlapping_check_box = QtWidgets.QCheckBox("Include overlapping points")

        self._include_overlapping = False

        overlapping_check_box.checkStateChanged.connect(self._set_include_overlapping)

        self.overlapping_check_box = overlapping_check_box

        #
        baseline_statistics_widget = StatisticWidget()

        self.baseline_statistics_widget = baseline_statistics_widget

        #
        structure_statistics_widget = StatisticWidget()

        self.structure_statistics_widget = structure_statistics_widget

        #
        layout = QtWidgets.QGridLayout()

        layout.addWidget(directories_combo_box, 0, 0, 1, 2)
        layout.addWidget(include_all_directories_check_box, 1, 0, 1, 2)
        layout.addWidget(slice_names_combo_box, 0, 2, 1, 2)
        layout.addWidget(include_all_slices_checkbox, 1, 2, 1, 2)
        layout.addWidget(canvas, 2, 1, 1, 2)
        layout.addWidget(overlapping_check_box, 3, 1, 1, 2)
        layout.addWidget(previous_button, 4, 1)
        layout.addWidget(next_button, 4, 2)
        layout.addWidget(
            baseline_statistics_widget,
            2,
            0,
            2,
            1,
            alignment=QtCore.Qt.AlignmentFlag.AlignVCenter,
        )
        layout.addWidget(
            structure_statistics_widget,
            2,
            3,
            2,
            1,
            alignment=QtCore.Qt.AlignmentFlag.AlignVCenter,
        )

        self.setLayout(layout)

        #
        self._update_canvas()

    def parse_results(self, data: list[QuantificationResults]) -> None:
        self._dataframe = self.parse_results_to_dataframe(data)

        self._update_combo_boxes()
        self._update_canvas()

    def _update_canvas(self) -> None:
        if self._dataframe is None:
            return

        self.canvas.axes.cla()

        if self._current_data is None:
            filtered_dataframe = self._dataframe
            if not self._include_all_directories:
                if self._include_all_slices:
                    filtered_dataframe = filtered_dataframe[
                        filtered_dataframe.original_directory
                        == self.directories_combo_box.currentText()
                    ]
                else:
                    filtered_dataframe = filtered_dataframe[
                        (
                            filtered_dataframe.original_directory
                            == self.directories_combo_box.currentText()
                        )
                        & (
                            filtered_dataframe.slice_name
                            == self.slice_names_combo_box.currentText()
                        )
                    ]

            if not self._include_overlapping:
                filtered_dataframe = filtered_dataframe[
                    filtered_dataframe.baseline_data != 0
                ]

            self._canvases_count = 0
            self._structure_pairs = []
            for cortex_structure in filtered_dataframe.cortex_structure.unique():
                cortical_structures = filtered_dataframe.loc[
                    filtered_dataframe.cortex_structure == cortex_structure,
                    "cortical_structure",
                ].unique()
                self._canvases_count += len(cortical_structures)

                for cortical_structure in cortical_structures:
                    self._structure_pairs.append((cortex_structure, cortical_structure))

            if self._canvas_index > len(self._structure_pairs):
                self._canvas_index = 0

            self._current_data = filtered_dataframe

        try:
            cortex_structure, cortical_structure = self._structure_pairs[
                self._canvas_index
            ]
        except IndexError:
            cortex_structure = ""
            cortical_structure = ""
        if self._current_display_data is None:
            intermediary_data = self._current_data[
                self._current_data.cortex_structure == cortex_structure
            ]
            self._current_display_data = intermediary_data[
                intermediary_data.cortical_structure == cortical_structure
            ]

        self.canvas.axes.set_title(
            f"Cortical depth of {cortical_structure} relative to {cortex_structure}"
        )
        self.canvas.axes.boxplot(
            self._current_display_data.loc[:, ["baseline_data", "registered_data"]]
        )
        self.canvas.axes.set_xticks([1, 2], ["Baseline", "Registered"])

        self.baseline_statistics_widget.process_data(
            self._current_display_data.baseline_data
        )
        self.structure_statistics_widget.process_data(
            self._current_display_data.registered_data
        )

        self.canvas.axes.set_ylabel("Cortical depth (μm)")
        self.canvas.draw()

        self._update_canvas_buttons_states()

    def _update_combo_boxes(self) -> None:
        if self._dataframe is None:
            return

        self._populate_directories_combo_box()

    def _populate_directories_combo_box(self) -> None:
        if self._dataframe is None:
            return

        self.directories_combo_box.blockSignals(True)

        self.directories_combo_box.clear()
        self.directories_combo_box.addItems(self._dataframe.original_directory.unique())

        self.directories_combo_box.blockSignals(False)

        self._populate_slices_combo_box()

        self._invalidate_current_data()

    def _populate_slices_combo_box(self) -> None:
        if self._dataframe is None:
            return

        self.slice_names_combo_box.blockSignals(True)

        self.slice_names_combo_box.clear()

        self.slice_names_combo_box.addItems(
            self._dataframe.loc[
                self._dataframe.original_directory
                == self.directories_combo_box.currentText(),
                "slice_name",
            ].unique()
        )

        self.slice_names_combo_box.blockSignals(False)

    def _set_include_all_directories(self, check_state: QtCore.Qt.CheckState) -> None:
        if check_state == QtCore.Qt.CheckState.PartiallyChecked:
            raise ValueError("Cannot understand partial toggle.")

        self._include_all_directories = check_state == QtCore.Qt.CheckState.Checked

        # Disable other relevant widgets when including all directories
        self.directories_combo_box.setEnabled(not self._include_all_directories)
        self.slice_names_combo_box.setEnabled(not self._include_all_directories)
        self.include_all_slices_checkbox.setEnabled(not self._include_all_directories)

        self._invalidate_current_data()

    def _set_include_all_slices(self, check_state: QtCore.Qt.CheckState) -> None:
        if check_state == QtCore.Qt.CheckState.PartiallyChecked:
            raise ValueError("Cannot understand partial toggle.")

        self._include_all_slices = check_state == QtCore.Qt.CheckState.Checked
        self._invalidate_current_data()

    def _set_include_overlapping(self, check_state: QtCore.Qt.CheckState) -> None:
        if check_state == QtCore.Qt.CheckState.PartiallyChecked:
            raise ValueError("Cannot understand partial toggle.")

        self._include_overlapping = check_state == QtCore.Qt.CheckState.Checked
        self._invalidate_current_data()

    def _decrement_index(self) -> None:
        if self._canvas_index < 1:
            return

        self._canvas_index -= 1
        self._update_canvas_buttons_states()
        self._invalidate_current_display_data()

        self._update_canvas()

    def _increment_index(self) -> None:
        if self._canvas_index >= len(self._structure_pairs) - 1:
            return

        self._canvas_index += 1
        self._update_canvas_buttons_states()
        self._invalidate_current_display_data()

        self._update_canvas()

    def _update_canvas_buttons_states(self) -> None:
        self.previous_button.setEnabled(self._canvas_index > 0)
        self.next_button.setEnabled(self._canvas_index < len(self._structure_pairs) - 1)

    def _invalidate_current_data(self) -> None:
        self._current_data = None
        self._invalidate_current_display_data()

    def _invalidate_current_display_data(self) -> None:
        self._current_display_data = None

        self._update_canvas()

    @staticmethod
    def parse_results_to_dataframe(
        results: list[QuantificationResults],
    ) -> pd.DataFrame:
        dataframe_rows = []
        for result in results:
            alignment_directory = result.settings.alignment_directory
            original_directory = result.settings.original_directory
            quantification_measure = result.settings.quantification_measure
            fast_rescale = result.settings.fast_rescale
            fast_transform = result.settings.fast_transform
            timestamp = result.timestamp
            hash_ = result.hash

            cortex_structure = result.settings.measure_settings.cortex_structure

            for slice_name, slice_result in result.data.items():
                for cortical_structure, values in slice_result.items():
                    for i in range(len(values[0])):
                        dataframe_rows.append(
                            [
                                str(alignment_directory),
                                str(original_directory),
                                quantification_measure,
                                fast_rescale,
                                fast_transform,
                                timestamp,
                                hash_,
                                slice_name,
                                cortex_structure,
                                cortical_structure,
                                values[0][i],
                                values[1][i],
                            ],
                        )

        return pd.DataFrame(
            data=dataframe_rows,
            columns=[
                "alignment_directory",
                "original_directory",
                "quantification_measure",
                "fast_rescale",
                "fast_transform",
                "timestamp",
                "hash",
                "slice_name",
                "cortex_structure",
                "cortical_structure",
                "baseline_data",
                "registered_data",
            ],
        )
