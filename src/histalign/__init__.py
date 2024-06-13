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
def histalign(average_template: str) -> None:
    app = QtWidgets.QApplication()

    window = Histalign(file_path=average_template)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    histalign(sys.argv[1:])
