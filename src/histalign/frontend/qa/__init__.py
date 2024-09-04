# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import json
import logging
from pathlib import Path
import re
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.workspace import HistologySlice, Workspace
from histalign.frontend.common_widgets import (
    ProjectDirectoriesComboBox,
    SelectedStructuresWidget,
)
from histalign.frontend.dialogs import OpenProjectDialog
from histalign.frontend.qa.measures import HistogramViewerWidget
from histalign.frontend.qa.viewer import QAViewerWidget

HASHED_DIRECTORY_NAME_PATTERN = re.compile(r"[0-9a-f]{10}")


class MainMenuBar(QtWidgets.QMenuBar):
    open_project_requested: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        file_menu = self.addMenu("&File")

        open_project_action = QtGui.QAction("&Open project", self)
        open_project_action.triggered.connect(self.open_project_requested.emit)

        file_menu.addAction(open_project_action)


class SliceNamesComboBox(QtWidgets.QComboBox):
    file_picked: QtCore.Signal = QtCore.Signal(str)

    name_to_path_map: dict[str, str]

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.name_to_path_map = {}

        self.currentTextChanged.connect(self.notify_change)

        self.setMinimumWidth(300)
        # Limits number of visible items to 10
        self.setStyleSheet("QComboBox { combobox-popup: 0; }")

    def parse_results(self, metadata_path: str) -> None:
        with open(metadata_path) as handle:
            paths = json.load(handle).get("slice_paths")

        if paths is None:
            return

        self.clear()

        metadata_root = Path(metadata_path).parent
        self.addItem("")
        for file_path in paths:
            file_name = Path(file_path).stem
            self.name_to_path_map[file_name] = file_path
            self.addItem(file_name)

            if (
                not Path(file_path).exists()
                or not (
                    metadata_root
                    / f"{HistologySlice.generate_file_name_hash(file_path)}.json"
                ).exists()
            ):
                self.model().item(self.findText(file_name)).setEnabled(False)

    def clear(self) -> None:
        super().clear()
        self.name_to_path_map = {"": ""}

    @QtCore.Slot()
    def notify_change(self, file_name) -> None:
        self.file_picked.emit(self.name_to_path_map[file_name])


class QAMainWindow(QtWidgets.QMainWindow):
    project_directory: str
    current_directory: str
    project_loaded: bool = False

    structures_processing: list[str]

    project_directories_combo_box: ProjectDirectoriesComboBox
    slice_names_combo_box: SliceNamesComboBox
    selected_structures_widget: SelectedStructuresWidget
    qa_viewer: QAViewerWidget
    histogram_viewer: HistogramViewerWidget

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)

        self.structures_processing = []
        self.update_status()

        menu_bar = MainMenuBar()
        menu_bar.open_project_requested.connect(self.show_open_project_dialog)
        self.setMenuBar(menu_bar)

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
        selected_structures_widget = SelectedStructuresWidget()

        self.selected_structures_widget = selected_structures_widget

        #
        qa_viewer = QAViewerWidget()
        qa_viewer.contour_processed.connect(self.remove_structure_from_status)

        selected_structures_widget.structure_added.connect(qa_viewer.add_contour)
        selected_structures_widget.structure_removed.connect(qa_viewer.remove_contour)
        selected_structures_widget.structure_added.connect(self.add_structure_to_status)

        self.qa_viewer = qa_viewer

        #
        histogram_viewer = HistogramViewerWidget(qa_viewer)

        qa_viewer.contour_mask_generated.connect(histogram_viewer.add_histogram)
        selected_structures_widget.structure_removed.connect(
            histogram_viewer.remove_histogram
        )

        self.histogram_viewer = histogram_viewer

        #
        layout = QtWidgets.QGridLayout()

        layout.addWidget(project_directories_combo_box, 0, 0, 1, -1)
        layout.addWidget(self.slice_names_combo_box, 1, 0)
        layout.addWidget(selected_structures_widget, 1, 1, 1, 2)
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
    def show_open_project_dialog(self) -> None:
        dialog = OpenProjectDialog(self)
        dialog.submitted.connect(self.open_project)
        dialog.open()

    @QtCore.Slot()
    def open_project(self, project_path: str) -> None:
        self.project_directory = str(Path(project_path).parent)

        self.project_directories_combo_box.parse_project(project_path)

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
    def add_structure_to_status(self, structure_name: str) -> None:
        self.structures_processing.append(structure_name)
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
