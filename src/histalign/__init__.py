# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import sys

import click
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.frontend.registration import RegistrationMainWindow


PREFERRED_STARTUP_SIZE = QtCore.QSize(1600, 900)


@click.group()
def histalign() -> None:
    pass


@click.command()
@click.option(
    "--fullscreen",
    is_flag=True,
)
def register(fullscreen: bool = False) -> None:
    app = QtWidgets.QApplication()

    window = RegistrationMainWindow()

    screen = app.screens()[0]
    window.resize(get_startup_size(screen))

    if fullscreen:
        window.showMaximized()
    else:
        window.show()

    sys.exit(app.exec())


def get_startup_size(screen: QtGui.QScreen) -> QtCore.QSize:
    if (
        screen.size().width() > PREFERRED_STARTUP_SIZE.width()
        and screen.size().height() > PREFERRED_STARTUP_SIZE.height()
    ):
        return PREFERRED_STARTUP_SIZE
    else:
        return QtCore.QSize(
            round(screen.size().width() * 0.75), round(screen.size().height() * 0.75)
        )


histalign.add_command(register)


if __name__ == "__main__":
    histalign(sys.argv[1:])
