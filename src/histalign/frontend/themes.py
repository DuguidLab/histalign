# SPDX-FileCopyrightText: 2024-present Olivier Delrée <olivierdelree@protonmail.com>
#
# SPDX-License-Identifier: MIT

from PySide6.QtGui import QColor, QPalette


def build_light_theme() -> QPalette:
    theme = QPalette()

    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText, QColor(0, 0, 0)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.WindowText, QColor(0, 0, 0)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
        QColor(190, 190, 190),
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Button, QColor(239, 239, 239)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Button, QColor(239, 239, 239)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(239, 239, 239)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Light, QColor(255, 255, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Light, QColor(255, 255, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Light, QColor(255, 255, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Midlight, QColor(202, 202, 202)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Midlight, QColor(202, 202, 202)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Midlight, QColor(202, 202, 202)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Dark, QColor(159, 159, 159)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Dark, QColor(159, 159, 159)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Dark, QColor(190, 190, 190)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Mid, QColor(184, 184, 184)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Mid, QColor(184, 184, 184)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Mid, QColor(184, 184, 184)
    )
    theme.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Text, QColor(0, 0, 0))
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, QColor(0, 0, 0)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(190, 190, 190)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.BrightText, QColor(255, 255, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.BrightText,
        QColor(255, 255, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.BrightText,
        QColor(255, 255, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, QColor(0, 0, 0)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.ButtonText, QColor(0, 0, 0)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(190, 190, 190),
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Base, QColor(255, 255, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Base, QColor(255, 255, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(239, 239, 239)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Window, QColor(239, 239, 239)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Window, QColor(239, 239, 239)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, QColor(239, 239, 239)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Shadow, QColor(118, 118, 118)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Shadow, QColor(118, 118, 118)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Shadow, QColor(177, 177, 177)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, QColor(48, 140, 198)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor(48, 140, 198)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Highlight,
        QColor(145, 145, 145),
    )
    theme.setColor(
        QPalette.ColorGroup.Active,
        QPalette.ColorRole.HighlightedText,
        QColor(255, 255, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.HighlightedText,
        QColor(255, 255, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.HighlightedText,
        QColor(255, 255, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Link, QColor(0, 0, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Link, QColor(0, 0, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Link, QColor(0, 0, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.LinkVisited, QColor(255, 0, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.LinkVisited,
        QColor(255, 0, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.LinkVisited,
        QColor(255, 0, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Active,
        QPalette.ColorRole.AlternateBase,
        QColor(247, 247, 247),
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.AlternateBase,
        QColor(247, 247, 247),
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.AlternateBase,
        QColor(247, 247, 247),
    )
    theme.setColor(
        QPalette.ColorGroup.Active,
        QPalette.ColorRole.ToolTipBase,
        QColor(255, 255, 220),
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.ToolTipBase,
        QColor(255, 255, 220),
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ToolTipBase,
        QColor(255, 255, 220),
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.ToolTipText, QColor(0, 0, 0)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipText, QColor(0, 0, 0)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipText, QColor(0, 0, 0)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.PlaceholderText, QColor(0, 0, 0)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.PlaceholderText,
        QColor(0, 0, 0),
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.PlaceholderText,
        QColor(0, 0, 0),
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Accent, QColor(48, 140, 198)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Accent, QColor(48, 140, 198)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Accent, QColor(145, 145, 145)
    )

    return theme


def build_dark_theme() -> QPalette:
    theme = QPalette()

    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText, QColor(255, 255, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.WindowText,
        QColor(255, 255, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
        QColor(157, 157, 157),
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Button, QColor(60, 60, 60)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Button, QColor(60, 60, 60)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(60, 60, 60)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Light, QColor(120, 120, 120)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Light, QColor(120, 120, 120)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Light, QColor(120, 120, 120)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Midlight, QColor(90, 90, 90)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Midlight, QColor(90, 90, 90)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Midlight, QColor(90, 90, 90)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Dark, QColor(30, 30, 30)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Dark, QColor(30, 30, 30)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Dark, QColor(30, 30, 30)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Mid, QColor(40, 40, 40)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Mid, QColor(40, 40, 40)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Mid, QColor(40, 40, 40)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Text, QColor(255, 255, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, QColor(255, 255, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(157, 157, 157)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.BrightText, QColor(153, 235, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.BrightText,
        QColor(153, 235, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.BrightText,
        QColor(153, 235, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, QColor(255, 255, 255)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.ButtonText,
        QColor(255, 255, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(157, 157, 157),
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Base, QColor(45, 45, 45)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Base, QColor(45, 45, 45)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(30, 30, 30)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Window, QColor(30, 30, 30)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Window, QColor(30, 30, 30)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, QColor(30, 30, 30)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Shadow, QColor(0, 0, 0)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Shadow, QColor(0, 0, 0)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Shadow, QColor(0, 0, 0)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, QColor(0, 120, 212)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor(30, 30, 30)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(0, 120, 212)
    )
    theme.setColor(
        QPalette.ColorGroup.Active,
        QPalette.ColorRole.HighlightedText,
        QColor(255, 255, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.HighlightedText,
        QColor(255, 255, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.HighlightedText,
        QColor(255, 255, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Link, QColor(0, 120, 212)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Link, QColor(0, 120, 212)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Link, QColor(48, 140, 198)
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.LinkVisited, QColor(0, 26, 104)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.LinkVisited, QColor(0, 26, 104)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.LinkVisited,
        QColor(255, 0, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.AlternateBase, QColor(0, 26, 104)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.AlternateBase,
        QColor(0, 26, 104),
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.AlternateBase,
        QColor(52, 52, 52),
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.ToolTipBase, QColor(60, 60, 60)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipBase, QColor(60, 60, 60)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ToolTipBase,
        QColor(255, 255, 220),
    )
    theme.setColor(
        QPalette.ColorGroup.Active,
        QPalette.ColorRole.ToolTipText,
        QColor(212, 212, 212),
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.ToolTipText,
        QColor(212, 212, 212),
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipText, QColor(0, 0, 0)
    )
    theme.setColor(
        QPalette.ColorGroup.Active,
        QPalette.ColorRole.PlaceholderText,
        QColor(255, 255, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.PlaceholderText,
        QColor(255, 255, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.PlaceholderText,
        QColor(255, 255, 255),
    )
    theme.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Accent, QColor(0, 120, 212)
    )
    theme.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Accent, QColor(30, 30, 30)
    )
    theme.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Accent, QColor(157, 157, 157)
    )

    return theme


LIGHT_THEME: QPalette = build_light_theme()
DARK_THEME: QPalette = build_dark_theme()


if __name__ == "__main__":
    print("hello")
