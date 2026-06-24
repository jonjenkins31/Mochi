"""Mochi Studio window — the ref_1 "AI Studio" layout, restyled for Mochi.

Pure view: the widget knows nothing about the bus. It exposes seams
(:meth:`MochiStudioWindow.show_frame`, :meth:`set_emotion`,
:meth:`set_status`) that :func:`make_surface` drives from bus events. Run
``python -m mochi.interfaces.studio`` to preview it with no bus.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

from .background import GradientBackground
from .icons import logo_pixmap
from .sidebar import Sidebar
from .theme import (
    ACCENT, ACCENT_HI, BG, DEEP, GOOD, INK, INK_DIM, PANEL, PANEL_HI, STROKE,
    _label, stylesheet,
)

_TABS = ["Create", "Customize", "Animate"]
_SWATCHES = ["#7C5CFF", "#4ADE80", "#F472B6", "#FBBF24", "#38BDF8",
             "#FB7185", "#A78BFA", "#34D399", "#F59E0B", "#60A5FA"]


class MochiStudioWindow(QWidget):
    """The Mochi Studio main window. Pure UI + a few render seams."""

    def __init__(self, agent_name: str = "Mochi", ctx: Any = None) -> None:
        super().__init__()
        self._agent_name = agent_name
        self._ctx = ctx
        self._char: QLabel | None = None   # set by a tab that hosts the avatar stage
        self.setObjectName("MochiStudio")
        self.setWindowTitle("Mochi Studio")
        self.setWindowIcon(QIcon(logo_pixmap(PANEL, ACCENT_HI, 64)))
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)
        self._build_ui()
        self._apply_theme()

    # ── layout ────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # The gradient backdrop is a free child behind everything (sized in
        # resizeEvent) — a swappable overlay, not baked into the window.
        self._bg = GradientBackground(self)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._sidebar = Sidebar(self._agent_name)
        self._sidebar.navSelected.connect(self._on_nav)
        root.addWidget(self._sidebar)
        root.addWidget(self._main_column(), stretch=1)
        self._bg.lower()                       # keep it behind the content

    def resizeEvent(self, e: Any) -> None:  # noqa: N802 — Qt override
        super().resizeEvent(e)
        self._bg.setGeometry(self.rect())

    def _main_column(self) -> QWidget:
        # Shell = top bar + the center page stack ONLY. The right "Customize"
        # panel and the bottom carousel/timeline are NOT baked in — they're
        # opt-in pieces a specific tab adds to its own page (see
        # _right_panel / _bottom_bar, reused where a tab needs them).
        wrap = QWidget()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._topbar())
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(18, 14, 18, 16)
        bl.setSpacing(0)
        bl.addWidget(self._center(), stretch=1)
        col.addWidget(body, stretch=1)
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

    def _empty_page(self) -> QWidget:
        """The Dashboard — intentionally empty for now; the backdrop shows."""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        return page

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
        self._center_stack.addWidget(self._empty_page())       # 0  Dashboard (empty)
        self._center_stack.addWidget(self._media_page())       # 1  Media (built)
        self._center_stack.addWidget(self._characters_page())  # 2  Characters (built)
        self._center_stack.addWidget(self._chat_page())        # 3  Chat (avatar + TUI)
        self._pages = {"Dashboard": 0, "Media": 1, "Characters": 2, "Chat": 3}
        # Planned tabs — clickable wireframe stubs until each is built out.
        _STUBS = [
            ("Animation", "Trigger expressions (happy / sad / blink…), a live avatar preview, "
                          "and the mscript editor — drives the animation node."),
            ("Editors", "Author animations: mscript / bitmap / sprite editors."),
            ("Assets", "Browse + preview the asset library — gifs, bitmaps, sprites, mscripts, "
                       "math, video, skins."),
            ("Packs", "Bundle + manage asset packs (export / import / share)."),
            ("Diagnostics", "Node + agent health, perf counters, and logs."),
            ("Learn", "Tutorials — the migrated docs/learn guides (animations, sprites, mscripts…)."),
            ("Settings", "Config — voice, model, instance paths, theme."),
        ]
        for name, blurb in _STUBS:
            self._pages[name] = self._center_stack.count()
            self._center_stack.addWidget(self._stub_page(name, blurb))
        return self._center_stack

    def _stub_page(self, name: str, blurb: str) -> QWidget:
        """A clickable wireframe placeholder — names the tab + its planned content."""
        page = QFrame(); page.setObjectName("Stage")
        v = QVBoxLayout(page); v.setContentsMargins(30, 28, 30, 28); v.setSpacing(10)
        v.addWidget(_label(name, size=18, bold=True))
        v.addWidget(_label("◌  planned — wireframe stub", color=ACCENT, size=11, bold=True))
        note = _label(blurb, color=INK_DIM, size=13); note.setWordWrap(True)
        v.addWidget(note)
        v.addStretch(1)
        return page

    def _characters_page(self) -> QWidget:
        from mochi.interfaces.studio.characters import CharactersPage
        return CharactersPage()

    def _chat_page(self) -> QWidget:
        from mochi.interfaces.studio.chat import ChatPage
        return ChatPage(self._ctx)

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
        cand = pathlib.Path(__file__).resolve().parents[2] / "assets"
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
    def _on_nav(self, name: str) -> None:
        """The sidebar emitted a nav pick — swap the center page."""
        self._center_stack.setCurrentIndex(self._pages.get(name, 0))

    def _select_tab(self, btn: QPushButton) -> None:
        for b in self._tab_buttons:
            b.setChecked(b is btn)

    # ── render seams (driven by make_surface from bus events) ──────
    def show_frame(self, rgba: bytes, w: int, h: int) -> None:
        """Paint one animation frame (RGBA8) — only when a tab hosts the avatar
        stage (sets ``self._char``). No-op otherwise."""
        if self._char is None:
            return
        img = QImage(rgba, w, h, w * 4, QImage.Format.Format_RGBA8888)
        self._char.setPixmap(QPixmap.fromImage(img).scaled(
            self._char.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def set_emotion(self, emotion: str) -> None:
        if self._char is not None:
            self._char.setToolTip(f"emotion: {emotion}")

    def set_status(self, text: str) -> None:
        self.setWindowTitle(f"Mochi Studio — {text}" if text else "Mochi Studio")

    # ── theme ─────────────────────────────────────────────────────
    def _apply_theme(self) -> None:
        self.setStyleSheet(stylesheet())


def make_surface(ctx: Any, spec: Any = None) -> MochiStudioWindow:  # noqa: ARG001
    """Chassis surface factory — the ONLY bus coupling. Subscribes the
    window to existing event-gateway topics; publishes nothing the core
    doesn't already expose. No core/other-surface changes."""
    name = (
        getattr(getattr(ctx, "core", None), "agent_name", None)
        or getattr(ctx, "agent_name", None) or "Mochi")
    win = MochiStudioWindow(agent_name=name, ctx=ctx)
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
