# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path
import re
from typing import Optional

from PySide6 import QtCore, QtWidgets

from histalign.backend.workspace import HistologySlice, Workspace
from histalign.frontend.common_widgets import (
    BasicApplicationWindow,
    ProjectDirectoriesComboBox,
    SliceNamesComboBox,
    StructureFinderWidget,
)
from histalign.frontend.qa.measures import HistogramViewerWidget
from histalign.frontend.qa.viewer import QAViewerWidget

HASHED_DIRECTORY_NAME_PATTERN = re.compile(r"[0-9a-f]{10}")


class QAMainWindow(BasicApplicationWindow):
    project_directory: Path
    current_directory: str
    project_loaded: bool = False

    structures_processing: list[str]

    project_directories_combo_box: ProjectDirectoriesComboBox
    slice_names_combo_box: SliceNamesComboBox
    structure_finder_widget: StructureFinderWidget
    qa_viewer: QAViewerWidget
    histogram_viewer: HistogramViewerWidget

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(
            f"{self.__module__}.{self.__class__.__qualname__}"
        )

        self.structures_processing = []
        self.update_status()

        #
        slice_names_combo_box = SliceNamesComboBox()
        slice_names_combo_box.file_picked.connect(self.update_histology)

        self.slice_names_combo_box = slice_names_combo_box

        #
        project_directories_combo_box = ProjectDirectoriesComboBox()
        project_directories_combo_box.currentTextChanged.connect(
            self.update_slice_names_combo_box
        )

        self.project_directories_combo_box = project_directories_combo_box

        #
        structure_finder_widget = StructureFinderWidget()

        self.structure_finder_widget = structure_finder_widget

        #
        qa_viewer = QAViewerWidget()
        qa_viewer.contour_processed.connect(self.remove_structure_from_status)

        model = structure_finder_widget.tree_view.model()
        model.item_checked.connect(qa_viewer.add_contour)
        model.item_checked.connect(self.add_structure_to_status)
        model.item_unchecked.connect(qa_viewer.remove_contour)

        self.qa_viewer = qa_viewer

        #
        histogram_viewer = HistogramViewerWidget(qa_viewer)

        qa_viewer.contour_mask_generated.connect(histogram_viewer.add_histogram)
        model.item_unchecked.connect(histogram_viewer.remove_histogram)

        self.histogram_viewer = histogram_viewer

        #
        layout = QtWidgets.QGridLayout()

        layout.addWidget(project_directories_combo_box, 0, 0, 1, -1)
        layout.addWidget(self.slice_names_combo_box, 1, 0)
        layout.addWidget(structure_finder_widget, 1, 1, 1, 2)
        layout.addWidget(self.qa_viewer, 2, 0, 1, 2)
        layout.addWidget(histogram_viewer, 2, 2, 1, 1)

        layout.setColumnStretch(1, 5)
        layout.setColumnStretch(2, 3)
        layout.setColumnMinimumWidth(1, 500)
        layout.setColumnMinimumWidth(2, 300)
        layout.setRowMinimumHeight(2, 500)

        layout.setContentsMargins(0, 0, 0, 0)

        #
        central_widget = QtWidgets.QWidget()
        central_widget.setLayout(layout)
        central_widget.setMinimumSize(layout.minimumSize())
        self.setCentralWidget(central_widget)

    def update_status(self) -> None:
        if self.structures_processing:
            message = (
                f"Processing {len(self.structures_processing)} "
                f"structure{'s' if len(self.structures_processing) > 1 else ''}..."
            )
        else:
            message = ""

        self.statusBar().showMessage(message)

    @QtCore.Slot()
    def open_project(self, project_file_path: str) -> None:
        self.project_directory = Path(project_file_path).parent

        self.project_directories_combo_box.parse_project(self.project_directory)

        self.project_loaded = True

    @QtCore.Slot()
    def update_slice_names_combo_box(self, directory: str) -> None:
        if not directory:
            return

        self.slice_names_combo_box.parse_results(
            str(
                Path(self.project_directory)
                / Workspace.generate_directory_hash(directory)
                / "metadata.json"
            )
        )

    @QtCore.Slot()
    def update_histology(self, file_path: str) -> None:
        if file_path == "":
            self.qa_viewer.clear()
            return

        directory_hash = Workspace.generate_directory_hash(str(Path(file_path).parent))
        file_hash = HistologySlice.generate_file_name_hash(file_path)
        result_path = (
            Path(self.project_directory) / directory_hash / f"{file_hash}.json"
        )
        result_path = str(result_path) if result_path.exists() else None

        self.qa_viewer.load_histology(file_path, result_path)

    @QtCore.Slot()
    def add_structure_to_status(self, index: QtCore.QModelIndex) -> None:
        self.structures_processing.append(index.internalPointer().name)
        self.update_status()

    @QtCore.Slot()
    def remove_structure_from_status(self, structure_name: str) -> None:
        try:
            self.structures_processing.remove(structure_name)
        except ValueError:
            self.logger.error(
                "Tried to remove non-existent structure from status list."
            )
        self.update_status()
