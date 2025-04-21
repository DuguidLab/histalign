# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging

import numpy as np

_module_logger = logging.getLogger(__name__)


def quantify_average_fluorescence(array: np.ndarray, mask: np.ndarray) -> float:
    if not mask.any():
        return 0.0

    return np.mean(array, where=mask > 0).astype(float)


def quantify_cell_count(array: np.ndarray, mask: np.ndarray) -> int:
    _module_logger.warning("quantify_cell_count: NotImplementedError")
    return -1
