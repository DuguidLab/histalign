import os
from pathlib import Path
import sys
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class MainMenuBar(QtWidgets.QMenuBar):
    create_project_request: QtCore.Signal = QtCore.Signal()
    open_project: QtCore.Signal = QtCore.Signal(str)
    open_image_directory: QtCore.Signal = QtCore.Signal(str)
    open_atlas: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        file_menu = self.addMenu("&File")

        create_workspace_action = QtGui.QAction("Create &project", self)
        create_workspace_action.triggered.connect(self.create_project_request.emit)

        open_workspace_action = QtGui.QAction("Open p&roject", self)
        open_workspace_action.triggered.connect(self.open_project_picker)

        open_image_directory_action = QtGui.QAction("Open &image directory", self)
        open_image_directory_action.triggered.connect(self.open_image_directory_picker)

        open_atlas_action = QtGui.QAction("Open &atlas volume", self)
        open_atlas_action.triggered.connect(self.open_atlas_file_picker)

        file_menu.addAction(create_workspace_action)
        file_menu.addAction(open_workspace_action)
        file_menu.addAction(open_image_directory_action)
        file_menu.addAction(open_atlas_action)

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

    @QtCore.Slot()
    def open_atlas_file_picker(self) -> None:
        atlas_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select an atlas volume file",
            os.getcwd(),
            "Atlas (*.npy *.nrrd)",
            options=QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )

        if atlas_path == "":
            return

        self.open_atlas.emit(atlas_path)

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
