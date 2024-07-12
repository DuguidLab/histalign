# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import sys

import click
from PySide6 import QtWidgets

from histalign.application import Histalign


@click.command()
@click.option(
    "--average-template",
    required=True,
    type=click.STRING,
)
@click.option(
    "--fullscreen",
    required=False,
    is_flag=True,
)
def histalign(
    average_template: str,
    fullscreen: bool = False,
) -> None:
    app = QtWidgets.QApplication()

    window = Histalign(
        average_volume_file_path=average_template,
        fullscreen=fullscreen,
    )
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    histalign(sys.argv[1:])
