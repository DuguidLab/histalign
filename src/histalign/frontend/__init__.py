# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from typing import Optional

from PySide6 import QtCore, QtWidgets

from histalign.frontend.centralised import CentralisedWindow
from histalign.frontend.qa import QAMainWindow
from histalign.frontend.registration import RegistrationMainWindow


PREFERRED_STARTUP_SIZE = QtCore.QSize(1600, 900)


class ApplicationWidget(QtWidgets.QWidget):
    main_window: QtWidgets.QWidget

    def __init__(self, fullscreen: bool = False) -> None:
        super().__init__(None)

        main_window = QtWidgets.QWidget()
        self.main_window = main_window

        layout = QtWidgets.QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(main_window)
        self.setLayout(layout)

        if fullscreen:
            self.showMaximized()
        else:
            self.resize(self.get_startup_size())
            self.show()

    def open_centralised_window(self) -> None:
        self.set_main_window(CentralisedWindow())

    def open_registration_window(self) -> None:
        self.set_main_window(RegistrationMainWindow())
        self.main_window.project_closed.connect(self.main_window.close)
        self.main_window.project_closed.connect(self.open_centralised_window)

    def open_qa_window(self) -> None:
        self.set_main_window(QAMainWindow())

    def set_main_window(self, window: QtWidgets.QWidget) -> None:
        old_main_window = self.layout().takeAt(0).widget()

        window.setParent(self)
        self.layout().addWidget(window)
        self.main_window = window

        old_main_window.deleteLater()

        if isinstance(window, CentralisedWindow):
            title = "Histalign"
        elif isinstance(window, RegistrationMainWindow):
            title = "Histalign - Registration"
        elif isinstance(window, QAMainWindow):
            title = "Histalign - QA"
        else:
            title = "Histalign"
            logging.getLogger(__name__).warning(
                f"Could not set custom title for window type '{type(window)}'."
            )

        self.setWindowTitle(title)

    @staticmethod
    def get_startup_size() -> QtCore.QSize:
        screen = QtWidgets.QApplication.screens()[0]

        if (
            screen.size().width() > PREFERRED_STARTUP_SIZE.width()
            and screen.size().height() > PREFERRED_STARTUP_SIZE.height()
        ):
            return PREFERRED_STARTUP_SIZE
        else:
            return QtCore.QSize(
                round(screen.size().width() * 0.75),
                round(screen.size().height() * 0.75),
            )
