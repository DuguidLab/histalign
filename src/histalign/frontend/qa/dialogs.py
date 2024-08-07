# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class StructureNameInputDialog(QtWidgets.QDialog):
    completion_options: list[str]

    line_edit: QtWidgets.QLineEdit

    submitted: QtCore.Signal = QtCore.Signal(str)

    def __init__(
        self, completion_options: list[str], parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__(parent)

        self.line_edit = QtWidgets.QLineEdit()
        self.structure_names_list = completion_options
        completer = QtWidgets.QCompleter(self.structure_names_list, self.line_edit)
        completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.line_edit.setCompleter(completer)
        # Select first row from popup when pressing return without a row highlighted
        self.line_edit.returnPressed.connect(
            lambda: self.line_edit.setText(
                completer.completionModel().index(completer.currentRow(), 0).data()
                if completer.popup().isVisible()
                else self.line_edit.text()
            )
        )

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.button(QtWidgets.QDialogButtonBox.Ok).clicked.connect(self.validate)
        button_box.button(QtWidgets.QDialogButtonBox.Cancel).clicked.connect(self.close)

        layout = QtWidgets.QFormLayout()

        layout.addWidget(self.line_edit)
        layout.addWidget(button_box)

        self.setLayout(layout)

        self._blinking_timer = QtCore.QTimer(self)
        self._stop_blinking_timer = QtCore.QTimer(self)
        self._stop_blinking_timer.setSingleShot(True)

        default_colour = self.line_edit.palette().color(QtGui.QPalette.Base).name()
        blinking_colour = "#cccccc"
        self._blinking_timer.timeout.connect(
            lambda: self.toggle_colour(
                self.line_edit, (default_colour, blinking_colour)
            )
        )
        self._stop_blinking_timer.timeout.connect(self._blinking_timer.stop)
        # Ensure we don't end on blinking colour because of weird timing
        self._stop_blinking_timer.timeout.connect(
            lambda: self.toggle_colour(self.line_edit, (default_colour, default_colour))
        )

        self.setWindowTitle("Select a structure")
        self.setMinimumWidth(300)

    def report_wrong_input(
        self, blinking_interval: int = 150, blink_count: int = 2
    ) -> None:
        # User spammed return
        if self._blinking_timer.isActive():
            return

        self._blinking_timer.start(blinking_interval)
        self._stop_blinking_timer.start(2 * blink_count * blinking_interval)

    @QtCore.Slot()
    def validate(self) -> None:
        current_text = self.line_edit.text()
        if current_text not in self.structure_names_list:
            self.report_wrong_input()
        else:
            self.submitted.emit(current_text)
            self.close()

    @staticmethod
    def toggle_colour(widget: QtWidgets.QWidget, colours: tuple[str, str]) -> None:
        if widget.palette().color(QtGui.QPalette.Base).name() == colours[0]:
            new_colour = colours[1]
        else:
            new_colour = colours[0]

        widget.setStyleSheet(f"background-color: {new_colour}")
