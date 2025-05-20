# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

"""The main application entry point."""

if __name__ == "histalign":
    # Fix a typing bug when using `vedo` with python==3.10.12.
    # Leaving `typing_extensions.Self` as-is leads to the following error message:
    # TypeError: Plain typing.Self is not valid as type argument
    # and happens because vedo uses the `Self` annotation in the return type of some
    # methods, while it apparently is malformed.
    from typing import TypeVar

    import typing_extensions

    Self = TypeVar("Self")
    typing_extensions.Self = Self  # type: ignore[assignment]

import logging
import sys

import click
from PySide6 import QtCore, QtWidgets

from histalign.frontend import HistalignMainWindow
from histalign.frontend.themes import DARK_THEME, LIGHT_THEME
from histalign.io.convert import convert
from histalign.io.image import list_formats, load_plugins
from histalign.io.info import info
from histalign.io.project import project
from histalign.io.split import split
from histalign.io.transform import transform

PREFERRED_STARTUP_SIZE = QtCore.QSize(1600, 900)

# Set up package logging
_module_logger = logging.getLogger("histalign")
if __name__ == "histalign":
    _formatter = logging.Formatter(
        "[{asctime}] - [{levelname:>8s} ] - {message} ({name}:{lineno})",
        style="{",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _console_handler = logging.StreamHandler()
    _console_handler.setFormatter(_formatter)

    _module_logger.addHandler(_console_handler)


@click.group(invoke_without_command=True)
@click.pass_context
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
def histalign(
    context: click.Context, verbosity: int, fullscreen: bool, dark: bool, debug_ui: bool
) -> None:
    """Root command with which to start the main GUI application.

    To use the command-line interface for IO, refer to the subcommands.
    """
    # Handle setting up plugins for IO subcommands
    load_plugins()

    if verbosity == 1:
        set_log_level(logging.INFO)
    elif verbosity >= 2:
        set_log_level(logging.DEBUG)

    if context.invoked_subcommand is not None:
        # Pass control to subcommand
        return

    # Start in GUI mode
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


histalign.add_command(convert, "convert")
histalign.add_command(list_formats, "list")
histalign.add_command(info, "info")
histalign.add_command(project, "project")
histalign.add_command(split, "split")
histalign.add_command(transform, "transform")


if __name__ == "__main__":
    histalign(sys.argv[1:])
