# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import numpy as np


def get_average_fluorescence(image: np.ndarray, mask: np.ndarray) -> float:
    return np.mean(image, where=mask > 0)
