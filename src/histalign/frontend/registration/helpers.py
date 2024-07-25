# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from PySide6 import QtGui, QtWidgets


def get_dummy_title_bar(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    top_margin = parent.contentsMargins().top()
    if top_margin == 0:
        title_bar = QtWidgets.QWidget()
    else:
        title_bar = QtWidgets.QLabel()
        font = QtGui.QFont()
        font.setPixelSize(1)
        title_bar.setFont(font)
    title_bar.setMinimumHeight(parent.contentsMargins().top())
    return title_bar
