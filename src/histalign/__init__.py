# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

if __name__ in ["__main__", "histalign"]:
    # Fix a typing bug when using `vedo` with python==3.10.12.
    # Leaving `typing_extensions.Self` as-is leads to the following error message:
    # TypeError: Plain typing.Self is not valid as type argument
    # and happens because vedo uses the `Self` annotation in the return type of some
    # methods, while it apparently is malformed.
    # Avoid being invasive by only patching it when we're the main application.
    from typing import TypeVar

    import typing_extensions

    Self = TypeVar("Self")
    typing_extensions.Self = Self

import logging
import sys

import click
from PySide6 import QtCore, QtWidgets

from histalign.frontend import HistalignMainWindow
from histalign.frontend.themes import DARK_THEME, LIGHT_THEME

PREFERRED_STARTUP_SIZE = QtCore.QSize(1600, 900)

# Set up package logging
_module_logger = logging.getLogger(__name__)

_formatter = logging.Formatter(
    "[{asctime}] - [{levelname:>8s} ] - {message} ({name}:{lineno})",
    style="{",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)

_module_logger.addHandler(_console_handler)


@click.command
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
@click.option(
    "--fullscreen",
    is_flag=True,
    help="Whether to start the application in fullscreen.",
)
@click.option(
    "--dark",
    is_flag=True,
    help="Enable experimental dark theme.",
)
@click.option(
    "--debug-ui",
    is_flag=True,
    help="Whether to enable UI debugging. " "This adds a border around elements.",
)
def histalign(verbosity: int, fullscreen: bool, dark: bool, debug_ui: bool) -> None:
    if verbosity == 1:
        set_log_level(logging.INFO)
    elif verbosity >= 2:
        set_log_level(logging.DEBUG)

    app = QtWidgets.QApplication()

    app.setStyle("Fusion")
    if dark:
        app.setPalette(DARK_THEME)
    else:
        app.setPalette(LIGHT_THEME)

    font = app.font()
    font.setFamily("Sans Serif")
    app.setFont(font)

    if debug_ui:
        app.setStyleSheet("* { border: 1px solid blue; }")

    window = HistalignMainWindow()
    if fullscreen:
        window.showMaximized()
    else:
        window.resize(compute_startup_size())
        window.show()

    sys.exit(app.exec())


def compute_startup_size() -> QtCore.QSize:
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


def set_log_level(level: int | str) -> None:
    _module_logger.setLevel(level)


if __name__ == "__main__":
    histalign(sys.argv[1:])
