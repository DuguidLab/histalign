# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
import sys
from typing import Callable

import click
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.frontend.qa import QAMainWindow
from histalign.frontend.registration import RegistrationMainWindow


if __name__ == "histalign":
    logger = logging.getLogger(__name__)
    formatter = logging.Formatter(logging.BASIC_FORMAT)
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)


PREFERRED_STARTUP_SIZE = QtCore.QSize(1600, 900)


def default_options(function: Callable) -> click.option:
    return click.option(
        "--fullscreen",
        is_flag=True,
    )(
        click.option(
            "--debug-ui",
            is_flag=True,
        )(function)
    )


@click.group()
@click.option(
    "-v",
    "--verbose",
    "verbosity",
    required=False,
    count=True,
    help=(
        "Set verbosity level. Level 0 is WARNING (default). Level 1 is INFO. "
        "Level 2 is DEBUG."
    ),
)
def histalign(verbosity: int) -> None:
    if verbosity == 1:
        logging.getLogger("histalign").setLevel(logging.INFO)
    elif verbosity >= 2:
        logging.getLogger("histalign").setLevel(logging.DEBUG)


@histalign.command()
@default_options
def register(fullscreen: bool = False, debug_ui: bool = False) -> None:
    app = QtWidgets.QApplication()

    if debug_ui:
        app.setStyleSheet("* { border: 1px solid blue; }")

    window = RegistrationMainWindow()

    screen = app.screens()[0]
    window.resize(get_startup_size(screen))

    if fullscreen:
        window.showMaximized()
    else:
        window.show()

    sys.exit(app.exec())


@histalign.command()
@default_options
def qa(fullscreen: bool = False, debug_ui: bool = False) -> None:
    app = QtWidgets.QApplication()

    if debug_ui:
        app.setStyleSheet("* { border: 1px solid blue; }")

    window = QAMainWindow()
    window.show()

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


if __name__ == "__main__":
    histalign(sys.argv[1:])
