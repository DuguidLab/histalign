# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierDelrée@protonmail.com>
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets


class ProjectCreateDialog(QtWidgets.QDialog):
    resolution_combo_box: QtWidgets.QComboBox
    project_picker_line_edit: QtWidgets.QLineEdit
    submit_button: QtWidgets.QPushButton

    create_project: QtCore.Signal = QtCore.Signal(dict)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        main_layout = QtWidgets.QFormLayout()
        main_layout.setVerticalSpacing(20)

        resolution_layout = QtWidgets.QHBoxLayout()
        resolution_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        resolution_layout.setSpacing(20)

        self.resolution_combo_box = QtWidgets.QComboBox()
        self.resolution_combo_box.setFixedSize(60, 22)
        self.resolution_combo_box.setEditable(True)
        self.resolution_combo_box.lineEdit().setReadOnly(True)
        self.resolution_combo_box.lineEdit().setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
        )
        self.resolution_combo_box.lineEdit().selectionChanged.connect(
            lambda: self.resolution_combo_box.lineEdit().deselect()
        )
        self.resolution_combo_box.addItem("10")
        self.resolution_combo_box.addItem("25")
        self.resolution_combo_box.addItem("50")
        self.resolution_combo_box.addItem("100")

        resolution_layout.addWidget(self.resolution_combo_box)

        project_picker_layout = QtWidgets.QGridLayout()
        project_picker_layout.setContentsMargins(0, 0, 0, 0)
        project_picker_layout.setHorizontalSpacing(5)
        project_picker_layout.setVerticalSpacing(10)

        project_picker_title = QtWidgets.QLabel()
        project_picker_title.setText("Project directory (must be empty)")

        self.project_picker_line_edit = QtWidgets.QLineEdit()
        self.project_picker_line_edit.textChanged.connect(
            self.validate_project_directory
        )

        project_picker_button = QtWidgets.QPushButton()
        project_picker_button.setText("...")
        project_picker_button.setFixedSize(25, 22)

        project_picker_button.clicked.connect(self.popup_file_picker)

        project_picker_layout.addWidget(
            project_picker_title,
            0,
            0,
            1,
            2,
            alignment=QtCore.Qt.AlignmentFlag.AlignLeft,
        )
        project_picker_layout.addWidget(self.project_picker_line_edit, 1, 0)
        project_picker_layout.addWidget(project_picker_button, 1, 1)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.submit_button = button_box.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
        )
        self.submit_button.setEnabled(False)
        button_box.accepted.connect(self.broadcast_project_create_settings)
        button_box.rejected.connect(self.close)

        main_layout.addRow("Atlas resolution", resolution_layout)
        main_layout.addRow(project_picker_layout)
        main_layout.addRow(button_box)

        self.setLayout(main_layout)

        self.setFixedSize(350, self.layout().sizeHint().height())

    def popup_file_picker(self) -> None:
        self.project_picker_line_edit.setText(
            QtWidgets.QFileDialog.getExistingDirectory(
                caption="Pick an empty project directory",
                options=QtWidgets.QFileDialog.Option.DontUseNativeDialog,
            )
        )

    @QtCore.Slot()
    def validate_project_directory(self, directory: str) -> None:
        # Check the directory is empty
        directory = Path(directory)

        valid = False
        try:
            next(directory.iterdir())
        except FileNotFoundError:
            pass
        except StopIteration:
            valid = True

        if valid:
            self.submit_button.setEnabled(True)
        else:
            self.submit_button.setEnabled(False)

    @QtCore.Slot()
    def broadcast_project_create_settings(self) -> None:
        self.create_project.emit(
            {
                "resolution": self.resolution_combo_box.currentText(),
                "directory": self.project_picker_line_edit.text(),
            }
        )
        self.close()
