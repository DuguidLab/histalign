from __future__ import annotations

from enum import Enum
import json
import logging
import shutil
from typing import Any, Optional

from pydantic import BaseModel, field_validator, ValidationError
from PySide6 import QtCore, QtGui, QtWidgets

from histalign.io import DATA_ROOT
from histalign.resources import RESOURCES_ROOT

DEFAULT_KEYMAP_CONFIG_PATH = RESOURCES_ROOT / "keymaps" / "default.json"
USER_KEYMAP_CONFIG_PATH = DATA_ROOT / "keymap.json"
if not USER_KEYMAP_CONFIG_PATH.exists():
    shutil.copy(DEFAULT_KEYMAP_CONFIG_PATH, USER_KEYMAP_CONFIG_PATH)

_module_logger = logging.getLogger(__name__)


class Shortcuts(Enum):
    NEW_PROJECT = "MenuBar.NewProject"
    OPEN_PROJECT = "MenuBar.OpenProject"
    SAVE_PROJECT = "MenuBar.SaveProject"
    CLOSE_PROJECT = "MenuBar.CloseProject"
    OPEN_IMAGES_FOLDER = "MenuBar.OpenImagesFolder"
    EXPORT_VOLUME = "MenuBar.ExportVolume"
    QUIT_APPLICATION = "MenuBar.QuitApplication"
    SAVE_ALIGNMENT = "ToolBar.SaveAlignment"
    LOAD_ALIGNMENT = "ToolBar.LoadAlignment"
    AUTO_CONTRAST = "ToolBar.AutoContrast"
    TOGGLE_GLOBAL_ALPHA = "ToolBar.ToggleGlobalAlpha"


class Keymap:
    _instance: Optional[Keymap] = None
    _config: _KeymapConfig

    def __new__(cls, *args, **kwargs) -> Keymap:
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
            cls._load_config()

        return cls._instance

    def __getitem__(self, item: Shortcuts) -> QtGui.QKeySequence:
        for entry in self._config.keymap:
            if item.value == entry.id:
                return entry.key_sequence

        raise KeyError

    def get(self, item: Shortcuts, default: Any) -> Any:
        try:
            return self.__getitem__(item)
        except KeyError:
            return default

    @classmethod
    def _load_config(cls) -> None:
        try:
            with open(USER_KEYMAP_CONFIG_PATH) as handle:
                cls._config = _KeymapConfig(**json.load(handle))
        except (FileNotFoundError, json.JSONDecodeError, ValidationError, ValueError):
            _module_logger.error(
                "Failed to parse keymap config, reverting to default keymap."
            )

            try:
                with open(DEFAULT_KEYMAP_CONFIG_PATH) as handle:
                    cls._config = _KeymapConfig(**json.load(handle))
            except (
                FileNotFoundError,
                json.JSONDecodeError,
                ValidationError,
                ValueError,
            ):
                _module_logger.critical(
                    "Could not load default keymap, terminating application."
                )

                app = QtWidgets.QApplication.instance()
                if app is None:
                    exit()

                app.quit()


class _KeymapConfig(BaseModel):
    keymap: list[_KeymapEntry]


class _KeymapEntry(BaseModel, arbitrary_types_allowed=True):
    id: str
    key_sequence: QtGui.QKeySequence

    @field_validator("key_sequence", mode="before")
    @classmethod
    def validate_key_sequence(cls, value: Any) -> QtGui.QKeySequence:
        key_sequence = QtGui.QKeySequence(value)

        if (
            key_sequence.matches(QtGui.QKeySequence(QtCore.Qt.Key.Key_unknown))
            != QtGui.QKeySequence.SequenceMatch.NoMatch
        ):
            raise ValueError(f"Could not parse key sequence '{value}' as a shortcut.")

        return key_sequence
