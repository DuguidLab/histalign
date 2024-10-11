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

        self.offset_spin_box.setMinimum(-axis_length // 2)
        self.offset_spin_box.setMaximum(axis_length // 2 + (axis_length % 2 != 0) - 1)

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

    rotation_spin_box: QtWidgets.QSpinBox
    translation_x_spin_box: QtWidgets.QSpinBox
    translation_y_spin_box: QtWidgets.QSpinBox
    scale_x_spin_box: QtWidgets.QDoubleSpinBox
    scale_y_spin_box: QtWidgets.QDoubleSpinBox
    shear_x_spin_box: QtWidgets.QDoubleSpinBox
    shear_y_spin_box: QtWidgets.QDoubleSpinBox

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

        rotation_spin_box = QtWidgets.QSpinBox()
        rotation_spin_box.setMinimum(-90)
        rotation_spin_box.setMaximum(90)
        rotation_spin_box.valueChanged.connect(self.update_rotation)
        self.rotation_spin_box = rotation_spin_box

        translation_x_spin_box = QtWidgets.QSpinBox()
        translation_x_spin_box.setMinimum(-500)
        translation_x_spin_box.setMaximum(500)
        translation_x_spin_box.valueChanged.connect(self.update_translation_x)
        translation_x_spin_box.installEventFilter(self)
        self.translation_x_spin_box = translation_x_spin_box

        translation_y_spin_box = QtWidgets.QSpinBox()
        translation_y_spin_box.setMinimum(-500)
        translation_y_spin_box.setMaximum(500)
        translation_y_spin_box.valueChanged.connect(self.update_translation_y)
        translation_y_spin_box.installEventFilter(self)
        self.translation_y_spin_box = translation_y_spin_box

        scale_x_spin_box = QtWidgets.QDoubleSpinBox()
        scale_x_spin_box.setMinimum(0.01)
        scale_x_spin_box.setMaximum(3.0)
        scale_x_spin_box.setValue(1.0)
        scale_x_spin_box.setSingleStep(0.01)
        scale_x_spin_box.valueChanged.connect(self.update_scale_x)
        self.scale_x_spin_box = scale_x_spin_box

        scale_y_spin_box = QtWidgets.QDoubleSpinBox()
        scale_y_spin_box.setMinimum(0.01)
        scale_y_spin_box.setMaximum(3.0)
        scale_y_spin_box.setValue(1.0)
        scale_y_spin_box.setSingleStep(0.01)
        scale_y_spin_box.valueChanged.connect(self.update_scale_y)
        self.scale_y_spin_box = scale_y_spin_box

        shear_x_spin_box = QtWidgets.QDoubleSpinBox()
        shear_x_spin_box.setMinimum(-1.0)
        shear_x_spin_box.setMaximum(1.0)
        shear_x_spin_box.setValue(0.0)
        shear_x_spin_box.setSingleStep(0.01)
        shear_x_spin_box.valueChanged.connect(self.update_shear_x)
        self.shear_x_spin_box = shear_x_spin_box

        shear_y_spin_box = QtWidgets.QDoubleSpinBox()
        shear_y_spin_box.setMinimum(-1.0)
        shear_y_spin_box.setMaximum(1.0)
        shear_y_spin_box.setValue(0.0)
        shear_y_spin_box.setSingleStep(0.01)
        shear_y_spin_box.valueChanged.connect(self.update_shear_y)
        self.shear_y_spin_box = shear_y_spin_box

        layout = QtWidgets.QFormLayout()
        layout.addRow(title)
        layout.addRow(separator)
        layout.addRow("Rotation", self.rotation_spin_box)
        layout.addRow("X Translation", self.translation_x_spin_box)
        layout.addRow("Y Translation", self.translation_y_spin_box)
        layout.addRow("X Scale", self.scale_x_spin_box)
        layout.addRow("Y Scale", self.scale_y_spin_box)
        layout.addRow("X Shear", self.shear_x_spin_box)
        layout.addRow("Y Shear", self.shear_y_spin_box)

        self.setLayout(layout)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if not watched.isEnabled():
            return super().eventFilter(watched, event)

        match event.type():
            case QtCore.QEvent.Type.Wheel:
                if event.angleDelta().y() > 0:  # Scroll up
                    watched.setValue(watched.value() + 5 * watched.singleStep())
                elif event.angleDelta().y() < 0:  # Scroll down
                    watched.setValue(watched.value() - 5 * watched.singleStep())
                else:  # Could be horizontal scrolling
                    return super().eventFilter(watched, event)

                # Reproduce selection behaviour as it is with up/down buttons
                watched.lineEdit().setSelection(
                    len(watched.lineEdit().text()), -watched.lineEdit().maxLength()
                )
            case _:
                return super().eventFilter(watched, event)

        return True

    def reload_settings(self) -> None:
        self.rotation_spin_box.setValue(self.settings.rotation)
        self.translation_x_spin_box.setValue(self.settings.translation_x)
        self.translation_y_spin_box.setValue(self.settings.translation_y)
        self.scale_x_spin_box.setValue(self.settings.scale_x)
        self.scale_y_spin_box.setValue(self.settings.scale_y)
        self.shear_x_spin_box.setValue(self.settings.shear_x)
        self.shear_y_spin_box.setValue(self.settings.shear_y)

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
        self.values_changed.emit()

    @QtCore.Slot()
    def update_scale_y(self, new_value: float) -> None:
        self.settings.scale_y = round(new_value, 2)
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
        self.rotation_spin_box.setValue(0)
        self.translation_x_spin_box.setValue(0)
        self.translation_y_spin_box.setValue(0)
        self.scale_x_spin_box.setValue(1.0)
        self.scale_y_spin_box.setValue(1.0)
        self.shear_x_spin_box.setValue(0.0)
        self.shear_y_spin_box.setValue(0.0)
        self.blockSignals(False)

        self.values_changed.emit()


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
