# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.models import (
    Quantification,
    QuantificationSettings,
    Resolution,
)
from histalign.backend.quantification import QuantificationThread
from histalign.backend.workspace import Workspace
from histalign.frontend import lua_aware_shift
from histalign.frontend.common_widgets import (
    AnimatedCheckBox,
    ColumnsFrame,
    CutOffLabel,
    HoverButton,
    ProjectDirectoriesComboBox,
    StructureFinderDialog,
    StructureTagHolderWidget,
    TitleFrame,
)
from histalign.language_helpers import unwrap
from histalign.resources import ICONS_ROOT


class PrepareWidget(QtWidgets.QWidget):
    project_root: Optional[Path]
    resolution: Optional[Resolution]
    running: bool

    quantification_parameters_frame: QuantificationParametersFrame
    jobs_frame: ColumnsFrame
    add_job_button: QtWidgets.QPushButton
    run_jobs_button: QtWidgets.QPushButton
    progress_bar: QtWidgets.QProgressBar

    jobs_started: QtCore.Signal = QtCore.Signal()
    jobs_finished: QtCore.Signal = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.project_root = None
        self.resolution = None
        self.running = False

        self._jobs_map: dict[JobWidget, QuantificationSettings] = {}
        self._progress = 0
        self._progress_step = 0

        progress_timer = QtCore.QTimer(self)
        progress_timer.timeout.connect(self.update_progress)
        self._progress_timer = progress_timer

        quantification_parameters_frame = QuantificationParametersFrame()
        quantification_parameters_frame.structures_frame.tag_holder_modified.connect(
            self.update_add_job_state
        )
        quantification_parameters_frame.setContentsMargins(
            1, quantification_parameters_frame.contentsMargins().top(), 1, 1
        )
        self.quantification_parameters_frame = quantification_parameters_frame

        add_job_button = QtWidgets.QPushButton("Add job")
        add_job_button.clicked.connect(self.queue_job)
        self.add_job_button = add_job_button

        jobs_frame = ColumnsFrame(
            title="Jobs", column_count=2, column_titles=("Slices", "Volumes")
        )
        jobs_frame.setContentsMargins(1, jobs_frame.contentsMargins().top(), 1, 1)
        self.jobs_frame = jobs_frame

        run_jobs_button = QtWidgets.QPushButton("Run jobs")
        run_jobs_button.clicked.connect(self.start_jobs)
        self.run_jobs_button = run_jobs_button

        progress_bar = QtWidgets.QProgressBar()
        self.progress_bar = progress_bar

        layout = QtWidgets.QGridLayout()
        layout.addWidget(quantification_parameters_frame, 0, 0)
        layout.addWidget(jobs_frame, 0, 1)
        layout.addWidget(add_job_button, 1, 0)
        layout.addWidget(run_jobs_button, 1, 1)
        layout.addWidget(progress_bar, 2, 0, 1, 2)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        self.setLayout(layout)

        self.update_add_job_state()

    def parse_project(self, path: Path, resolution: Resolution) -> None:
        self.project_root = path
        self.resolution = resolution

        self.quantification_parameters_frame.parse_project(path)

    def update_add_job_state(self) -> None:
        holder = (
            self.quantification_parameters_frame.structures_frame.structure_tag_holder
        )
        enabled = len(holder.get_tag_names()) > 0

        self.add_job_button.setEnabled(enabled)
        if enabled:
            self.add_job_button.setToolTip("")
        else:
            self.add_job_button.setToolTip("No structures selected.")

    def set_running_state(self, running: bool) -> None:
        self.running = running
        self.add_job_button.setEnabled(not running)
        self.run_jobs_button.setEnabled(not running)

    def reset(self) -> None:
        self.quantification_parameters_frame.reset()
        self._jobs_map.clear()

        self.jobs_frame.clear()

    @QtCore.Slot()
    def queue_job(self) -> None:
        frame = self.quantification_parameters_frame

        widget = JobWidget(
            frame.quantification_combo_box.currentText(),
            frame.directory_widget.currentText(),
            frame.structures_frame.structure_tag_holder.get_tag_names(),
        )
        self.jobs_frame.add_widget(
            widget, 1 if frame.run_on_volume_check_box.isChecked() else 0
        )

        directory_hash = Workspace.generate_directory_hash(
            frame.directory_widget.currentText()
        )
        self._jobs_map[widget] = QuantificationSettings(
            source_directory=Path(frame.directory_widget.currentText()),
            alignment_directory=unwrap(self.project_root) / directory_hash,
            resolution=unwrap(self.resolution),
            quantification=Quantification(frame.quantification_combo_box.currentText()),
            on_volume=frame.run_on_volume_check_box.isChecked(),
            structures=frame.structures_frame.structure_tag_holder.get_tag_names(),
            channel_regex=frame.channel_frame.regex,
            channel_substitution=frame.channel_frame.substitution,
        )

        widget.removal_requested.connect(lambda: self.pop_job(widget))

    @QtCore.Slot()
    def pop_job(self, widget: JobWidget, user_made: bool = True) -> None:
        if user_made and self.running:
            return

        layout = unwrap(self.jobs_frame.layout())
        layout.takeAt(layout.indexOf(widget))

        self._jobs_map.pop(widget)
        widget.deleteLater()

    @QtCore.Slot()
    def start_jobs(self) -> None:
        self._progress = 0
        self._progress_step = 0

        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(len(self._jobs_map))
        self.update_progress()
        self._progress_timer.start(500)

        self.jobs_started.emit()
        self._progress_timer.start()
        self.run_next_job()

    @QtCore.Slot()
    def run_next_job(self) -> None:
        try:
            widget, settings = next(iter(self._jobs_map.items()))
        except StopIteration:
            self.jobs_finished.emit()
            return

        thread = QuantificationThread(settings, self)
        thread.finished.connect(lambda: self.pop_job(widget, user_made=False))
        thread.finished.connect(self.increment_progress)
        thread.finished.connect(self.run_next_job)
        thread.finished.connect(thread.deleteLater)

        thread.start()

    @QtCore.Slot()
    def increment_progress(self) -> None:
        self._progress += 1

    @QtCore.Slot()
    def update_progress(self) -> None:
        in_progress = self._progress < self.progress_bar.maximum()

        self._progress_step = (self._progress_step + 1) % 3

        if in_progress:
            dots = "." * (self._progress_step + 1)
            message = f"Quantifying{dots} (%p%)"
        else:
            message = f"Finished"

        self.progress_bar.setValue(self._progress)
        self.progress_bar.setFormat(message)

        if not in_progress:
            self._progress_timer.stop()


class QuantificationParametersFrame(TitleFrame):
    project_root: Optional[Path]

    quantification_combo_box: QtWidgets.QComboBox
    directory_widget: ProjectDirectoriesComboBox
    run_on_volume_label: QtWidgets.QLabel
    run_on_volume_check_box: AnimatedCheckBox
    channel_frame: ChannelFrame
    structures_frame: StructureFrame

    def __init__(
        self,
        title: str = "Quantification parameters",
        bold: bool = True,
        italic: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(title, bold, italic, parent)

        self.project_root = None

        quantification_combo_box = QtWidgets.QComboBox()
        quantification_combo_box.addItems(
            [variant.display_value.capitalize() for variant in Quantification]
        )
        quantification_combo_box.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            quantification_combo_box.sizePolicy().verticalPolicy(),
        )
        self.quantification_combo_box = quantification_combo_box

        directory_widget = ProjectDirectoriesComboBox()
        directory_widget.currentTextChanged.connect(self.update_on_volume_state)
        directory_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            directory_widget.sizePolicy().verticalPolicy(),
        )
        self.directory_widget = directory_widget

        run_on_volume_label = QtWidgets.QLabel("Run on volume?")
        self.run_on_volume_label = run_on_volume_label

        run_on_volume_check_box = AnimatedCheckBox()
        run_on_volume_check_box.checkStateChanged.connect(
            lambda x: self.channel_frame.setEnabled(x != QtCore.Qt.CheckState.Checked)
        )
        self.run_on_volume_check_box = run_on_volume_check_box

        multi_channel_frame = ChannelFrame()
        self.channel_frame = multi_channel_frame

        structures_frame = StructureFrame()
        structures_frame.setContentsMargins(
            1, structures_frame.contentsMargins().top(), 1, 1
        )
        self.structures_frame = structures_frame

        layout = QtWidgets.QGridLayout()
        layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinimumSize)
        layout.addWidget(QtWidgets.QLabel("Quantification"), 0, 0)
        layout.addWidget(quantification_combo_box, 0, 1)
        layout.addWidget(QtWidgets.QLabel("Directory"), 1, 0)
        layout.addWidget(directory_widget, 1, 1)
        layout.addWidget(run_on_volume_label, 2, 0)
        layout.addWidget(
            run_on_volume_check_box, 2, 1, alignment=QtCore.Qt.AlignmentFlag.AlignRight
        )
        layout.addWidget(multi_channel_frame, 3, 0, 1, 2)
        layout.addWidget(structures_frame, 4, 0, 1, 2)
        layout.setHorizontalSpacing(30)
        self.setLayout(layout)

        self.update_on_volume_state()

    def parse_project(self, path: Path) -> None:
        self.project_root = path

        self.directory_widget.parse_project(path)

    def update_on_volume_state(self) -> None:
        if self.project_root is None:
            return

        alignment_directory = self.project_root / Workspace.generate_directory_hash(
            self.directory_widget.currentText()
        )
        interpolated_directory = alignment_directory / "volumes" / "interpolated"
        if (
            interpolated_directory.exists()
            and len(list(interpolated_directory.iterdir())) > 0
        ):
            self.run_on_volume_label.setEnabled(True)
            self.run_on_volume_check_box.setEnabled(True)
            self.run_on_volume_label.setToolTip("")
            self.run_on_volume_check_box.setToolTip("")
        else:
            self.run_on_volume_label.setEnabled(False)
            self.run_on_volume_check_box.setEnabled(False)
            self.run_on_volume_check_box.setChecked(False)
            self.run_on_volume_label.setToolTip(
                "No volume found for the current directory. "
                "Build one to allow quantification."
            )
            self.run_on_volume_check_box.setToolTip(
                "No volume found for the current directory. "
                "Build one to allow quantification."
            )

    def reset(self) -> None:
        self.project_root = None
        self.directory_widget.clear()


class ChannelFrame(TitleFrame):
    check_box: AnimatedCheckBox
    regex_line_edit: QtWidgets.QLineEdit
    substitution_line_edit: QtWidgets.QLineEdit

    def __init__(
        self,
        title: str = "Multichannel images",
        bold: bool = False,
        italic: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(title, bold, italic, parent)

        #
        check_box = AnimatedCheckBox()

        check_box.checkStateChanged.connect(
            lambda x: self.regex_line_edit.setEnabled(x == QtCore.Qt.CheckState.Checked)
        )
        check_box.checkStateChanged.connect(
            lambda x: self.substitution_line_edit.setEnabled(
                x == QtCore.Qt.CheckState.Checked
            )
        )

        self.check_box = check_box

        #
        # setFormAlignment doesn't work for right-aligned so make sub-layout
        check_box_layout = QtWidgets.QHBoxLayout()

        check_box_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        check_box_layout.addWidget(check_box)

        #
        regex_line_edit = QtWidgets.QLineEdit()

        regex_line_edit.setEnabled(False)

        self.regex_line_edit = regex_line_edit

        #
        substitution_line_edit = QtWidgets.QLineEdit()

        substitution_line_edit.setEnabled(False)

        self.substitution_line_edit = substitution_line_edit

        #
        layout = QtWidgets.QFormLayout()

        layout.addRow("Are images multichannel?", check_box_layout)
        layout.addRow("Channel regex", regex_line_edit)
        layout.addRow("Channel substitution", substitution_line_edit)

        self.setLayout(layout)

        #
        self.setContentsMargins(
            1, self.contentsMargins().top(), 1, self.contentsMargins().bottom()
        )

    @property
    def regex(self) -> str:
        regex = ""
        if self.regex_line_edit.isEnabled():
            regex = self.regex_line_edit.text()

        return regex

    @property
    def substitution(self) -> str:
        substitution = ""
        if self.substitution_line_edit.isEnabled():
            substitution = self.substitution_line_edit.text()

        return substitution


class ZStackFrame(TitleFrame):
    check_box: AnimatedCheckBox
    regex_line_edit: QtWidgets.QLineEdit
    spacing_line_edit: QtWidgets.QLineEdit

    def __init__(
        self,
        title: str = "Z-stacks",
        bold: bool = False,
        italic: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(title, bold, italic, parent)

        #
        check_box = AnimatedCheckBox()

        check_box.checkStateChanged.connect(
            lambda x: self.regex_line_edit.setEnabled(x == QtCore.Qt.CheckState.Checked)
        )
        check_box.checkStateChanged.connect(
            lambda x: self.spacing_line_edit.setEnabled(
                x == QtCore.Qt.CheckState.Checked
            )
        )

        self.check_box = check_box

        #
        # setFormAlignment doesn't work for right-aligned so make sub-layout
        check_box_layout = QtWidgets.QHBoxLayout()

        check_box_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        check_box_layout.addWidget(check_box)

        #
        regex_line_edit = QtWidgets.QLineEdit()
        regex_line_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        regex_line_edit.setEnabled(False)
        self.regex_line_edit = regex_line_edit

        #
        spacing_line_edit = QtWidgets.QLineEdit()
        spacing_line_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        spacing_line_edit.setValidator(QtGui.QIntValidator())
        spacing_line_edit.setEnabled(False)
        self.spacing_line_edit = spacing_line_edit

        #
        layout = QtWidgets.QFormLayout()

        layout.addRow("Are images Z-stacks?", check_box_layout)
        layout.addRow("Z-stack regex", regex_line_edit)
        layout.addRow("Spacing (μm)", spacing_line_edit)

        self.setLayout(layout)

        #
        self.setContentsMargins(
            1, self.contentsMargins().top(), 1, self.contentsMargins().bottom()
        )

    @property
    def regex(self) -> str:
        return self.regex_line_edit.text()

    @property
    def spacing(self) -> str:
        return self.spacing_line_edit.text()


class StructureFrame(TitleFrame):
    tag_holder_modified: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        title: str = "Structures",
        bold: bool = True,
        italic: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(title, bold, italic, parent)

        #
        pop_up = StructureFinderDialog(self)

        self.pop_up = pop_up

        #
        structures_button = QtWidgets.QPushButton("Add/remove structures")

        structures_button.clicked.connect(lambda: self.pop_up.resize(self.size()))
        structures_button.clicked.connect(self.pop_up.exec)

        self.structures_button = structures_button

        #
        structure_tag_holder = StructureTagHolderWidget()

        view = pop_up.finder_widget.tree_view
        view.item_checked.connect(structure_tag_holder.add_tag_from_index)
        view.item_checked.connect(lambda _: self.tag_holder_modified.emit())
        view.item_unchecked.connect(structure_tag_holder.remove_tag_from_index)
        view.item_unchecked.connect(lambda _: self.tag_holder_modified.emit())

        self.structure_tag_holder = structure_tag_holder

        #
        layout = QtWidgets.QGridLayout()

        layout.addWidget(structures_button, 0, 0, 1, -1)
        layout.addWidget(structure_tag_holder, 1, 0, 1, -1)

        self.setLayout(layout)


class JobWidget(QtWidgets.QFrame):
    removal_requested: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        quantification: str,
        directory: str,
        structures: list[str],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        quantification_label = CutOffLabel(quantification)
        palette = quantification_label.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Window,
            lua_aware_shift(palette.window().color(), 50),
        )
        quantification_label.setPalette(palette)
        self.setAutoFillBackground(True)
        quantification_label.setAutoFillBackground(True)
        quantification_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        directory_label = CutOffLabel(directory)

        structures_label = CutOffLabel(", ".join(structures))

        first_row_layout = QtWidgets.QHBoxLayout()
        first_row_layout.addWidget(QtWidgets.QWidget(), stretch=1)
        first_row_layout.addWidget(quantification_label, stretch=10)
        first_row_layout.addWidget(QtWidgets.QWidget(), stretch=1)
        first_row_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)

        close_button = HoverButton(
            icon_path=ICONS_ROOT / "close-square-line-icon.png", parent=self
        )
        close_button.clicked.connect(self.removal_requested.emit)
        close_button.setFixedSize(
            QtCore.QSize(
                quantification_label.sizeHint().height(),
                quantification_label.sizeHint().height(),
            )
        )
        close_button.setIconSize(close_button.size())
        self.close_button = close_button

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(first_row_layout)
        layout.addWidget(
            directory_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter
        )
        layout.addWidget(
            structures_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter
        )
        layout.setContentsMargins(5, 0, 5, 5)
        self.setLayout(layout)

        close_button.raise_()  # Ensure button is above any other widget

        palette = self.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Window,
            lua_aware_shift(palette.window().color(), 10),
        )
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)

        top_right = self.rect().topRight()
        top_right -= QtCore.QPoint(self.close_button.size().width() - 1, 0)
        self.close_button.setGeometry(
            top_right.x(),
            top_right.y(),
            self.close_button.size().width(),
            self.close_button.size().width(),
        )
