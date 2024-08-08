# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import json
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


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
        self.clear()

        with open(metadata_path) as handle:
            contents = json.load(handle)

        self.addItem("")
        for file_path in contents:
            file_name = Path(file_path).stem
            self.name_to_path_map[file_name] = file_path
            self.addItem(file_name)

    def clear(self) -> None:
        super().clear()
        self.name_to_path_map = {"": ""}

    @QtCore.Slot()
    def notify_change(self, file_name) -> None:
        self.file_picked.emit(self.name_to_path_map[file_name])
