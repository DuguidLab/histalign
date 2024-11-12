# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from histalign.backend.models import HistologySettings, Orientation, VolumeSettings


class VolumeSettingsWidget(QtWidgets.QWidget):
    settings: Optional[VolumeSettings] = None

    offset_spin_box: QtWidgets.QSpinBox
    pitch_spin_box: QtWidgets.QSpinBox
    yaw_spin_box: QtWidgets.QSpinBox

    values_changed: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        title_font = QtGui.QFont()
        title_font.setBold(True)
        title = QtWidgets.QLabel(text="Atlas Volume Settings", font=title_font)

        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)

        #
        offset_spin_box = QtWidgets.QSpinBox()
        offset_spin_box.valueChanged.connect(self.update_offset)
        self.offset_spin_box = offset_spin_box

        #
        pitch_spin_box = QtWidgets.QSpinBox()
        pitch_spin_box.setMinimum(-90)
        pitch_spin_box.setMaximum(90)
        pitch_spin_box.valueChanged.connect(self.update_pitch)
        self.pitch_spin_box = pitch_spin_box

        #
        yaw_spin_box = QtWidgets.QSpinBox()
        yaw_spin_box.setMinimum(-90)
        yaw_spin_box.setMaximum(90)
        yaw_spin_box.valueChanged.connect(self.update_yaw)
        self.yaw_spin_box = yaw_spin_box

        #
        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow(title)
        layout.addRow(separator)
        layout.addRow("Offset", self.offset_spin_box)
        layout.addRow("Pitch", self.pitch_spin_box)
        layout.addRow("Yaw", self.yaw_spin_box)

        self.setLayout(layout)

    def update_offset_spin_box_limits(self) -> None:
        match self.settings.orientation:
            case Orientation.CORONAL:
                axis_length = self.settings.shape[0]
            case Orientation.HORIZONTAL:
                axis_length = self.settings.shape[1]
            case Orientation.SAGITTAL:
                axis_length = self.settings.shape[2]
            case _:
                # Should be impossible thanks to pydantic
                raise Exception("Panic: assert not reached")

        self.offset_spin_box.setMinimum(-axis_length // 2 + (axis_length % 2 == 0))
        self.offset_spin_box.setMaximum(axis_length // 2)

    def reload_settings(self) -> None:
        self.offset_spin_box.setValue(self.settings.offset)
        self.pitch_spin_box.setValue(self.settings.pitch)
        self.yaw_spin_box.setValue(self.settings.yaw)

    @QtCore.Slot()
    def update_offset(self, new_offset: int) -> None:
        self.settings.offset = new_offset
        self.values_changed.emit()

    @QtCore.Slot()
    def update_pitch(self, new_pitch: int) -> None:
        self.settings.pitch = new_pitch
        self.values_changed.emit()

    @QtCore.Slot()
    def update_yaw(self, new_yaw: int) -> None:
        self.settings.yaw = new_yaw
        self.values_changed.emit()

    @QtCore.Slot()
    def reset_to_defaults(self) -> None:
        self.blockSignals(True)  # Avoid notifying for every value reset
        self.offset_spin_box.setValue(0)
        self.pitch_spin_box.setValue(0)
        self.yaw_spin_box.setValue(0)
        self.blockSignals(False)

        self.values_changed.emit()


class HistologySettingsWidget(QtWidgets.QWidget):
    settings: Optional[HistologySettings] = None
    scaling_linked: bool = True
    scaling_ratio: float = 1.0

    rotation_spin_box: QtWidgets.QDoubleSpinBox
    translation_x_spin_box: QtWidgets.QSpinBox
    translation_y_spin_box: QtWidgets.QSpinBox
    scale_x_spin_box: QtWidgets.QDoubleSpinBox
    scale_y_spin_box: QtWidgets.QDoubleSpinBox
    shear_x_spin_box: QtWidgets.QDoubleSpinBox
    shear_y_spin_box: QtWidgets.QDoubleSpinBox
    scale_link_button = QtWidgets.QPushButton

    values_changed: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        title_font = QtGui.QFont()
        title_font.setBold(True)
        title = QtWidgets.QLabel(text="Histological Slice Settings", font=title_font)

        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)

        rotation_spin_box = QtWidgets.QDoubleSpinBox()
        rotation_spin_box.setMinimum(-90.0)
        rotation_spin_box.setMaximum(90.0)
        rotation_spin_box.setSingleStep(0.1)
        rotation_spin_box.valueChanged.connect(self.update_rotation)
        rotation_spin_box.installEventFilter(self)
        self.rotation_spin_box = rotation_spin_box

        translation_x_spin_box = QtWidgets.QSpinBox()
        translation_x_spin_box.setMinimum(-5000)
        translation_x_spin_box.setMaximum(5000)
        translation_x_spin_box.valueChanged.connect(self.update_translation_x)
        translation_x_spin_box.installEventFilter(self)
        self.translation_x_spin_box = translation_x_spin_box

        translation_y_spin_box = QtWidgets.QSpinBox()
        translation_y_spin_box.setMinimum(-5000)
        translation_y_spin_box.setMaximum(5000)
        translation_y_spin_box.valueChanged.connect(self.update_translation_y)
        translation_y_spin_box.installEventFilter(self)
        self.translation_y_spin_box = translation_y_spin_box

        scale_x_spin_box = QtWidgets.QDoubleSpinBox()
        scale_x_spin_box.setMinimum(0.01)
        scale_x_spin_box.setMaximum(3.0)
        scale_x_spin_box.setValue(1.0)
        scale_x_spin_box.setSingleStep(0.01)
        scale_x_spin_box.valueChanged.connect(self.update_scale_x)
        scale_x_spin_box.installEventFilter(self)
        self.scale_x_spin_box = scale_x_spin_box

        scale_y_spin_box = QtWidgets.QDoubleSpinBox()
        scale_y_spin_box.setMinimum(0.01)
        scale_y_spin_box.setMaximum(3.0)
        scale_y_spin_box.setValue(1.0)
        scale_y_spin_box.setSingleStep(0.01)
        scale_y_spin_box.valueChanged.connect(self.update_scale_y)
        scale_y_spin_box.installEventFilter(self)
        self.scale_y_spin_box = scale_y_spin_box

        shear_x_spin_box = QtWidgets.QDoubleSpinBox()
        shear_x_spin_box.setMinimum(-1.0)
        shear_x_spin_box.setMaximum(1.0)
        shear_x_spin_box.setValue(0.0)
        shear_x_spin_box.setSingleStep(0.01)
        shear_x_spin_box.valueChanged.connect(self.update_shear_x)
        shear_x_spin_box.installEventFilter(self)
        self.shear_x_spin_box = shear_x_spin_box

        shear_y_spin_box = QtWidgets.QDoubleSpinBox()
        shear_y_spin_box.setMinimum(-1.0)
        shear_y_spin_box.setMaximum(1.0)
        shear_y_spin_box.setValue(0.0)
        shear_y_spin_box.setSingleStep(0.01)
        shear_y_spin_box.valueChanged.connect(self.update_shear_y)
        shear_y_spin_box.installEventFilter(self)
        self.shear_y_spin_box = shear_y_spin_box

        #
        scale_link_button = QtWidgets.QPushButton()

        scale_link_button.clicked.connect(self.toggle_scale_link)

        scale_link_button.setIcon(QtGui.QIcon("resources/icons/link-icon.png"))

        self.scale_link_button = scale_link_button

        #
        scale_link_layout = QtWidgets.QHBoxLayout()

        scale_link_layout.addWidget(
            scale_link_button, alignment=QtCore.Qt.AlignmentFlag.AlignRight
        )

        #
        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow(title)
        layout.addRow(separator)
        layout.addRow("Rotation", self.rotation_spin_box)
        layout.addRow("X Translation", self.translation_x_spin_box)
        layout.addRow("Y Translation", self.translation_y_spin_box)
        layout.addRow("X Scale", self.scale_x_spin_box)
        layout.addRow(scale_link_layout)
        layout.addRow("Y Scale", self.scale_y_spin_box)
        layout.addRow("X Shear", self.shear_x_spin_box)
        layout.addRow("Y Shear", self.shear_y_spin_box)

        self.setLayout(layout)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if not watched.isEnabled():
            return super().eventFilter(watched, event)

        modified = False
        match event.type():
            case QtCore.QEvent.Type.KeyPress:
                combination = event.keyCombination()
                if combination.key() == QtCore.Qt.Key.Key_Up:
                    direction_multiplier = 1
                elif combination.key() == QtCore.Qt.Key.Key_Down:
                    direction_multiplier = -1
                else:
                    return super().eventFilter(watched, event)

                if (
                    combination.keyboardModifiers()
                    == QtCore.Qt.KeyboardModifier.ShiftModifier
                ):
                    modified = True
                elif (
                    combination.keyboardModifiers()
                    != QtCore.Qt.KeyboardModifier.NoModifier
                ):
                    # Drop Qt's default handling of combinations
                    return True
            case QtCore.QEvent.Type.Wheel:
                modified = True
                if event.angleDelta().y() > 0:  # Scroll up
                    direction_multiplier = 1
                elif event.angleDelta().y() < 0:  # Scroll down
                    direction_multiplier = -1
                else:  # Could be horizontal scrolling
                    return super().eventFilter(watched, event)
            case _:
                return super().eventFilter(watched, event)

        step_size = watched.singleStep()
        if modified:
            step_size *= 5

        watched.setValue(watched.value() + direction_multiplier * step_size)

        # Reproduce selection behaviour as it is with up/down buttons
        watched.lineEdit().setSelection(
            len(watched.lineEdit().text()), -watched.lineEdit().maxLength()
        )

        return True

    def reload_settings(self) -> None:
        self.rotation_spin_box.setValue(self.settings.rotation)
        self.translation_x_spin_box.setValue(self.settings.translation_x)
        self.translation_y_spin_box.setValue(self.settings.translation_y)
        scaling_linked = self.scaling_linked
        if scaling_linked:
            self.toggle_scale_link()
        self.scale_x_spin_box.setValue(self.settings.scale_x)
        self.scale_y_spin_box.setValue(self.settings.scale_y)
        if scaling_linked:
            self.toggle_scale_link()
        self.shear_x_spin_box.setValue(self.settings.shear_x)
        self.shear_y_spin_box.setValue(self.settings.shear_y)

    def compute_scaling_ratio(self) -> None:
        self.scaling_ratio = self.settings.scale_x / self.settings.scale_y

    @QtCore.Slot()
    def update_rotation(self, new_angle: int) -> None:
        self.settings.rotation = new_angle
        self.values_changed.emit()

    @QtCore.Slot()
    def update_translation_x(self, new_value: int) -> None:
        self.settings.translation_x = new_value
        self.values_changed.emit()

    @QtCore.Slot()
    def update_translation_y(self, new_value: int) -> None:
        self.settings.translation_y = new_value
        self.values_changed.emit()

    @QtCore.Slot()
    def update_scale_x(self, new_value: float) -> None:
        self.settings.scale_x = round(new_value, 2)

        if self.scaling_linked:
            self.settings.scale_y = new_value / self.scaling_ratio
            self.scale_y_spin_box.setValue(self.settings.scale_y)
        else:
            self.compute_scaling_ratio()

        self.values_changed.emit()

    @QtCore.Slot()
    def update_scale_y(self, new_value: float) -> None:
        self.settings.scale_y = round(new_value, 2)

        if self.scaling_linked:
            self.settings.scale_x = new_value * self.scaling_ratio
            self.scale_x_spin_box.setValue(self.settings.scale_x)
        else:
            self.compute_scaling_ratio()

        self.values_changed.emit()

    @QtCore.Slot()
    def update_shear_x(self, new_value: float) -> None:
        self.settings.shear_x = round(new_value, 2)
        self.values_changed.emit()

    @QtCore.Slot()
    def update_shear_y(self, new_value: float) -> None:
        self.settings.shear_y = round(new_value, 2)
        self.values_changed.emit()

    @QtCore.Slot()
    def reset_to_defaults(self) -> None:
        self.blockSignals(True)  # Avoid notifying for every value reset
        self.rotation_spin_box.setValue(0.0)
        self.translation_x_spin_box.setValue(0)
        self.translation_y_spin_box.setValue(0)
        scaling_linked = self.scaling_linked
        if scaling_linked:
            self.toggle_scale_link()
        self.scale_x_spin_box.setValue(1.0)
        self.scale_y_spin_box.setValue(1.0)
        if scaling_linked:
            self.toggle_scale_link()
        self.scaling_linked = self.scaling_linked
        self.shear_x_spin_box.setValue(0.0)
        self.shear_y_spin_box.setValue(0.0)
        self.blockSignals(False)

        self.values_changed.emit()

    @QtCore.Slot()
    def toggle_scale_link(self) -> None:
        self.scaling_linked = not self.scaling_linked

        if self.scaling_linked:
            self.scale_link_button.setIcon(QtGui.QIcon("resources/icons/link-icon.png"))
        else:
            self.scale_link_button.setIcon(
                QtGui.QIcon("resources/icons/broken-link-icon.png")
            )

        self.scale_link_button.update()

    @QtCore.Slot()
    def handle_outside_zoom(self, steps: int) -> None:
        scaling_linked = self.scaling_linked
        if not scaling_linked:
            self.toggle_scale_link()

        spin_box = (
            self.scale_x_spin_box
            if self.scale_x_spin_box.value() > self.scale_y_spin_box.value()
            else self.scale_y_spin_box
        )

        spin_box.setValue(spin_box.value() + steps * spin_box.singleStep())

        if not scaling_linked:
            self.toggle_scale_link()

    @QtCore.Slot()
    def handle_outside_translation(self, translation: QtCore.QPoint) -> None:
        self.translation_x_spin_box.setValue(
            self.translation_x_spin_box.value() + translation.x()
        )
        self.translation_y_spin_box.setValue(
            self.translation_y_spin_box.value() + translation.y()
        )


class SettingsWidget(QtWidgets.QWidget):
    histology_settings_widget: HistologySettingsWidget
    volume_settings_widget: VolumeSettingsWidget

    def __init__(
        self,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)

        #
        volume_settings_widget = VolumeSettingsWidget()

        self.volume_settings_widget = volume_settings_widget

        #
        histology_settings_widget = HistologySettingsWidget()

        self.histology_settings_widget = histology_settings_widget

        #
        layout = QtWidgets.QVBoxLayout()

        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self.histology_settings_widget)
        layout.addWidget(self.volume_settings_widget)

        self.setLayout(layout)

    def reload_settings(self) -> None:
        self.volume_settings_widget.reload_settings()
        self.histology_settings_widget.reload_settings()
