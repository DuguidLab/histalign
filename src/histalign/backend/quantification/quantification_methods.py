# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

import numpy as np


def compute_average_fluorescence(image: np.ndarray, mask: np.ndarray) -> float:
    # Avoid a RuntimeWarning when mask is empty
    if not mask.any():
        return 0.0

    return np.mean(image, where=mask > 0).astype(float)
