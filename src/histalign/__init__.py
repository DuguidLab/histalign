# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import sys

import click
from PySide6 import QtWidgets

from histalign.application import Histalign


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
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    histalign(sys.argv[1:])
