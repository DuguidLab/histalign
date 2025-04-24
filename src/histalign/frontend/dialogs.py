# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import os
from pathlib import Path
from typing import Any, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.models import (
    Orientation,
    ProjectSettings,
    Resolution,
    VolumeExportSettings,
)
from histalign.backend.workspace import alignment_directory_has_volumes, Workspace
from histalign.frontend.common_widgets import (
    file_picker_overwrite_validator,
    FilePickerWidget,
    FileSelectorWidget,
)
from histalign.io import is_empty_directory, list_alignment_directories


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


class ExportVolumeDialog(QtWidgets.QDialog):
    submitted: QtCore.Signal = QtCore.Signal(VolumeExportSettings)

    def __init__(
        self, project_root: Path, parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)

        choices = list_alignment_directories(project_root)
        choices = [
            path
            for path in choices
            if alignment_directory_has_volumes(
                Path(project_root / Workspace.generate_directory_hash(path))
            )
        ]

        image_directory_widget = FileSelectorWidget("Image directory", choices=choices)
        image_directory_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.image_directory_widget = image_directory_widget

        alignment_check_box = QtWidgets.QCheckBox()
        alignment_check_box.stateChanged.connect(
            lambda: self.export_button_state_validator(export_directory_widget.text)
        )
        self.alignment_check_box = alignment_check_box

        interpolation_check_box = QtWidgets.QCheckBox()
        interpolation_check_box.stateChanged.connect(
            lambda: self.export_button_state_validator(export_directory_widget.text)
        )
        self.interpolation_check_box = interpolation_check_box

        export_directory_widget = FilePickerWidget(
            "Export directory",
            directory_mode=True,
            save_mode=True,
            validators=[self.export_button_state_validator],
        )
        export_directory_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.export_directory_widget = export_directory_widget

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).clicked.connect(
            self.submit
        )
        button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(
            "Export"
        )
        button_box.button(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        ).clicked.connect(self.reject)
        self.button_box = button_box

        layout = QtWidgets.QGridLayout()
        layout.addWidget(image_directory_widget, 0, 0, 1, -1)
        layout.addWidget(QtWidgets.QLabel("Alignment volume"), 1, 0, 1, 2)
        layout.addWidget(
            alignment_check_box, 1, 2, alignment=QtCore.Qt.AlignmentFlag.AlignRight
        )
        layout.addWidget(QtWidgets.QLabel("Interpolated volume"), 2, 0, 1, 2)
        layout.addWidget(
            interpolation_check_box, 2, 2, alignment=QtCore.Qt.AlignmentFlag.AlignRight
        )
        layout.addWidget(export_directory_widget, 3, 0, 1, -1)
        layout.addItem(QtWidgets.QSpacerItem(0, 10), 4, 0)
        layout.addWidget(
            button_box, 5, 0, 1, -1, alignment=QtCore.Qt.AlignmentFlag.AlignRight
        )
        layout.setSpacing(10)
        self.setLayout(layout)

        self.setWindowTitle("Export volume")
        self.setFixedSize(400, layout.sizeHint().height())

        self.export_button_state_validator("")  # Trigger once to set tool tips

    @property
    def alignment_directory(self) -> str:
        return self.image_directory_widget.text

    @property
    def include_aligned(self) -> bool:
        return self.alignment_check_box.isChecked()

    @property
    def include_interpolated(self) -> bool:
        return self.interpolation_check_box.isChecked()

    @property
    def export_directory(self) -> str:
        return self.export_directory_widget.text

    def export_button_state_validator(self, path: str, _: Any = None) -> str:
        ok_button = self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        path_ = Path(path) if path else Path("/__dummy__path__")

        if not self.alignment_directory:
            ok_button.setEnabled(False)
            ok_button.setToolTip("Invalid alignment directory.")
        elif self.include_aligned + self.include_interpolated < 1:
            ok_button.setEnabled(False)
            ok_button.setToolTip("Choose at least one volume to export.")
        elif not (path_.exists() and path_.is_dir()):
            ok_button.setEnabled(False)
            ok_button.setToolTip("Invalid export directory.")
        else:
            ok_button.setEnabled(True)
            ok_button.setToolTip("")

        return path

    @QtCore.Slot()
    def submit(self) -> None:
        self.submitted.emit(
            VolumeExportSettings(
                image_directory=self.alignment_directory,
                include_aligned=self.include_aligned,
                include_interpolated=self.include_interpolated,
                export_directory=self.export_directory,
            )
        )
        self.accept()


class InfiniteProgressDialog(QtWidgets.QProgressDialog):
    def __init__(self, text: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setMinimum(0)
        self.setMaximum(0)
        self.setCancelButton(None)  # type: ignore[arg-type]

        self.setWindowTitle("")
        self.setLabelText(text)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Escape:
            # Disable closing dialog with Escape
            event.accept()
            return

        super().keyPressEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        # Ugly but not all platforms support having a frame and no close button
        event.ignore()
        return
