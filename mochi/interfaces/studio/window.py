"""Mochi Studio window — the ref_1 "AI Studio" layout, restyled for Mochi.

Pure view: the widget knows nothing about the bus. It exposes seams
(:meth:`MochiStudioWindow.show_frame`, :meth:`set_emotion`,
:meth:`set_status`) that :func:`make_surface` drives from bus events. Run
``python -m mochi.interfaces.studio`` to preview it with no bus.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

# ── palette (dark purple, from the ref_1 mockup) ────────────────────
DEEP = "#0E0C16"
BG = "#151221"
PANEL = "#1C1830"
PANEL_HI = "#262038"
STROKE = "#2C2545"
ACCENT = "#7C5CFF"
ACCENT_HI = "#9B7DFF"
INK = "#ECEAF6"
INK_DIM = "#8A85A6"
GOOD = "#4ADE80"

_NAV = [
    ("◍", "Dashboard"), ("☺", "Characters"), ("✦", "Animations"),
    ("▶", "Media"), ("◈", "Persona"), ("▤", "Library"), ("⚙", "Settings"),
]
_TABS = ["Create", "Customize", "Animate"]
_SWATCHES = ["#7C5CFF", "#4ADE80", "#F472B6", "#FBBF24", "#38BDF8",
             "#FB7185", "#A78BFA", "#34D399", "#F59E0B", "#60A5FA"]


def _label(text: str, *, color: str = INK, size: int = 13, bold: bool = False) -> QLabel:
    lab = QLabel(text)
    f = QFont("SF Pro Text", size)
    f.setBold(bold)
    lab.setFont(f)
    lab.setStyleSheet(f"color: {color}; background: transparent;")
    return lab


class MochiStudioWindow(QWidget):
    """The Mochi Studio main window. Pure UI + a few render seams."""

    def __init__(self, agent_name: str = "Mochi") -> None:
        super().__init__()
        self._agent_name = agent_name
        self.setObjectName("MochiStudio")
        self.setWindowTitle("Mochi Studio")
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)
        self._build_ui()
        self._apply_theme()

    # ── layout ────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._sidebar())
        root.addWidget(self._main_column(), stretch=1)

    def _sidebar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(232)
        col = QVBoxLayout(bar)
        col.setContentsMargins(18, 22, 18, 18)
        col.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = _label("◆", color=ACCENT, size=20, bold=True)
        brand.addWidget(logo)
        brand.addWidget(_label("Mochi Studio", size=15, bold=True))
        brand.addStretch(1)
        col.addLayout(brand)
        col.addSpacing(22)

        self._nav_buttons: list[QPushButton] = []
        for i, (icon, name) in enumerate(_NAV):
            b = QPushButton(f"  {icon}    {name}")
            b.setObjectName("NavItem")
            b.setProperty("nav", name)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(i == 0)
            b.clicked.connect(lambda _=False, btn=b: self._select_nav(btn))
            self._nav_buttons.append(b)
            col.addWidget(b)

        col.addStretch(1)
        col.addWidget(self._plan_card())
        return bar

    def _plan_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("PlanCard")
        c = QVBoxLayout(card)
        c.setContentsMargins(16, 16, 16, 16)
        c.setSpacing(4)
        c.addWidget(_label("Premium Plan", size=13, bold=True))
        c.addWidget(_label("Unlock every character\nslot + HD export.", color="#E5DEFF", size=11))
        c.addSpacing(8)
        btn = QPushButton("Upgrade")
        btn.setObjectName("PlanBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        c.addWidget(btn)
        return card

    def _main_column(self) -> QWidget:
        wrap = QWidget()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._topbar())
        body = QHBoxLayout()
        body.setContentsMargins(18, 14, 18, 12)
        body.setSpacing(16)
        body.addWidget(self._center(), stretch=1)
        body.addWidget(self._right_panel())
        bw = QWidget()
        bw.setLayout(body)
        col.addWidget(bw, stretch=1)
        col.addWidget(self._bottom_bar())
        return wrap

    def _topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(60)
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(8)
        self._tab_buttons: list[QPushButton] = []
        for i, t in enumerate(_TABS):
            b = QPushButton(t)
            b.setObjectName("Tab")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(i == 0)
            b.clicked.connect(lambda _=False, btn=b: self._select_tab(btn))
            self._tab_buttons.append(b)
            row.addWidget(b)
        row.addStretch(1)
        search = QLineEdit()
        search.setObjectName("Search")
        search.setPlaceholderText("Search characters, animations…")
        search.setFixedWidth(240)
        row.addWidget(search)
        export = QPushButton("Export")
        export.setObjectName("Accent")
        export.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(export)
        avatar = QLabel(self._agent_name[:1].upper())
        avatar.setObjectName("Avatar")
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFixedSize(34, 34)
        row.addWidget(avatar)
        return bar

    def _stage(self) -> QWidget:
        stage = QFrame()
        stage.setObjectName("Stage")
        v = QVBoxLayout(stage)
        v.setContentsMargins(0, 0, 0, 0)
        # The character preview lands here. Until the animation node is
        # wired (phase 3) it's a placeholder; show_frame() swaps in pixels.
        self._char = QLabel()
        self._char.setObjectName("CharView")
        self._char.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._char.setText(f"◍\n\n{self._agent_name}")
        self._char.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        v.addWidget(self._char)
        return stage

    def _center(self) -> QWidget:
        self._center_stack = QStackedWidget()
        self._pages = {"Media": 1, "Characters": 2}
        self._center_stack.addWidget(self._stage())            # 0
        self._center_stack.addWidget(self._media_page())       # 1
        self._center_stack.addWidget(self._characters_page())  # 2
        return self._center_stack

    def _characters_page(self) -> QWidget:
        from mochi.interfaces.studio.characters import CharactersPage
        return CharactersPage()

    def _media_page(self) -> QWidget:
        from PySide6.QtWidgets import QListWidget
        from mochi.interfaces.media_player.window import MediaView
        page = QFrame(); page.setObjectName("Stage")
        outer = QVBoxLayout(page); outer.setContentsMargins(18, 18, 18, 18); outer.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(_label("Media Library", size=15, bold=True))
        self._lib_count = _label("", color=INK_DIM, size=12)
        head.addWidget(self._lib_count)
        head.addStretch(1)
        folder = QPushButton("Open folder…"); folder.setObjectName("Tab")
        folder.setCursor(Qt.CursorShape.PointingHandCursor)
        folder.clicked.connect(self._open_media_folder)
        launch = QPushButton("⧉  Launch Media Player"); launch.setObjectName("Accent")
        launch.setCursor(Qt.CursorShape.PointingHandCursor)
        launch.clicked.connect(self._launch_media)
        head.addWidget(folder); head.addWidget(launch)
        outer.addLayout(head)
        body = QHBoxLayout(); body.setSpacing(14)
        self._library = QListWidget(); self._library.setObjectName("Library")
        self._library.setFixedWidth(250)
        self._library.itemClicked.connect(self._on_library_pick)
        body.addWidget(self._library)
        self._media_view = MediaView()
        body.addWidget(self._media_view, stretch=1)
        outer.addLayout(body, stretch=1)
        self._media_path = ""
        self._media_dir = self._default_media_dir()
        self._scan_library()
        return page

    def _default_media_dir(self) -> str:
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[3]
        cand = root / "archive" / "mochi-v4" / "assets"
        return str(cand if cand.exists() else pathlib.Path.home())

    def _scan_library(self) -> None:
        import pathlib
        from PySide6.QtWidgets import QListWidgetItem
        from mochi.interfaces.media_player.window import _GIF, _IMAGE, _VIDEO, media_kind
        self._library.clear()
        exts = _IMAGE | _GIF | _VIDEO
        d = pathlib.Path(self._media_dir)
        files = sorted((q for q in d.rglob("*") if q.is_file() and q.suffix.lower() in exts),
                       key=lambda q: q.name.lower())[:500]
        glyph = {"image": "🖼", "gif": "▶", "video": "🎬"}
        for q in files:
            it = QListWidgetItem(f"{glyph.get(media_kind(str(q)), '•')}  {q.name}")
            it.setData(Qt.ItemDataRole.UserRole, str(q))
            self._library.addItem(it)
        self._lib_count.setText(f"· {len(files)} files")

    def _on_library_pick(self, item: Any) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self._media_path = path
            self._media_view.play(path)

    def _open_media_folder(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Choose media folder", self._media_dir)
        if d:
            self._media_dir = d
            self._scan_library()

    def _launch_media(self) -> None:
        from mochi.interfaces.media_player.window import FloatingMediaPlayer
        if getattr(self, "_floating_media", None) is None:
            self._floating_media = FloatingMediaPlayer()
        if self._media_path:
            self._floating_media.play(self._media_path)
        else:
            self._floating_media.show(); self._floating_media.raise_()

    def _right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("RightPanel")
        panel.setFixedWidth(284)
        v = QVBoxLayout(panel)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(12)
        v.addWidget(_label("Customize", size=14, bold=True))
        v.addWidget(_label("PALETTE", color=INK_DIM, size=10, bold=True))
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, c in enumerate(_SWATCHES):
            sw = QPushButton()
            sw.setObjectName("Swatch")
            sw.setFixedSize(QSize(34, 34))
            sw.setCursor(Qt.CursorShape.PointingHandCursor)
            sw.setStyleSheet(
                f"QPushButton#Swatch{{background:{c};border-radius:8px;"
                f"border:2px solid {'#FFFFFF' if i == 0 else 'transparent'};}}")
            grid.addWidget(sw, i // 5, i % 5)
        gw = QWidget()
        gw.setLayout(grid)
        v.addWidget(gw)
        v.addSpacing(6)
        v.addWidget(_label("PROPERTIES", color=INK_DIM, size=10, bold=True))
        for name in ("Outfit", "Mood", "Accent", "Background"):
            v.addLayout(self._prop_row(name))
        v.addStretch(1)
        return panel

    def _prop_row(self, name: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(_label(name, color=INK_DIM, size=12))
        row.addStretch(1)
        s = QSlider(Qt.Orientation.Horizontal)
        s.setObjectName("Prop")
        s.setFixedWidth(120)
        s.setValue(55)
        row.addWidget(s)
        return row

    def _bottom_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("BottomBar")
        bar.setFixedHeight(122)
        v = QVBoxLayout(bar)
        v.setContentsMargins(18, 12, 18, 12)
        v.setSpacing(8)
        carousel = QHBoxLayout()
        carousel.setSpacing(10)
        for i in range(7):
            t = QFrame()
            t.setObjectName("Thumb")
            t.setFixedSize(64, 56)
            if i == 0:
                t.setStyleSheet(
                    f"QFrame#Thumb{{background:{PANEL_HI};border-radius:10px;"
                    f"border:2px solid {ACCENT};}}")
            carousel.addWidget(t)
        carousel.addStretch(1)
        v.addLayout(carousel)
        timeline = QSlider(Qt.Orientation.Horizontal)
        timeline.setObjectName("Timeline")
        timeline.setValue(30)
        v.addWidget(timeline)
        return bar

    # ── selection state ───────────────────────────────────────────
    def _select_nav(self, btn: QPushButton) -> None:
        for b in self._nav_buttons:
            b.setChecked(b is btn)
        self._center_stack.setCurrentIndex(self._pages.get(btn.property("nav"), 0))

    def _select_tab(self, btn: QPushButton) -> None:
        for b in self._tab_buttons:
            b.setChecked(b is btn)

    # ── render seams (driven by make_surface from bus events) ──────
    def show_frame(self, rgba: bytes, w: int, h: int) -> None:
        """Paint one animation frame (RGBA8, w*h*4 bytes) on the stage."""
        img = QImage(rgba, w, h, w * 4, QImage.Format.Format_RGBA8888)
        self._char.setPixmap(QPixmap.fromImage(img).scaled(
            self._char.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def set_emotion(self, emotion: str) -> None:
        self._char.setToolTip(f"emotion: {emotion}")

    def set_status(self, text: str) -> None:
        self.setWindowTitle(f"Mochi Studio — {text}" if text else "Mochi Studio")

    # ── theme ─────────────────────────────────────────────────────
    def _apply_theme(self) -> None:
        self.setStyleSheet(f"""
            QWidget#MochiStudio {{ background: {BG}; }}
            QFrame#Sidebar {{ background: {PANEL}; border-right: 1px solid {STROKE}; }}
            QPushButton#NavItem {{
                text-align: left; padding: 11px 12px; border: none;
                border-radius: 10px; color: {INK_DIM};
                font-size: 13px; background: transparent;
            }}
            QPushButton#NavItem:hover {{ background: {PANEL_HI}; color: {INK}; }}
            QPushButton#NavItem:checked {{ background: {ACCENT}; color: white; }}
            QFrame#PlanCard {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 {ACCENT}, stop:1 #5B3FD6);
                border-radius: 14px;
            }}
            QPushButton#PlanBtn {{
                background: rgba(255,255,255,0.18); color: white; border: none;
                border-radius: 9px; padding: 8px; font-weight: 600;
            }}
            QPushButton#PlanBtn:hover {{ background: rgba(255,255,255,0.30); }}
            QFrame#TopBar {{ background: {BG}; border-bottom: 1px solid {STROKE}; }}
            QPushButton#Tab {{
                border: none; padding: 8px 16px; border-radius: 9px;
                color: {INK_DIM}; font-size: 13px; background: transparent;
            }}
            QPushButton#Tab:checked {{ background: {PANEL_HI}; color: {INK}; }}
            QLineEdit#Search {{
                background: {PANEL}; border: 1px solid {STROKE}; border-radius: 9px;
                padding: 7px 12px; color: {INK}; font-size: 12px;
            }}
            QLineEdit#Search:focus {{ border: 1px solid {ACCENT}; }}
            QPushButton#Accent {{
                background: {ACCENT}; color: white; border: none;
                border-radius: 9px; padding: 8px 18px; font-weight: 600;
            }}
            QPushButton#Accent:hover {{ background: {ACCENT_HI}; }}
            QLabel#Avatar {{
                background: {PANEL_HI}; color: {INK}; border-radius: 17px;
                font-weight: 700; border: 1px solid {STROKE};
            }}
            QFrame#Stage {{
                background: qlineargradient(x1:0,y1:0,x2:0.6,y2:1,
                    stop:0 {PANEL_HI}, stop:1 {DEEP});
                border-radius: 18px; border: 1px solid {STROKE};
            }}
            QLabel#CharView {{ color: {INK_DIM}; font-size: 40px; }}
            QFrame#RightPanel {{ background: {PANEL}; border-radius: 16px; border: 1px solid {STROKE}; }}
            QFrame#BottomBar {{ background: {PANEL}; border-top: 1px solid {STROKE}; }}
            QFrame#Thumb {{ background: {PANEL_HI}; border-radius: 10px; border: 1px solid {STROKE}; }}
            QListWidget#Library {{
                background: {PANEL}; border: 1px solid {STROKE}; border-radius: 12px;
                color: {INK}; font-size: 12px; padding: 6px; outline: none;
            }}
            QListWidget#Library::item {{ padding: 7px 8px; border-radius: 7px; }}
            QListWidget#Library::item:selected {{ background: {ACCENT}; color: white; }}
            QListWidget#Library::item:hover {{ background: {PANEL_HI}; }}
            QSlider::groove:horizontal {{ height: 4px; background: {STROKE}; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
            QSlider::handle:horizontal {{
                background: white; width: 13px; height: 13px;
                margin: -5px 0; border-radius: 7px;
            }}
        """)


def make_surface(ctx: Any, spec: Any = None) -> MochiStudioWindow:  # noqa: ARG001
    """Chassis surface factory — the ONLY bus coupling. Subscribes the
    window to existing event-gateway topics; publishes nothing the core
    doesn't already expose. No core/other-surface changes."""
    name = (
        getattr(getattr(ctx, "core", None), "agent_name", None)
        or getattr(ctx, "agent_name", None) or "Mochi")
    win = MochiStudioWindow(agent_name=name)
    bus = getattr(ctx, "bus", None)
    if bus is not None:
        from mochi.app.surfaces import make_bus_bridge
        from mochi.transport import topics
        win._bridge = make_bus_bridge(
            bus, [topics.SENSE_ANIMATION_STATE, "/sense/agent_state"])

        def _on_msg(msg: Any) -> None:
            state = getattr(msg, "state", "") or ""
            params = getattr(msg, "params", None) or {}
            if isinstance(params, dict) and params.get("emotion"):
                win.set_emotion(params["emotion"])
            if state:
                win.set_status(state)
        win._bridge.message.connect(_on_msg)
    return win
