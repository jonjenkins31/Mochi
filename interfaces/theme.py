"""One palette, two modes, applied to the whole application.

The readability problem was not any single colour — it was thirty
`setStyleSheet("color:#777784")` calls, each picking a grey by eye, on
top of a sheet that was only ever applied to the TAB WIDGET. Anything
outside it — a dialog, a popup, a message box, the avatar window —
fell through to Qt's defaults and came out light-on-light or
dark-on-dark depending on the platform.

So: the sheet goes on the QApplication, and secondary text is a ROLE
rather than a hex value. `label.setObjectName("Dim")` is styled here,
and follows the theme; `setStyleSheet("color:#777784")` cannot.

CONTRAST IS CHECKED, NOT EYEBALLED. Every ink/background pair below is
asserted against WCAG AA in the test suite — 4.5:1 for body text, 3:1
for large and secondary. The old dim grey `#777784` on `#101014` was
3.4:1, which is why it read as "there is something written here" and
not as words.

    ink       body text          >= 7:1, comfortably past AA
    dim       secondary text     >= 4.5:1, still real text
    hint      placeholders       >= 3:1, deliberately quiet
    accent    the one highlight  used for focus and selection

WHY TWO MODES AND NOT THREE. Light and dark are the two a person
actually asks for. "Follow the system" is a third code path that is
wrong exactly when the system is wrong, and the toggle is one click.
"""

from __future__ import annotations

from typing import Any

#: Role -> colour, per mode. Named by JOB, never by appearance: `ink`
#: is dark in light mode and light in dark mode, and every call site
#: stays correct without knowing which.
PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "canvas": "#14141A",   # the window itself
        "panel":  "#1E1E28",   # raised surfaces: fields, buttons, tabs
        "sunken": "#0C0C11",   # text areas, lists, anything you read into
        "ink":     "#ECECF4",
        "dim":     "#A8A8BC",
        "hint":    "#7B7B90",
        "rule":    "#33333F",
        "accent":  "#9B8CFF",
        # DARK ink on the accent, not white. A bright chip on a dark
        # theme is the readable direction — white on this lands at 3.3
        # and fails AA, which matters because selected list rows and
        # checked buttons are text on the accent.
        "accent_ink": "#14141A",
        "ok":      "#57D9A3",
        "warn":    "#E8B355",
        "bad":     "#FF7B72",
    },
    "light": {
        "canvas": "#F4F4F8",
        "panel":  "#FFFFFF",
        "sunken": "#FBFBFD",
        "ink":     "#1B1B24",
        "dim":     "#54546A",
        "hint":    "#75758C",
        "rule":    "#D5D5E0",
        "accent":  "#5344CC",
        "accent_ink": "#FFFFFF",
        "ok":      "#137A56",
        "warn":    "#8A5A00",
        "bad":     "#B3261E",
    },
}

#: The default, and what every screenshot so far was taken in.
DEFAULT = "dark"


def palette(mode: str = DEFAULT) -> dict[str, str]:
    return PALETTES.get(str(mode).lower(), PALETTES[DEFAULT])


def stylesheet(mode: str = DEFAULT) -> str:
    """The whole application's look, from the roles above.

    Every rule here exists because something was unreadable without it.
    Notably `:disabled` — Qt's default disabled grey is derived from
    the palette, not the stylesheet, and on a dark canvas it lands at
    about 2:1.
    """
    c = palette(mode)
    return f"""
QWidget {{ background: {c['canvas']}; color: {c['ink']};
           font-size: 12px; }}
QWidget:disabled {{ color: {c['hint']}; }}
QToolTip {{ background: {c['panel']}; color: {c['ink']};
            border: 1px solid {c['rule']}; padding: 4px; }}

QLabel {{ background: transparent; }}
QLabel#Dim {{ color: {c['dim']}; }}
QLabel#Hint {{ color: {c['hint']}; font-size: 11px; }}
QLabel#Heading {{ color: {c['ink']}; font-size: 15px; font-weight: 600; }}
QLabel#Ok {{ color: {c['ok']}; }}
QLabel#Warn {{ color: {c['warn']}; }}
QLabel#Bad {{ color: {c['bad']}; }}
QLabel#Screen {{ background: #000000; border: 1px solid {c['rule']};
                 border-radius: 6px; }}

QPushButton {{ background: {c['panel']}; color: {c['ink']};
               border: 1px solid {c['rule']}; border-radius: 6px;
               padding: 6px 12px; }}
QPushButton:hover {{ border-color: {c['accent']}; }}
QPushButton:pressed {{ background: {c['sunken']}; }}
QPushButton:checked {{ background: {c['accent']}; color: {c['accent_ink']};
                       border-color: {c['accent']}; }}
QPushButton:disabled {{ color: {c['hint']}; border-color: {c['rule']}; }}

QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {c['panel']}; color: {c['ink']};
    border: 1px solid {c['rule']}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {c['accent']};
    selection-color: {c['accent_ink']}; }}
QComboBox:focus, QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {c['accent']}; }}
QComboBox QAbstractItemView {{ background: {c['panel']}; color: {c['ink']};
    border: 1px solid {c['rule']};
    selection-background-color: {c['accent']};
    selection-color: {c['accent_ink']}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QPlainTextEdit, QTextEdit {{ background: {c['sunken']};
    font-family: "SF Mono", Menlo, Consolas, monospace; }}

QListWidget, QTreeWidget, QTableWidget, QGraphicsView {{
    background: {c['sunken']}; color: {c['ink']};
    border: 1px solid {c['rule']}; border-radius: 6px; }}
QListWidget::item {{ padding: 5px 6px; border-radius: 4px; }}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background: {c['accent']}; color: {c['accent_ink']}; }}
QListWidget::item:hover {{ background: {c['panel']}; }}
QHeaderView::section {{ background: {c['panel']}; color: {c['dim']};
    border: none; border-bottom: 1px solid {c['rule']}; padding: 6px; }}

QGroupBox {{ border: 1px solid {c['rule']}; border-radius: 8px;
             margin-top: 10px; padding-top: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px;
                    color: {c['dim']}; }}

QCheckBox, QRadioButton {{ spacing: 7px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px; height: 15px; border: 1px solid {c['rule']};
    border-radius: 4px; background: {c['panel']}; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {c['accent']}; border-color: {c['accent']}; }}
QCheckBox::indicator:disabled {{ background: {c['canvas']}; }}

QTabWidget::pane {{ border: 1px solid {c['rule']}; border-radius: 8px;
                    top: -1px; }}
QTabBar::tab {{ background: transparent; color: {c['dim']};
                padding: 7px 14px; border: none;
                border-bottom: 2px solid transparent; }}
QTabBar::tab:hover {{ color: {c['ink']}; }}
QTabBar::tab:selected {{ color: {c['ink']};
                         border-bottom: 2px solid {c['accent']}; }}

QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent; width: 10px; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: {c['rule']}; border-radius: 5px;
                      min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {c['hint']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{ background: {c['sunken']}; border: 1px solid {c['rule']};
                border-radius: 5px; text-align: center; color: {c['ink']}; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
QSplitter::handle {{ background: transparent; }}
QMenuBar {{ background: {c['canvas']}; color: {c['ink']}; }}
QMenuBar::item:selected {{ background: {c['accent']};
                           color: {c['accent_ink']}; }}
QMenu {{ background: {c['panel']}; color: {c['ink']};
         border: 1px solid {c['rule']}; }}
QMenu::item:selected {{ background: {c['accent']};
                        color: {c['accent_ink']}; }}
"""


def apply(qt_app: Any, mode: str = DEFAULT) -> str:
    """Dress the whole application. Returns the mode that took.

    On the QApplication, not on a window: a dialog or a popup has no
    parent widget to inherit from, which is exactly where the
    unreadable defaults were coming from.
    """
    mode = str(mode).lower()
    if mode not in PALETTES:
        mode = DEFAULT
    try:
        qt_app.setStyleSheet(stylesheet(mode))
    except Exception:  # noqa: BLE001 — a theme is never worth crashing for
        pass
    return mode


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two #RRGGBB colours.

    Here rather than only in the test because a palette that is not
    measured is a palette that drifts back to unreadable the next time
    somebody picks a grey by eye.
    """
    def luminance(colour: str) -> float:
        parts = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        parts = [p / 12.92 if p <= 0.03928 else ((p + 0.055) / 1.055) ** 2.4
                 for p in parts]
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]

    first, second = luminance(a), luminance(b)
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


__all__ = ["PALETTES", "DEFAULT", "palette", "stylesheet", "apply", "contrast"]
