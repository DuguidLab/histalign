# SPDX-FileCopyrightText: 2025-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.io import RESOURCES_ROOT
from histalign.frontend.common_widgets import (
    CutOffLabel,
    Icon,
    TitleFrame,
)
from histalign.frontend.pyside_helpers import lua_aware_shift
from histalign.frontend.quantification.prepare import QuantificationParametersFrame

_module_logger = logging.getLogger(__name__)


class VolumeBuilderWidget(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        parameters_frame = QuantificationParametersFrame()

        jobs_frame = TitleFrame("Jobs", bold=True)

        job_sub_layout = QtWidgets.QVBoxLayout()
        for i in range(3):
            job_sub_layout.addWidget(JobWidget())
        job_sub_layout.addStretch(1)
        jobs_frame.setLayout(job_sub_layout)

        run_jobs_button = QtWidgets.QPushButton("Run jobs")
        run_jobs_button.setContentsMargins(0, 0, 0, 0)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(run_jobs_button)
        button_layout.setContentsMargins(
            jobs_frame.contentsMargins().left() - jobs_frame.frameWidth(),
            0,
            jobs_frame.contentsMargins().right() - jobs_frame.frameWidth(),
            jobs_frame.contentsMargins().bottom() - jobs_frame.frameWidth(),
        )

        jobs_layout = QtWidgets.QVBoxLayout()
        jobs_layout.addWidget(jobs_frame)
        jobs_layout.addLayout(button_layout)

        main_layout = QtWidgets.QHBoxLayout()
        main_layout.addWidget(parameters_frame, stretch=1)
        main_layout.addLayout(jobs_layout, stretch=1)

        progress_bar = QtWidgets.QProgressBar()

        progress_bar_layout = QtWidgets.QHBoxLayout()
        progress_bar_layout.addWidget(progress_bar)
        progress_bar_layout.setContentsMargins(
            jobs_frame.contentsMargins().left() - jobs_frame.frameWidth(),
            0,
            jobs_frame.contentsMargins().right() - jobs_frame.frameWidth(),
            jobs_frame.contentsMargins().bottom() - jobs_frame.frameWidth(),
        )

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(main_layout)
        layout.addLayout(progress_bar_layout)

        self.setLayout(layout)


class JobWidget(QtWidgets.QFrame):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        folder_label = CutOffLabel("/home/user/data/project/experiment/subject/images")

        z_stack_label = QtWidgets.QLabel("Z-stacks?")

        z_stack_icon = Icon(RESOURCES_ROOT / "icons" / "check-mark-square-icon.png")

        z_stack_layout = QtWidgets.QHBoxLayout()
        z_stack_layout.addWidget(z_stack_label)
        z_stack_layout.addWidget(z_stack_icon)
        z_stack_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)

        multi_channel_label = QtWidgets.QLabel("Multi-channel?")

        multi_channel_icon = Icon(
            RESOURCES_ROOT / "icons" / "check-mark-square-icon.png"
        )

        multi_channel_layout = QtWidgets.QHBoxLayout()
        multi_channel_layout.addWidget(multi_channel_label)
        multi_channel_layout.addWidget(multi_channel_icon)
        multi_channel_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)

        bottom_layout = QtWidgets.QHBoxLayout()
        bottom_layout.addLayout(z_stack_layout)
        bottom_layout.addLayout(multi_channel_layout)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(folder_label)
        layout.addLayout(bottom_layout)
        self.setLayout(layout)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        self.setFrameShape(QtWidgets.QFrame.Shape.Box)

        palette = self.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Window,
            lua_aware_shift(palette.window().color(), 20),
        )
        self.setPalette(palette)

        self.setAutoFillBackground(True)
