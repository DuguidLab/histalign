# SPDX-FileCopyrightText: 2025-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import pydantic
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.io import ICONS_ROOT
from histalign.backend.models import (
    ProjectSettings,
    Resolution,
    VolumeBuildingSettings,
)
from histalign.backend.volume_builder import (
    VolumeBuilderThread,
    VolumeInterpolatorThread,
)
from histalign.backend.workspace import Workspace
from histalign.frontend.common_widgets import (
    CutOffLabel,
    HoverButton,
    Icon,
    TitleFrame,
)
from histalign.frontend.pyside_helpers import lua_aware_shift
from histalign.frontend.quantification.prepare import QuantificationParametersFrame

_module_logger = logging.getLogger(__name__)


class VolumeBuilderWidget(QtWidgets.QWidget):
    project_root: Optional[Path]
    resolution: Optional[Resolution]
    running: bool

    parameters_frame: QuantificationParametersFrame
    add_job_button: QtWidgets.QPushButton
    run_jobs_button: QtWidgets.QPushButton
    jobs_layout: QtWidgets.QVBoxLayout
    main_widget: QtWidgets.QWidget
    progress_bar: QtWidgets.QProgressBar

    _jobs_map: dict[JobWidget, VolumeBuildingSettings]
    _jobs_thread: Optional[QtCore.QThread]
    _progress: int

    project_opened: QtCore.Signal = QtCore.Signal()
    project_closed: QtCore.Signal = QtCore.Signal()
    jobs_started: QtCore.Signal = QtCore.Signal()
    jobs_finished: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.project_root = None
        self.resolution = None
        self.running = False

        self._jobs_map = {}
        self._jobs_thread = None
        self._progress = 0

        # Create left column
        parameters_frame = QuantificationParametersFrame()
        self.parameters_frame = parameters_frame

        add_job_button = QtWidgets.QPushButton("Add job")
        add_job_button.clicked.connect(self.queue_job)
        add_job_button.setContentsMargins(
            parameters_frame.contentsMargins().left() - parameters_frame.frameWidth(),
            0,
            parameters_frame.contentsMargins().right() - parameters_frame.frameWidth(),
            parameters_frame.contentsMargins().bottom() - parameters_frame.frameWidth(),
        )
        self.add_job_button = add_job_button

        add_job_button_layout = QtWidgets.QHBoxLayout()
        add_job_button_layout.addWidget(add_job_button)
        add_job_button_layout.setContentsMargins(
            parameters_frame.contentsMargins().left() - parameters_frame.frameWidth(),
            0,
            parameters_frame.contentsMargins().right() - parameters_frame.frameWidth(),
            parameters_frame.contentsMargins().bottom() - parameters_frame.frameWidth(),
        )

        parameters_layout = QtWidgets.QVBoxLayout()
        parameters_layout.addWidget(parameters_frame)
        parameters_layout.addLayout(add_job_button_layout)

        # Create right column
        jobs_frame = TitleFrame("Jobs", bold=True)

        jobs_area = QtWidgets.QScrollArea()
        jobs_area.setWidgetResizable(True)
        jobs_area.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )

        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.addStretch(1)
        widget.setLayout(layout)
        jobs_area.setWidget(widget)
        self.jobs_layout = layout

        tmp_layout = QtWidgets.QHBoxLayout()
        tmp_layout.addWidget(jobs_area)

        jobs_frame.setLayout(tmp_layout)

        run_jobs_button = QtWidgets.QPushButton("Run jobs")
        run_jobs_button.clicked.connect(self.start_jobs)
        run_jobs_button.setContentsMargins(0, 0, 0, 0)
        self.run_jobs_button = run_jobs_button

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
        main_layout.addLayout(parameters_layout, stretch=1)
        main_layout.addLayout(jobs_layout, stretch=1)

        main_widget = QtWidgets.QWidget()
        main_widget.setLayout(main_layout)
        main_widget.setEnabled(False)
        self.main_widget = main_widget

        # Add a progress bar at the bottom
        progress_bar = QtWidgets.QProgressBar()
        self.progress_bar = progress_bar

        progress_bar_layout = QtWidgets.QHBoxLayout()
        progress_bar_layout.addWidget(progress_bar)
        progress_bar_layout.setContentsMargins(
            jobs_frame.contentsMargins().left() - jobs_frame.frameWidth(),
            0,
            jobs_frame.contentsMargins().right() - jobs_frame.frameWidth(),
            jobs_frame.contentsMargins().bottom() - jobs_frame.frameWidth(),
        )

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(main_widget)
        layout.addLayout(progress_bar_layout)

        self.setLayout(layout)

        self.project_opened.connect(lambda: self.main_widget.setEnabled(True))
        self.project_closed.connect(lambda: self.main_widget.setEnabled(False))
        self.jobs_started.connect(lambda: self.set_running_state(True))
        self.jobs_finished.connect(lambda: self.set_running_state(False))

    def open_project(self, project_file_path: str | Path) -> None:
        path = Path(project_file_path)

        with open(path) as handle:
            contents = json.load(handle)
        try:
            project_settings = ProjectSettings(**contents["project_settings"])
        except (KeyError, pydantic.ValidationError):
            _module_logger.error(
                f"Could not load project settings from project file at: {path}."
            )
            # TODO: Let main GUI know this failed
            return
        self.resolution = project_settings.resolution

        self.project_root = path.parent
        self.parameters_frame.directory_widget.parse_project(path.parent)

    def set_running_state(self, enabled: bool) -> None:
        self.running = enabled
        self.add_job_button.setEnabled(not enabled)
        self.run_jobs_button.setEnabled(not enabled)

    @QtCore.Slot()
    def queue_job(self) -> None:
        frame = self.parameters_frame

        widget = JobWidget(
            frame.directory_widget.currentText(),
            frame.z_stack_frame.check_box.isChecked(),
            frame.multichannel_frame.check_box.isChecked(),
        )
        self.jobs_layout.insertWidget(self.jobs_layout.count() - 1, widget)

        directory_hash = Workspace.generate_directory_hash(
            frame.directory_widget.currentText()
        )
        self._jobs_map[widget] = VolumeBuildingSettings(
            alignment_directory=self.project_root / directory_hash,
            original_directory=frame.directory_widget.currentText(),
            resolution=self.resolution,
            z_stack_regex=frame.z_stack_frame.regex_line_edit.text(),
            channel_regex=frame.multichannel_frame.regex_line_edit.text(),
            channel_index=frame.multichannel_frame.quantification_channel_line_edit.text(),
        )

        widget.remove_requested.connect(lambda: self.pop_job(widget))

    @QtCore.Slot()
    def pop_job(self, widget: JobWidget, user_made: bool = True) -> None:
        if user_made and self.running:
            return

        self._jobs_map.pop(widget)
        self.jobs_layout.takeAt(self.jobs_layout.indexOf(widget))
        widget.deleteLater()

    @QtCore.Slot()
    def start_jobs(self) -> None:
        self.jobs_started.emit()

        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(len(self._jobs_map.keys()) * 2)
        self._progress = -1
        self.increment_progress()

        self.build_next_volume()

    @QtCore.Slot()
    def build_next_volume(self) -> None:
        try:
            widget, settings = next(iter(self._jobs_map.items()))
        except StopIteration:
            self.jobs_finished.emit()
            return

        builder_thread = VolumeBuilderThread(settings, self)
        builder_thread.finished.connect(self.increment_progress)
        builder_thread.finished.connect(self.interpolate_next_volume)
        builder_thread.finished.connect(builder_thread.deleteLater)

        builder_thread.start()

    @QtCore.Slot()
    def interpolate_next_volume(self) -> None:
        widget, settings = next(iter(self._jobs_map.items()))

        interpolator_thread = VolumeInterpolatorThread(settings, self)
        interpolator_thread.finished.connect(
            lambda: self.pop_job(widget, user_made=False)
        )
        interpolator_thread.finished.connect(self.increment_progress)
        interpolator_thread.finished.connect(self.build_next_volume)
        interpolator_thread.finished.connect(interpolator_thread.deleteLater)

        interpolator_thread.start()

    @QtCore.Slot()
    def increment_progress(self) -> None:
        self._progress += 1

        try:
            directory_name = next(iter(self._jobs_map.items()))[
                1
            ].original_directory.name

            if self._progress % 2 == 0:
                message = f"Building aligned volume for '{directory_name}'."
            else:
                message = f"Interpolating aligned volume for '{directory_name}'."
        except StopIteration:
            message = "All jobs have finished"

        message += " (%p%)"

        self.progress_bar.setFormat(message)
        self.progress_bar.setValue(self._progress)


class JobWidget(QtWidgets.QFrame):
    remove_requested: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        folder_text: str,
        z_stacks: bool,
        multi_channel: bool,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        check_icon_path = ICONS_ROOT / "check-mark-box-line-icon.png"
        cross_icon_path = ICONS_ROOT / "close-square-line-icon.png"

        folder_label = CutOffLabel(folder_text)

        z_stack_label = QtWidgets.QLabel("Z-stacks?")
        z_stack_icon = Icon(check_icon_path if z_stacks else cross_icon_path)

        z_stack_layout = QtWidgets.QHBoxLayout()
        z_stack_layout.addWidget(z_stack_label)
        z_stack_layout.addWidget(z_stack_icon)
        z_stack_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)

        multi_channel_label = QtWidgets.QLabel("Multi-channel?")
        multi_channel_icon = Icon(check_icon_path if multi_channel else cross_icon_path)

        multi_channel_layout = QtWidgets.QHBoxLayout()
        multi_channel_layout.addWidget(multi_channel_label)
        multi_channel_layout.addWidget(multi_channel_icon)
        multi_channel_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)

        bottom_layout = QtWidgets.QHBoxLayout()
        bottom_layout.addLayout(z_stack_layout)
        bottom_layout.addLayout(multi_channel_layout)

        close_button = HoverButton(
            shift=40, icon_path=ICONS_ROOT / "close-line-icon.png"
        )
        close_button.setFixedSize(40, 40)
        close_button.clicked.connect(self.remove_requested.emit)

        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addWidget(
            folder_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter
        )
        main_layout.addLayout(bottom_layout)
        main_layout.setContentsMargins(0, 0, 0, 0)

        layout = QtWidgets.QHBoxLayout()
        layout.addLayout(main_layout, stretch=1)
        layout.addWidget(close_button, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self.setLayout(layout)

        self.setFrameShape(QtWidgets.QFrame.Shape.Box)

        palette = self.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Window,
            lua_aware_shift(palette.window().color(), 20),
        )
        self.setPalette(palette)

        self.setAutoFillBackground(True)
