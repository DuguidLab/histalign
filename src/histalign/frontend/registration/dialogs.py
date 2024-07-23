# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets


class AtlasChangeDialog(QtWidgets.QDialog):
    submitted: QtCore.Signal = QtCore.Signal(int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        layout = QtWidgets.QFormLayout()
        layout.setSpacing(20)

        resolution_layout = QtWidgets.QHBoxLayout()

        label = QtWidgets.QLabel("Atlas resolution")

        combo_box = QtWidgets.QComboBox()
        combo_box.setFixedSize(60, 22)
        combo_box.setEditable(True)
        combo_box.lineEdit().setReadOnly(True)
        combo_box.lineEdit().setAlignment(QtCore.Qt.AlignRight)
        combo_box.lineEdit().selectionChanged.connect(
            lambda: combo_box.lineEdit().deselect()
        )
        combo_box.addItem("10")
        combo_box.addItem("25")
        combo_box.addItem("50")
        combo_box.addItem("100")

        resolution_layout.addWidget(label, alignment=QtCore.Qt.AlignLeft)
        resolution_layout.addWidget(combo_box, alignment=QtCore.Qt.AlignRight)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )

        button_box.button(QtWidgets.QDialogButtonBox.Ok).clicked.connect(self.submit)
        button_box.button(QtWidgets.QDialogButtonBox.Cancel).clicked.connect(self.close)

        layout.addRow(resolution_layout)
        layout.addRow(button_box)

        self.setLayout(layout)
        self.setFixedSize(200, layout.sizeHint().height())

    @QtCore.Slot()
    def submit(self) -> None:
        self.close()
        self.submitted.emit(int(self.findChild(QtWidgets.QComboBox).currentText()))


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
        self.setIcon(QtWidgets.QMessageBox.Error)


class NoActiveProjectDialog(QtWidgets.QMessageBox):
    def __init__(
        self, action: Optional[str] = None, parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("No active project")

        if action is None:
            self.setText("You must have a project open to do this.")
        else:
            self.setText(f"You must have a project open to {action}.")

        self.setIcon(QtWidgets.QMessageBox.Warning)


class ProjectCreateDialog(QtWidgets.QDialog):
    resolution_widget: QtWidgets.QComboBox
    project_path_widget: QtWidgets.QLineEdit
    submit_button: QtWidgets.QPushButton

    submitted: QtCore.Signal = QtCore.Signal(dict)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        layout = QtWidgets.QFormLayout()
        layout.setSpacing(20)

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

        button_box.button(QtWidgets.QDialogButtonBox.Cancel).clicked.connect(self.close)

        layout.addRow("Atlas resolution", resolution_layout)
        layout.addRow(project_picker_layout)
        layout.addRow(button_box)

        self.setLayout(layout)
        self.setFixedSize(350, layout.sizeHint().height())

    def show_directory_picker(self) -> None:
        choice = QtWidgets.QFileDialog.getExistingDirectory(
            caption="Select an empty project directory",
            options=QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )

        if choice != "":
            self.project_path_widget.setText(choice)

    @QtCore.Slot()
    def validate_project_path(self, path: str) -> None:
        path = Path(path)

        valid = False
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
            {
                "project_directory_path": self.project_path_widget.text(),
                "atlas_resolution": int(self.resolution_widget.currentText()),
            }
        )
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
