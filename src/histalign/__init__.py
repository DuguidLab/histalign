# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

if __name__ == "__main__":
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
from typing import Callable

import click
from PySide6 import QtCore, QtWidgets

from histalign.frontend import ApplicationWidget
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


def set_log_level(level: int | str) -> None:
    _module_logger.setLevel(level)


def common_options(function: Callable) -> click.option:
    return click.option(
        "-v",
        "--verbose",
        "verbosity",
        required=False,
        count=True,
        help=(
            "Set verbosity level. Level 0 is WARNING (default). Level 1 is INFO. "
            "Level 2 is DEBUG."
        ),
    )(
        click.option(
            "--fullscreen",
            is_flag=True,
            help="Whether to start the application in fullscreen.",
        )(
            click.option(
                "--debug-ui",
                is_flag=True,
                help=(
                    "Whether to enable UI debugging. "
                    "This adds a border around elements."
                ),
            )(
                click.option(
                    "--dark",
                    is_flag=True,
                    help="Enable experimental dark theme.",
                )(function)
            )
        )
    )


@click.group(invoke_without_command=True)
@common_options
@click.pass_context
def histalign(
    context: click.Context, verbosity: int, fullscreen: bool, debug_ui: bool, dark: bool
) -> None:
    if not context.invoked_subcommand:
        start_app(
            verbosity, fullscreen, debug_ui, dark, callback="open_centralised_window"
        )


@histalign.command()
@common_options
def register(verbosity: int, fullscreen: bool, debug_ui: bool, dark: bool) -> None:
    start_app(
        verbosity, fullscreen, debug_ui, dark, callback="open_registration_window"
    )


@histalign.command()
@common_options
def qa(verbosity: int, fullscreen: bool, debug_ui: bool, dark: bool) -> None:
    start_app(verbosity, fullscreen, debug_ui, dark, callback="open_qa_window")


@histalign.command()
@common_options
def preprocess(verbosity: int, fullscreen: bool, debug_ui: bool, dark: bool) -> None:
    start_app(
        verbosity, fullscreen, debug_ui, dark, callback="open_preprocessing_window"
    )


@histalign.command()
@common_options
def quantify(verbosity: int, fullscreen: bool, debug_ui: bool, dark: bool) -> None:
    start_app(
        verbosity, fullscreen, debug_ui, dark, callback="open_quantification_window"
    )


@histalign.command()
@common_options
def visualise(verbosity: int, fullscreen: bool, debug_ui: bool, dark: bool) -> None:
    start_app(
        verbosity, fullscreen, debug_ui, dark, callback="open_visualisation_window"
    )


def start_app(
    verbosity: int,
    fullscreen: bool,
    debug_ui: bool,
    dark: bool,
    *args,
    callback: str,
    **kwargs,
) -> None:
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
    app.dark = dark

    if debug_ui:
        app.setStyleSheet("* { border: 1px solid blue; }")

    window = ApplicationWidget(fullscreen=fullscreen)
    getattr(window, callback)()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    histalign(sys.argv[1:])
