# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.frontend.preprocessing import PreprocessingMainWindow
from histalign.frontend.qa import QAMainWindow
from histalign.frontend.quantification import QuantificationMainWindow
from histalign.frontend.registration import RegistrationMainWindow
from histalign.frontend.visualisation import VisualisationMainWindow


class PlaceholderPage(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        label = QtWidgets.QLabel("PLACEHOLDER")

        font = QtGui.QFont()
        font.setPointSize(50)
        label.setFont(font)

        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(QtGui.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        self.setLayout(layout)


class Button(QtWidgets.QPushButton):
    def __init__(self, text: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(text, parent)

        font = QtGui.QFont()
        font.setPointSize(25)
        self.setFont(font)
        self.setFixedHeight(100)


class TabProxyStyle(QtWidgets.QProxyStyle):
    def sizeFromContents(
        self,
        type: QtWidgets.QStyle.ContentsType,
        option: QtWidgets.QStyleOption,
        size: QtCore.QSize,
        widget: Optional[QtWidgets.QWidget],
    ) -> QtCore.QSize:
        size = super().sizeFromContents(type, option, size, widget)
        if type == QtWidgets.QStyle.ContentsType.CT_TabBarTab:
            size.transpose()
            size = QtCore.QSize(150, 150)
        return size

    def drawControl(
        self,
        element: QtWidgets.QStyle.ControlElement,
        option: QtWidgets.QStyleOption,
        painter: QtGui.QPainter,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        if element == QtWidgets.QStyle.ControlElement.CE_TabBarTabLabel:
            font = QtGui.QFont()
            font.setPointSize(15)
            painter.setFont(font)

            option.shape = QtWidgets.QTabBar.Shape.RoundedNorth
        super().drawControl(element, option, painter, widget)


class CentralisedWindow(QtWidgets.QTabWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        global main_window

        super().__init__(parent)

        #
        create_project_button = Button("Create project")
        create_project_button.clicked.connect(self.registration_create_project)

        open_project_button = Button("Open project")
        open_project_button.clicked.connect(self.registration_open_project)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(create_project_button)
        layout.addWidget(open_project_button)

        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(50, 20, 50, 20)
        layout.setSpacing(50)

        tab = QtWidgets.QWidget()
        tab.setLayout(layout)

        self.addTab(tab, "Register")

        #
        open_project_button = Button("Open project")
        open_project_button.clicked.connect(self.preprocessing_open_project)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(open_project_button)

        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(50, 20, 50, 20)
        layout.setSpacing(50)

        tab = QtWidgets.QWidget()
        tab.setLayout(layout)

        self.addTab(tab, "Preprocess")

        #
        open_project_button = Button("Open project")
        open_project_button.clicked.connect(self.qa_open_project)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(open_project_button)

        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(50, 20, 50, 20)
        layout.setSpacing(50)

        tab = QtWidgets.QWidget()
        tab.setLayout(layout)

        self.addTab(tab, "QA")

        #
        open_project_button = Button("Open project")
        open_project_button.clicked.connect(self.quantification_open_project)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(open_project_button)

        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(50, 20, 50, 20)
        layout.setSpacing(50)

        tab = QtWidgets.QWidget()
        tab.setLayout(layout)

        self.addTab(tab, "Quantify")

        #
        open_project_button = Button("Open project")
        open_project_button.clicked.connect(self.visualisation_open_project)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(open_project_button)

        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(50, 20, 50, 20)
        layout.setSpacing(50)

        tab = QtWidgets.QWidget()
        tab.setLayout(layout)

        self.addTab(tab, "Visualise")

        #
        self.setTabPosition(QtWidgets.QTabWidget.TabPosition.West)
        self.tabBar().setStyle(TabProxyStyle())

    @QtCore.Slot()
    def registration_create_project(self) -> None:
        new_window = RegistrationMainWindow(self)
        new_window.project_closed.connect(
            lambda x=self.parent(): x.open_centralised_window()
        )

        dialog = new_window.show_create_project_dialog()  # Non-blocking
        if dialog is None:
            raise ValueError("Did not receive a dialog.")

        dialog.submitted.connect(lambda: self.parent().set_main_window(new_window))
        dialog.rejected.connect(new_window.deleteLater)

    @QtCore.Slot()
    def registration_open_project(self) -> None:
        new_window = RegistrationMainWindow(self)

        new_window.show_open_project_dialog()  # Blocking

        if not new_window.workspace_loaded:
            # User cancelled
            new_window.deleteLater()
            return

        self.parent().set_main_window(new_window)

    @QtCore.Slot()
    def preprocessing_open_project(self) -> None:
        new_window = PreprocessingMainWindow(self)

        new_window.show_open_project_dialog()  # Blocking

        if not new_window.project_loaded:
            # User cancelled
            return

        self.parent().set_main_window(new_window)

    @QtCore.Slot()
    def qa_open_project(self) -> None:
        new_window = QAMainWindow(self)

        new_window.show_open_project_dialog()  # Blocking

        if not new_window.project_loaded:
            # User cancelled
            return

        self.parent().set_main_window(new_window)

    @QtCore.Slot()
    def quantification_open_project(self) -> None:
        new_window = QuantificationMainWindow(self)

        new_window.show_open_project_dialog()

        if not new_window.project_loaded:
            # User cancelled
            new_window.deleteLater()
            return

        self.parent().set_main_window(new_window)

    @QtCore.Slot()
    def visualisation_open_project(self) -> None:
        new_window = VisualisationMainWindow(self)

        new_window.show_open_project_dialog()

        if not new_window.project_loaded:
            # User cancelled
            new_window.deleteLater()
            return

        self.parent().set_main_window(new_window)
