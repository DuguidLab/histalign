# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
import sys
from typing import Callable

import click
from PySide6 import QtCore, QtWidgets

from histalign.frontend import ApplicationWidget

if __name__ == "histalign":
    logger = logging.getLogger(__name__)
    formatter = logging.Formatter(logging.BASIC_FORMAT)
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)


PREFERRED_STARTUP_SIZE = QtCore.QSize(1600, 900)


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
            )(function)
        )
    )


@click.group(invoke_without_command=True)
@common_options
@click.pass_context
def histalign(
    context: click.Context, verbosity: int, fullscreen: bool, debug_ui: bool
) -> None:
    if not context.invoked_subcommand:
        start_app(verbosity, fullscreen, debug_ui, callback="open_centralised_window")


@histalign.command()
@common_options
def register(verbosity: int, fullscreen: bool, debug_ui: bool) -> None:
    start_app(verbosity, fullscreen, debug_ui, callback="open_registration_window")


@histalign.command()
@common_options
def qa(verbosity: int, fullscreen: bool, debug_ui: bool) -> None:
    start_app(verbosity, fullscreen, debug_ui, callback="open_qa_window")


def quantify() -> None:
    pass


def visualise() -> None:
    pass


def start_app(
    verbosity: int,
    fullscreen: bool,
    debug_ui: bool,
    *args,
    callback: str,
    **kwargs,
) -> None:
    if verbosity == 1:
        logging.getLogger("histalign").setLevel(logging.INFO)
    elif verbosity >= 2:
        logging.getLogger("histalign").setLevel(logging.DEBUG)

    app = QtWidgets.QApplication()

    if debug_ui:
        app.setStyleSheet("* { border: 1px solid blue; }")

    window = ApplicationWidget(fullscreen=fullscreen)
    getattr(window, callback)()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    histalign(sys.argv[1:])
