# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import sys

import click
from PySide6 import QtCore, QtWidgets

from histalign.application import Histalign


PREFERRED_STARTUP_SIZE = QtCore.QSize(1600, 900)


@click.command()
@click.option(
    "--fullscreen",
    required=False,
    is_flag=True,
)
def histalign(fullscreen: bool = False) -> None:
    app = QtWidgets.QApplication()

    window = Histalign(
        fullscreen=fullscreen,
    )

    screen = app.screens()[0]
    if (
        screen.size().width() > PREFERRED_STARTUP_SIZE.width()
        and screen.size().height() > PREFERRED_STARTUP_SIZE.height()
    ):
        window.resize(PREFERRED_STARTUP_SIZE)
    else:
        window.resize(
            round(screen.size().width() * 0.75), round(screen.size().height() * 0.75)
        )

    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    histalign(sys.argv[1:])
