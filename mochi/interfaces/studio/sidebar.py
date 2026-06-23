"""The Studio left column — brand, the persistent nav menu, a profile, and a
support/links card. A self-contained widget; it knows nothing about the pages,
it just emits :data:`Sidebar.navSelected` so the window swaps the center.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .theme import ACCENT, INK_DIM, _label

# The persistent menu — (icon, page name). Names match window._pages keys.
NAV = [
    ("◍", "Dashboard"), ("☺", "Characters"), ("✦", "Animation"),
    ("✎", "Editors"), ("▶", "Media"), ("▤", "Assets"), ("▦", "Packs"),
    ("▣", "Chat"), ("◆", "Diagnostics"), ("◉", "Learn"), ("⚙", "Settings"),
]
_YOUTUBE = "https://youtube.com/@Jenkins_Robotics"


class ProfileCard(QFrame):
    """Who you're working as — avatar + name + subtitle. (A later pass can point
    this at the active character; for now it shows the agent.)"""

    def __init__(self, name: str, subtitle: str = "Local agent",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProfileCard")
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        av = QLabel((name[:1] or "M").upper())
        av.setObjectName("ProfileAvatar")
        av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setFixedSize(36, 36)
        row.addWidget(av)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(_label(name, size=13, bold=True))
        col.addWidget(_label(subtitle, color=INK_DIM, size=11))
        row.addLayout(col)
        row.addStretch(1)


class AddonCard(QFrame):
    """The bottom CTA slot — support / project links (vs. a premium upsell)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AddonCard")
        c = QVBoxLayout(self)
        c.setContentsMargins(16, 14, 16, 14)
        c.setSpacing(4)
        c.addWidget(_label("Jenkins Robotics", size=13, bold=True))
        c.addWidget(_label("Follow the build +\nsupport the project.", color="#E5DEFF", size=11))
        c.addSpacing(8)
        btn = QPushButton("YouTube")
        btn.setObjectName("AddonBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(_YOUTUBE)))
        c.addWidget(btn)


class Sidebar(QFrame):
    """The persistent left column. Emits ``navSelected(name)`` on menu clicks."""

    navSelected = Signal(str)

    def __init__(self, agent_name: str = "Mochi", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(232)
        col = QVBoxLayout(self)
        col.setContentsMargins(18, 22, 18, 18)
        col.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(_label("◆", color=ACCENT, size=20, bold=True))
        brand.addWidget(_label("Mochi Studio", size=15, bold=True))
        brand.addStretch(1)
        col.addLayout(brand)
        col.addSpacing(22)

        self._buttons: list[QPushButton] = []
        for i, (icon, name) in enumerate(NAV):
            b = QPushButton(f"  {icon}    {name}")
            b.setObjectName("NavItem")
            b.setProperty("nav", name)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(i == 0)
            b.clicked.connect(lambda _=False, btn=b: self._pick(btn))
            self._buttons.append(b)
            col.addWidget(b)

        col.addStretch(1)
        self.profile = ProfileCard(agent_name)
        col.addWidget(self.profile)
        col.addSpacing(8)
        col.addWidget(AddonCard())

    def _pick(self, btn: QPushButton) -> None:
        for b in self._buttons:
            b.setChecked(b is btn)
        self.navSelected.emit(str(btn.property("nav")))
