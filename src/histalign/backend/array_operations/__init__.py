# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

"""This module extends the functionality of NumPy with a few helper functions."""

import numpy as np


def safe_add_to_array(
    array: np.ndarray, value: int | float, inplace: bool = False
) -> np.ndarray:
    """Safely add a value to an array by clipping values, avoiding overflows.

    NumPy normally casts the result of the following operation:

    >>> array = np.array([250], dtype=np.uint8)
    >>> array + 1_000
    array([1250], dtype=uint16)

    However, it does not perform the cast if the value being added fits in the array's
    datatype. Meaning the following overflow occurs:

    >>> array = np.array([250], dtype=np.uint8)
    >>> array + 10
    array([4], dtype=uint8)

    Additionally, it does not perform the cast when using the shorthand (i.e., +=).
    This function aims to avoid any kind of ambiguity and will always return an array of
    the same type as `array` while preventing overflows during addition, instead
    clipping any value that would overflow to the maximum allowed value by `array`'s
    datatype.

    Args:
        array (np.ndarray): Array whose values to add to.
        value (int | float): Value to add from `array`.
        inplace (bool, optional): Whether to carry out the addition in place.

    Returns:
        np.ndarray: The result of the addition. If `inplace` is True, returns a
                    reference to `array`. Otherwise, this is a completely new array.
    """
    if inplace:
        target_array = array
    else:
        target_array = array.copy()

    maximum = get_dtype_maximum(target_array.dtype)
    threshold = maximum - value

    target_array[target_array >= threshold] = maximum
    target_array[target_array < threshold] += value

    return target_array


def safe_subtract_from_array(
    array: np.ndarray, value: int | float, inplace: bool = False
) -> np.ndarray:
    """Safely subtract a value from an array by clipping values, avoiding underflows.

    NumPy normally casts the result of the following operation:

    >>> array = np.array([4], dtype=np.uint8)
    >>> array - 1_000
    array([64540], dtype=uint16)

    However, it does not perform the cast if the value being added fits in the array's
    datatype. Meaning the following underflow occurs:

    >>> array = np.array([4], dtype=np.uint8)
    >>> array - 10
    array([250], dtype=uint8)

    Additionally, it does not perform the cast when using the shorthand (i.e., -=).
    This function aims to avoid any kind of ambiguity and will always return an array of
    the same type as `array` while preventing underflows during subtraction, instead
    clipping any value that would underflow to the minimum allowed value by `array`'s
    datatype.

    Args:
        array (np.ndarray): Array whose values to subtract from.
        value (int | float): Value to subtract from `array`.
        inplace (bool, optional): Whether to carry out the subtraction in place.

    Returns:
        np.ndarray: The result of the subtraction. If `inplace` is True, returns a
                    reference to `array`. Otherwise, this is a completely new array.
    """
    if inplace:
        target_array = array
    else:
        target_array = array.copy()

    minimum = get_dtype_minimum(target_array.dtype)
    threshold = value + minimum

    target_array[target_array <= threshold] = minimum
    target_array[target_array > threshold] -= value

    return target_array


def get_dtype_maximum(dtype: np.dtype) -> int | float:
    """Return the maximum value allowed for the given numpy datatype.

    Args:
        dtype (np.dtype): Datatype whose minimum to find.

    Returns:
        int | float: The maximum value allowed for `dtype`.
    """
    try:
        maximum = np.iinfo(dtype).max
    except ValueError:
        maximum = float(np.finfo(dtype).max)

    return maximum


def get_dtype_minimum(dtype: np.dtype) -> int | float:
    """Return the minimum value allowed for the given numpy datatype.

    Args:
        dtype (np.dtype): Datatype whose minimum to find.

    Returns:
        int | float: The minimum value allowed for `dtype`.
    """
    try:
        minimum = np.iinfo(dtype).min
    except ValueError:
        minimum = float(np.finfo(dtype).min)

    return minimum
