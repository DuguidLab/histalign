# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import os
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets

from histalign.backend.models import ProjectSettings


class AtlasChangeDialog(QtWidgets.QDialog):
    label: QtWidgets.QLabel
    combo_box: QtWidgets.QComboBox
    button_box: QtWidgets.QDialogButtonBox

    submitted: QtCore.Signal = QtCore.Signal(int)

    def __init__(
        self, current_resolution: int, parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)

        #
        label = QtWidgets.QLabel("Atlas resolution")

        self.label = label

        #
        combo_box = QtWidgets.QComboBox()
        combo_box.setFixedSize(60, 22)
        combo_box.setEditable(True)
        combo_box.lineEdit().setReadOnly(True)
        combo_box.lineEdit().setAlignment(QtCore.Qt.AlignRight)
        combo_box.lineEdit().selectionChanged.connect(
            lambda: combo_box.lineEdit().deselect()
        )
        resolutions = [10, 25, 50, 100]
        resolutions.remove(current_resolution)
        for resolution in resolutions:
            combo_box.addItem(str(resolution))

        self.combo_box = combo_box

        #
        resolution_layout = QtWidgets.QHBoxLayout()
        resolution_layout.addWidget(label, alignment=QtCore.Qt.AlignLeft)
        resolution_layout.addWidget(combo_box, alignment=QtCore.Qt.AlignRight)

        #
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )

        button_box.button(QtWidgets.QDialogButtonBox.Ok).clicked.connect(self.submit)
        button_box.button(QtWidgets.QDialogButtonBox.Cancel).clicked.connect(
            self.reject
        )

        self.button_box = button_box

        #
        layout = QtWidgets.QFormLayout()
        layout.setSpacing(20)

        layout.addRow(resolution_layout)
        layout.addRow(button_box)

        self.setLayout(layout)
        self.setFixedSize(200, layout.sizeHint().height())

    @QtCore.Slot()
    def submit(self) -> None:
        self.submitted.emit(int(self.combo_box.currentText()))
        self.accept()


class AtlasProgressDialog(QtWidgets.QProgressDialog):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent, flags=QtCore.Qt.CustomizeWindowHint | QtCore.Qt.WindowTitleHint
        )

        self.setWindowTitle(" ")
        self.setLabelText("Downloading atlas")

        self.setMinimum(0)
        self.setMaximum(0)
        self.setCancelButton(None)


class InvalidProjectFileDialog(QtWidgets.QMessageBox):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Invalid project file")
        self.setText("The selected project file is not valid.")
        self.setIcon(QtWidgets.QMessageBox.Critical)


class CreateProjectDialog(QtWidgets.QDialog):
    orientation_widget: QtWidgets.QComboBox
    resolution_widget: QtWidgets.QComboBox
    project_path_widget: QtWidgets.QLineEdit
    submit_button: QtWidgets.QPushButton

    submitted: QtCore.Signal = QtCore.Signal(ProjectSettings)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Project creation")

        layout = QtWidgets.QFormLayout()
        layout.setSpacing(20)

        orientation_layout = QtWidgets.QHBoxLayout()
        orientation_layout.setAlignment(QtCore.Qt.AlignRight)
        orientation_layout.setSpacing(20)

        orientation_widget = QtWidgets.QComboBox()
        orientation_widget.setFixedSize(95, 22)
        orientation_widget.setEditable(True)
        orientation_widget.lineEdit().setReadOnly(True)
        orientation_widget.lineEdit().setAlignment(QtCore.Qt.AlignRight)
        orientation_widget.lineEdit().selectionChanged.connect(
            lambda: orientation_widget.lineEdit().deselect()
        )
        orientation_widget.addItem("Coronal")
        orientation_widget.addItem("Horizontal")
        orientation_widget.addItem("Sagittal")

        orientation_layout.addWidget(orientation_widget)
        self.orientation_widget = orientation_widget

        resolution_layout = QtWidgets.QHBoxLayout()
        resolution_layout.setAlignment(QtCore.Qt.AlignRight)
        resolution_layout.setSpacing(20)

        resolution_widget = QtWidgets.QComboBox()
        resolution_widget.setFixedSize(60, 22)
        resolution_widget.setEditable(True)
        resolution_widget.lineEdit().setReadOnly(True)
        resolution_widget.lineEdit().setAlignment(QtCore.Qt.AlignRight)
        resolution_widget.lineEdit().selectionChanged.connect(
            lambda: resolution_widget.lineEdit().deselect()
        )
        resolution_widget.addItem("10")
        resolution_widget.addItem("25")
        resolution_widget.addItem("50")
        resolution_widget.addItem("100")

        resolution_layout.addWidget(resolution_widget)
        self.resolution_widget = resolution_widget

        project_picker_layout = QtWidgets.QGridLayout()
        project_picker_layout.setContentsMargins(0, 0, 0, 0)
        project_picker_layout.setHorizontalSpacing(5)
        project_picker_layout.setVerticalSpacing(10)

        project_picker_label = QtWidgets.QLabel("Project directory (must be empty)")

        project_picker_line_edit = QtWidgets.QLineEdit()
        project_picker_line_edit.textChanged.connect(self.validate_project_path)
        self.project_path_widget = project_picker_line_edit

        project_picker_button = QtWidgets.QPushButton("...")
        project_picker_button.setFixedSize(25, 22)
        project_picker_button.clicked.connect(self.show_directory_picker)

        project_picker_layout.addWidget(
            project_picker_label, 0, 0, 1, 2, alignment=QtCore.Qt.AlignLeft
        )
        project_picker_layout.addWidget(project_picker_line_edit, 1, 0)
        project_picker_layout.addWidget(project_picker_button, 1, 1)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )

        submit_button = button_box.button(QtWidgets.QDialogButtonBox.Ok)
        submit_button.setEnabled(False)
        submit_button.clicked.connect(self.submit)
        self.submit_button = submit_button

        button_box.button(QtWidgets.QDialogButtonBox.Cancel).clicked.connect(
            self.reject
        )

        layout.addRow("Orientation", orientation_layout)
        layout.addRow("Atlas resolution", resolution_layout)
        layout.addRow(project_picker_layout)
        layout.addRow(button_box)

        self.setLayout(layout)
        self.setFixedSize(350, layout.sizeHint().height())

    def show_directory_picker(self) -> None:
        choice = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            caption="Select an empty project directory",
            options=QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )

        if choice != "":
            self.project_path_widget.setText(choice)

    @QtCore.Slot()
    def validate_project_path(self, path: str) -> None:
        path = Path(path)

        valid = False
        if path.is_dir():
            try:
                next(path.iterdir())
            except FileNotFoundError:
                pass
            except StopIteration:
                valid = True

        self.submit_button.setEnabled(valid)

    @QtCore.Slot()
    def submit(self) -> None:
        self.submitted.emit(
            ProjectSettings(
                project_path=self.project_path_widget.text(),
                orientation=self.orientation_widget.currentText().lower(),
                resolution=self.resolution_widget.currentText(),
            )
        )
        self.accept()


class OpenProjectDialog(QtWidgets.QWidget):
    submitted: QtCore.Signal = QtCore.Signal(str)

    def open(self) -> None:
        project_file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select a project file",
            os.getcwd(),
            "Project (project.json)",
            options=QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )

        if project_file != "":
            self.submitted.emit(project_file)

        self.close()


class SaveProjectConfirmationDialog(QtWidgets.QMessageBox):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Save project")
        self.setText("Do you want to save your project?")
        self.setStandardButtons(
            QtWidgets.QMessageBox.Save
            | QtWidgets.QMessageBox.Discard
            | QtWidgets.QMessageBox.Cancel
        )
        self.setIcon(QtWidgets.QMessageBox.Question)
