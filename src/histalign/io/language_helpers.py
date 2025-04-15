# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from collections.abc import Callable
from typing import Generic, Optional, TypeVar

T = TypeVar("T")
RT = TypeVar("RT")


class classproperty(Generic[T, RT]):
    """
    Class property attribute (read-only).

    Same usage as @property, but taking the class as the first argument.

        class C:
            @classproperty
            def x(cls):
                return 0

        print(C.x)    # 0
        print(C().x)  # 0

    Source:
        https://github.com/python/cpython/issues/89519#issuecomment-1397534245
    """

    def __init__(self, func: Callable[[type[T]], RT]) -> None:
        self.__wrapped__: Callable[[type[T]], RT] = func

    def __get__(self, instance: Optional[T], owner: Optional[type[T]] = None) -> RT:
        if owner is None:
            owner = type(instance)
        return self.__wrapped__(owner)
