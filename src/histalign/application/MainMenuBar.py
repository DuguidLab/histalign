import os
from pathlib import Path
import sys
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class MainMenuBar(QtWidgets.QMenuBar):
    create_project: QtCore.Signal = QtCore.Signal(str)
    open_project: QtCore.Signal = QtCore.Signal(str)
    open_image_directory: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        file_menu = self.addMenu("&File")

        create_workspace_action = QtGui.QAction("Create &project", self)
        create_workspace_action.triggered.connect(self.create_project_picker)

        open_workspace_action = QtGui.QAction("Open &project", self)
        open_workspace_action.triggered.connect(self.open_project_picker)

        open_image_directory_action = QtGui.QAction("Open &image directory", self)
        open_image_directory_action.triggered.connect(self.open_image_directory_picker)

        file_menu.addAction(create_workspace_action)
        file_menu.addAction(open_workspace_action)
        file_menu.addAction(open_image_directory_action)

    @QtCore.Slot()
    def create_project_picker(self) -> None:
        directory_path = self.open_directory_picker("Select a new project directory")

        if directory_path == "":
            return

        try:
            # Only check for a single item instead of converting iterator to a list
            next(Path(directory_path).iterdir())

            message_box = QtWidgets.QMessageBox(self.parent())
            message_box.setText("Project directory should be empty.")
            message_box.open()

            return
        except StopIteration:
            pass

        # Directory is empty, good to go
        self.create_project.emit(directory_path)

    @QtCore.Slot()
    def open_project_picker(self) -> None:
        project_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select a project directory",
            os.getcwd(),
            "Project (*.txt)",
            options=QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )

        if project_path == "":
            return

        self.open_project.emit(project_path)

    @QtCore.Slot()
    def open_image_directory_picker(self) -> None:
        directory_path = self.open_directory_picker("Select an image directory.")

        if directory_path == "":
            return

        self.open_image_directory.emit(directory_path)

    def open_directory_picker(self, title: str) -> str:
        return QtWidgets.QFileDialog.getExistingDirectory(
            self,
            title,
            os.getcwd(),
            options=QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )


if __name__ == "__main__":
    app = QtWidgets.QApplication()

    window = QtWidgets.QMainWindow()
    window.setWindowTitle("FileDialog Playground")
    window.setFixedSize(1600, 900)
    window.setMenuBar(MainMenuBar())
    window.show()

    sys.exit(app.exec())
