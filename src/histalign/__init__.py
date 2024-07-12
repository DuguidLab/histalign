# SPDX-FileCopyrightText: 2024-present Olivier Delree <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import sys

import click
from PySide6 import QtWidgets

from histalign.application import Histalign


@click.command()
@click.option(
    "--image-directory",
    required=True,
    type=click.STRING,
)
@click.option(
    "--histology-slice",
    required=True,
    type=click.STRING,
)
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
    image_directory: str,
    histology_slice: str,
    average_template: str,
    fullscreen: bool = False,
) -> None:
    app = QtWidgets.QApplication()

    window = Histalign(
        image_directory=image_directory,
        histology_slice_file_path=histology_slice,
        average_volume_file_path=average_template,
        fullscreen=fullscreen,
    )
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    histalign(sys.argv[1:])
