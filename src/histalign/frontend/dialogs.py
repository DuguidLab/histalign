# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import os
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.models import Orientation, ProjectSettings, Resolution
from histalign.frontend.common_widgets import (
    file_picker_overwrite_validator,
    FilePickerWidget,
)
from histalign.io import is_empty_directory


class AtlasProgressDialog(QtWidgets.QProgressDialog):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent, flags=QtCore.Qt.CustomizeWindowHint | QtCore.Qt.WindowTitleHint
        )

        self.setWindowTitle(" ")
        self.setLabelText("Downloading atlas")

        self.setMinimum(0)
        self.setMaximum(0)
        self.setCancelButton(None)  # type: ignore[arg-type]

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        # Ugly but not all platforms support having a frame and no close button
        event.ignore()
        return

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Escape:
            # Disable closing dialog with Escape
            event.accept()
            return

        super().keyPressEvent(event)


class InvalidProjectFileDialog(QtWidgets.QMessageBox):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Invalid project file")
        self.setText("The selected project file is not valid.")
        self.setIcon(QtWidgets.QMessageBox.Critical)


class NewProjectDialog(QtWidgets.QDialog):
    orientation_widget: QtWidgets.QComboBox
    resolution_widget: QtWidgets.QComboBox
    project_path_label: QtWidgets.QLabel
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

        resolution_label = QtWidgets.QLabel("Atlas resolution")
        self.resolution_label = resolution_label

        resolution_widget = QtWidgets.QComboBox()
        resolution_widget.setFixedSize(60, 22)
        resolution_widget.setEditable(True)
        resolution_widget.lineEdit().setReadOnly(True)
        resolution_widget.lineEdit().setAlignment(QtCore.Qt.AlignRight)
        resolution_widget.lineEdit().selectionChanged.connect(
            lambda: resolution_widget.lineEdit().deselect()
        )
        resolution_widget.lineEdit().textChanged.connect(self.validate_resolution)
        resolution_widget.addItem("100")
        resolution_widget.addItem("50")
        resolution_widget.addItem("25")
        resolution_widget.addItem("10")

        resolution_layout.addWidget(resolution_widget)
        self.resolution_widget = resolution_widget

        directory_picker = FilePickerWidget(
            "Project directory",
            directory_mode=True,
            validators=[file_picker_overwrite_validator, self.path_validator],
        )
        directory_picker.layout().setContentsMargins(0, 0, 0, 0)
        self.directory_picker = directory_picker

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )

        submit_button = button_box.button(QtWidgets.QDialogButtonBox.Ok)
        submit_button.clicked.connect(self.submit)
        submit_button.setEnabled(False)
        self.submit_button = submit_button

        button_box.button(QtWidgets.QDialogButtonBox.Cancel).clicked.connect(
            self.reject
        )

        layout.addRow("Orientation", orientation_layout)
        layout.addRow(resolution_label, resolution_layout)
        layout.addRow(directory_picker)
        layout.addRow(button_box)

        self.setLayout(layout)
        self.setFixedSize(400, layout.sizeHint().height())

    def path_validator(self, path: str, widget: FilePickerWidget) -> str:
        path_ = Path(path) if path else Path("/__dummy__path__")
        self.submit_button.setEnabled(path_.exists() and path_.is_dir())

        return path

    def show_confirm_overwrite_dialog(self) -> bool:
        dialog = ConfirmOverwriteDialog(self)

        return dialog.exec() == QtWidgets.QMessageBox.StandardButton.Ok

    @QtCore.Slot()
    def submit(self) -> None:
        if (
            not is_empty_directory(Path(self.directory_picker.text))
            and not self.show_confirm_overwrite_dialog()
        ):
            return

        self.submitted.emit(
            ProjectSettings(
                project_path=Path(self.directory_picker.text),
                orientation=Orientation(self.orientation_widget.currentText().lower()),
                resolution=Resolution(int(self.resolution_widget.currentText())),
            )
        )
        self.accept()

    @QtCore.Slot()
    def validate_resolution(self, resolution: str) -> None:
        if resolution == "10":
            text = r"Atlas resolution (very high RAM budget)"
            colour = QtCore.Qt.GlobalColor.red
        elif resolution == "25":
            text = r"Atlas resolution (medium RAM budget)"
            colour = "#FF4F00"  # Orange
        elif resolution == "50":
            text = r"Atlas resolution (low RAM budget)"
            colour = QtWidgets.QApplication.palette().windowText().color()
        elif resolution == "100":
            text = r"Atlas resolution (very low RAM budget)"
            colour = QtWidgets.QApplication.palette().windowText().color()
        else:
            text = "Atlas resolution"
            colour = QtWidgets.QApplication.palette().windowText().color()

        self.resolution_label.setText(text)
        pallete = self.resolution_label.palette()
        pallete.setColor(QtGui.QPalette.ColorRole.WindowText, colour)
        self.resolution_label.setPalette(pallete)


class OpenImagesFolderDialog(QtWidgets.QFileDialog):
    submitted: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent, "Select an image directory", os.getcwd())

        self.setFileMode(QtWidgets.QFileDialog.FileMode.Directory)
        self.setOption(QtWidgets.QFileDialog.Option.DontUseNativeDialog, True)

        self.accepted.connect(lambda: self.submitted.emit(self.selectedFiles()[0]))


class OpenProjectDialog(QtWidgets.QFileDialog):
    submitted: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent, "Select project file", os.getcwd(), "Project (project.json)"
        )

        self.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFile)
        self.setOption(QtWidgets.QFileDialog.Option.DontUseNativeDialog, True)

        self.accepted.connect(lambda: self.submitted.emit(self.selectedFiles()[0]))

    def exec(self) -> None:
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


class ConfirmOverwriteDialog(QtWidgets.QMessageBox):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Overwrite directory?")
        self.setText(
            "Are you sure you want to delete all the contents of this directory?"
        )
        self.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Ok
            | QtWidgets.QMessageBox.StandardButton.Cancel
        )
        self.setButtonText(QtWidgets.QMessageBox.StandardButton.Ok, "Confirm")

        self.setIcon(QtWidgets.QMessageBox.Icon.Warning)


class ConfirmDeleteDialog(QtWidgets.QMessageBox):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Delete file?")
        self.setText(
            "Are you sure you want to delete this file? This action is not reversible."
        )
        self.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Ok
            | QtWidgets.QMessageBox.StandardButton.Cancel
        )
        self.setButtonText(QtWidgets.QMessageBox.StandardButton.Ok, "Confirm")

        self.setIcon(QtWidgets.QMessageBox.Icon.Warning)
