# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import hashlib
import os
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets

from histalign.backend.workspace.HistologySlice import HistologySlice
from histalign.frontend.qa.HistogramViewerWidget import HistogramViewerWidget
from histalign.frontend.qa.MainMenuBar import MainMenuBar
from histalign.frontend.qa.QAViewerWidget import QAViewerWidget
from histalign.frontend.qa.SliceNamesComboBox import SliceNamesComboBox
from histalign.frontend.qa.StructureSelectorFrame import StructureSelectorFrame


class QAMainWindow(QtWidgets.QMainWindow):
    current_directory: str

    slice_names_combo_box: QtWidgets.QComboBox
    qa_viewer: QAViewerWidget

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        menu_bar = MainMenuBar()
        menu_bar.open_results_directory_requested.connect(
            self.show_open_results_directory_dialog
        )
        self.setMenuBar(menu_bar)

        self.slice_names_combo_box = SliceNamesComboBox()
        self.slice_names_combo_box.file_picked.connect(self.update_histology)

        selector_frame = StructureSelectorFrame()

        self.qa_viewer = QAViewerWidget()
        selector_frame.structure_added.connect(self.qa_viewer.add_contour)
        selector_frame.structure_removed.connect(self.qa_viewer.remove_contour)

        histogram_viewer = HistogramViewerWidget(self.qa_viewer)
        self.qa_viewer.contour_mask_generated.connect(histogram_viewer.add_histogram)
        selector_frame.structure_removed.connect(histogram_viewer.remove_histogram)

        layout = QtWidgets.QGridLayout()

        layout.addWidget(self.slice_names_combo_box, 0, 0)
        layout.addWidget(selector_frame, 0, 1, 1, 2)
        layout.addWidget(self.qa_viewer, 1, 0, 1, 2)
        layout.addWidget(histogram_viewer, 1, 2, 1, 1)

        layout.setColumnStretch(1, 5)
        layout.setColumnStretch(2, 3)
        layout.setColumnMinimumWidth(1, 500)
        layout.setColumnMinimumWidth(2, 300)
        layout.setRowMinimumHeight(1, 500)

        layout.setContentsMargins(0, 0, 0, 0)

        central_widget = QtWidgets.QWidget()
        central_widget.setLayout(layout)
        central_widget.setMinimumSize(layout.minimumSize())
        self.setCentralWidget(central_widget)

        self.setWindowTitle("Histalign - QA")

    def open_results_directory(self, result_metadata_file_path: str) -> None:
        self.current_directory = str(Path(result_metadata_file_path).parent)
        self.qa_viewer.clear()
        self.slice_names_combo_box.parse_results(result_metadata_file_path)

    @QtCore.Slot()
    def update_histology(self, file_path: str) -> None:
        if file_path == "":
            self.qa_viewer.clear()
            return

        file_hash = HistologySlice.generate_file_name_hash(file_path)
        result_path = Path(self.current_directory) / f"{file_hash}.json"
        result_path = str(result_path) if result_path.exists() else None

        self.qa_viewer.load_histology(file_path, result_path)

    @QtCore.Slot()
    def show_open_results_directory_dialog(self) -> None:
        results_metadata_file_path = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select a result metadata file",
            os.getcwd(),
            "Result metadata (metadata.json)",
            options=QtWidgets.QFileDialog.DontUseNativeDialog,
        )[0]

        if results_metadata_file_path != "":
            self.open_results_directory(results_metadata_file_path)
