"""Characters page — the library list + a JANE-style profile.

Embedded as the Studio "Characters" tab. Reads the character library
(``personality/characters/``) and renders the selected character's sheet: name,
the SPECIAL attributes as bars, the Domains as PROGRESS levels, and the
prompt the model sees today. Pure view over :mod:`mochi.personality.character`.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPlainTextEdit, QProgressBar, QPushButton, QSlider,
    QScrollArea, QVBoxLayout, QWidget,
)

from mochi.interfaces.studio.theme import (
    ACCENT, BG, GOOD, INK, INK_DIM, PANEL, PANEL_HI, STROKE, _label,
)
from mochi.personality.character import Character, create_character, layer_items, list_characters, load_character, save_character_traits


def _bar(value: float, color: str = GOOD) -> QProgressBar:
    p = QProgressBar()
    p.setRange(0, 100)
    p.setValue(int(round(_f(value) * 100)))
    p.setTextVisible(False)
    p.setFixedHeight(8)
    p.setStyleSheet(
        f"QProgressBar{{background:{STROKE};border:none;border-radius:4px;}}"
        f"QProgressBar::chunk{{background:{color};border-radius:4px;}}")
    return p


def _f(v: Any) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


class CharactersPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._chars: list[Character] = list_characters()
        self._active_id = self._read_active()
        self._build()

    def _new_character(self) -> None:
        dlg = NewCharacterDialog(self)
        if not dlg.exec():
            return
        name, role, ci = dlg.values()
        if not name.strip():
            return
        c = create_character(name.strip(), role=role.strip(), custom_instructions=ci.strip())
        self._chars = list_characters()
        self._list.clear()
        for ch in self._chars:
            self._list.addItem(f"  {ch.name}")
        self._count_lbl.setText(str(len(self._chars)))
        idx = next((i for i, ch in enumerate(self._chars) if ch.id == c.id), 0)
        self._list.setCurrentRow(idx)

    def _edit_traits(self, c: Character) -> None:
        dlg = TraitEditor(c, self)
        if dlg.exec():
            save_character_traits(c.root, dlg.values())
            self._chars[self._list.currentRow()] = load_character(c.root)
            self._show(self._list.currentRow())

    def _read_active(self) -> str:
        try:
            from mochi.core.instance.instance import resolve_instance_dir
            from mochi.personality.character import active_character_id
            return active_character_id(resolve_instance_dir())
        except Exception:  # noqa: BLE001
            return ""

    def _use(self, c: Character) -> None:
        try:
            from mochi.core.instance.instance import resolve_instance_dir
            from mochi.personality.character import set_active_character
            set_active_character(resolve_instance_dir(), c.id)
            self._active_id = c.id
        except Exception:  # noqa: BLE001
            pass
        self._show(self._list.currentRow())

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        # ── library list ──────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(_label("Character Library", size=14, bold=True))
        head.addStretch(1)
        new = QPushButton("+ New"); new.setObjectName("Tab")
        new.setCursor(Qt.CursorShape.PointingHandCursor); new.clicked.connect(self._new_character)
        head.addWidget(new)
        self._count_lbl = _label(f"{len(self._chars)}", color=INK_DIM, size=12)
        head.addWidget(self._count_lbl)
        left.addLayout(head)
        self._list = QListWidget()
        self._list.setObjectName("Library")
        self._list.setFixedWidth(230)
        for c in self._chars:
            self._list.addItem(f"  {c.name}")
        self._list.currentRowChanged.connect(self._show)
        left.addWidget(self._list, stretch=1)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(230)
        root.addWidget(lw)

        # ── profile (rebuilt per selection) ───────────────────────
        self._profile = QFrame()
        self._profile.setObjectName("Stage")
        self._profile_lay = QVBoxLayout(self._profile)
        self._profile_lay.setContentsMargins(24, 22, 24, 22)
        self._profile_lay.setSpacing(16)
        root.addWidget(self._profile, stretch=1)

        if self._chars:
            self._list.setCurrentRow(0)
        else:
            self._profile_lay.addWidget(_label("No characters found.", color=INK_DIM))

    # ── profile render ────────────────────────────────────────────
    def _show(self, idx: int) -> None:
        while self._profile_lay.count():
            item = self._profile_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not (0 <= idx < len(self._chars)):
            return
        c = self._chars[idx]

        # header — big name + role
        name = _label(c.name, size=30, bold=True)
        self._profile_lay.addWidget(name)
        if c.role or c.description:
            self._profile_lay.addWidget(_label(c.role or c.description, color=INK_DIM, size=13))

        # select this character for the agent
        act = QHBoxLayout()
        use = QPushButton("✦  Use this character")
        use.setObjectName("Tab" if c.id == self._active_id else "Accent")
        use.setCursor(Qt.CursorShape.PointingHandCursor)
        use.clicked.connect(lambda: self._use(c))
        act.addWidget(use)
        edit = QPushButton("✎  Edit traits"); edit.setObjectName("Tab")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(lambda: self._edit_traits(c))
        act.addWidget(edit)
        if c.id == self._active_id:
            act.addWidget(_label("● ACTIVE — the agent is playing this character",
                                 color=GOOD, size=12, bold=True))
        act.addStretch(1)
        aw = QWidget(); aw.setLayout(act)
        self._profile_lay.addWidget(aw)

        # body: ATTRIBUTES | portrait | PROGRESS
        body = QHBoxLayout()
        body.setSpacing(22)
        body.addLayout(self._attrs(c), stretch=1)
        body.addWidget(self._portrait(c))
        body.addLayout(self._progress(c), stretch=1)
        bw = QWidget()
        bw.setLayout(body)
        self._profile_lay.addWidget(bw, stretch=1)

        # the in-depth sheet (the live model gets a short brief, not all of this)
        self._profile_lay.addWidget(_label("CHARACTER SHEET (in-depth — model gets a short brief)",
                                            color=INK_DIM, size=10, bold=True))
        prompt = QLabel(c.prompt() or "—")
        prompt.setWordWrap(True)
        prompt.setStyleSheet(f"color:{INK}; background:{PANEL_HI}; border-radius:10px; padding:12px;")
        self._profile_lay.addWidget(prompt)

    def _attrs(self, c: Character) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(10)
        col.addWidget(_label("ATTRIBUTES", color=INK_DIM, size=11, bold=True))
        for key, val in layer_items(c.personality.special):
            col.addWidget(_label(key.upper(), color=INK, size=12))
            col.addWidget(_bar(val))
        col.addStretch(1)
        return col

    def _progress(self, c: Character) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)
        col.addWidget(_label("PROGRESS", color=INK_DIM, size=11, bold=True))
        for key, val in layer_items(c.personality.domains):
            row = QHBoxLayout()
            row.addWidget(_label(key.upper(), color=INK, size=12))
            row.addStretch(1)
            row.addWidget(_label(f"LVL {int(round(_f(val) * 15))}", color=GOOD, size=12, bold=True))
            col.addLayout(row)
            col.addWidget(_bar(val))
        col.addStretch(1)
        return col

    def _portrait(self, c: Character) -> QWidget:
        box = QFrame()
        box.setObjectName("Stage")
        box.setFixedWidth(220)
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        lab = QLabel()
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card = c.card_path()
        if card is not None:
            lab.setPixmap(QPixmap(str(card)).scaledToWidth(
                200, Qt.TransformationMode.SmoothTransformation))
        else:
            lab.setText("◍")
            lab.setStyleSheet(f"color:{INK_DIM}; font-size:64px;")
        v.addWidget(lab)
        v.addSpacing(10)
        v.addWidget(_label("EXPRESSION", color=INK_DIM, size=10, bold=True))
        radar = TraitRadar([(k, val) for k, val in layer_items(c.personality.expression)])
        radar.setFixedHeight(168)
        v.addWidget(radar)
        return box


class TraitEditor(QDialog):
    """Slider editor for a character's trait layers (HEXACO/SPECIAL/Expression/
    Domains). Writes back to the sheet on Save."""

    _LAYERS = ("hexaco", "special", "expression", "domains")

    def __init__(self, character: Character, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit traits — {character.name}")
        self.resize(620, 640)
        self.setStyleSheet(f"QDialog{{background:{BG};}} QLabel{{color:{INK};}}")
        self._sliders: dict[tuple[str, str], QSlider] = {}
        outer = QVBoxLayout(self)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget(); grid = QGridLayout(body); grid.setSpacing(16)
        p = character.personality
        layers = [("HEXACO", "hexaco", p.hexaco), ("SPECIAL", "special", p.special),
                  ("EXPRESSION", "expression", p.expression), ("DOMAINS", "domains", p.domains)]
        for i, (title, key, struct) in enumerate(layers):
            box = QVBoxLayout(); box.setSpacing(8)
            box.addWidget(_label(title, color=ACCENT, size=12, bold=True))
            for field, val in layer_items(struct):
                row = QHBoxLayout()
                row.addWidget(_label(field, color=INK_DIM, size=11)); row.addStretch(1)
                sl = QSlider(Qt.Orientation.Horizontal); sl.setRange(0, 100)
                sl.setValue(int(round(float(val) * 100))); sl.setFixedWidth(150)
                vl = _label(f"{float(val):.2f}", color=GOOD, size=11)
                sl.valueChanged.connect(lambda v, lab=vl: lab.setText(f"{v/100:.2f}"))
                self._sliders[(key, field)] = sl
                row.addWidget(sl); row.addWidget(vl)
                box.addLayout(row)
            w = QWidget(); w.setLayout(box)
            grid.addWidget(w, i // 2, i % 2)
        scroll.setWidget(body); outer.addWidget(scroll, stretch=1)
        btns = QHBoxLayout(); btns.addStretch(1)
        cancel = QPushButton("Cancel"); cancel.setObjectName("Tab"); cancel.clicked.connect(self.reject)
        save = QPushButton("Save"); save.setObjectName("Accent"); save.clicked.connect(self.accept)
        btns.addWidget(cancel); btns.addWidget(save)
        outer.addLayout(btns)

    def values(self) -> dict:
        out: dict = {}
        for (layer, field), sl in self._sliders.items():
            out.setdefault(layer, {})[field] = sl.value() / 100.0
        return out


class NewCharacterDialog(QDialog):
    """Create a character: name + role + the prompt the model sees. Traits
    default to neutral and are tuned in the trait editor afterward."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New character")
        self.resize(460, 360)
        self.setStyleSheet(
            f"QDialog{{background:{BG};}} QLabel{{color:{INK};}}"
            f"QLineEdit,QPlainTextEdit{{background:{PANEL};color:{INK};"
            f"border:1px solid {STROKE};border-radius:8px;padding:7px;}}")
        v = QVBoxLayout(self); v.setSpacing(8)
        v.addWidget(_label("Name", color=INK_DIM, size=11))
        self._name = QLineEdit(); v.addWidget(self._name)
        v.addWidget(_label("Role (one line)", color=INK_DIM, size=11))
        self._role = QLineEdit(); v.addWidget(self._role)
        v.addWidget(_label("Character prompt (what the model sees)", color=INK_DIM, size=11))
        self._ci = QPlainTextEdit(); v.addWidget(self._ci, stretch=1)
        btns = QHBoxLayout(); btns.addStretch(1)
        cancel = QPushButton("Cancel"); cancel.setObjectName("Tab"); cancel.clicked.connect(self.reject)
        create = QPushButton("Create"); create.setObjectName("Accent"); create.clicked.connect(self.accept)
        btns.addWidget(cancel); btns.addWidget(create); v.addLayout(btns)

    def values(self) -> tuple[str, str, str]:
        return self._name.text(), self._role.text(), self._ci.toPlainText()


class TraitRadar(QWidget):
    """A spider/radar chart of a trait layer, painted with QPainter."""

    def __init__(self, items: list, color: str = ACCENT, parent: Any = None) -> None:
        super().__init__(parent)
        self._items = items
        self._color = color
        self.setMinimumSize(180, 160)

    def paintEvent(self, e: Any) -> None:  # noqa: N802
        import math
        n = len(self._items)
        if n < 3:
            return
        pa = QPainter(self)
        pa.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        R = min(w, h) / 2.0 - 26

        def pt(i: int, rad: float) -> QPointF:
            ang = 2 * math.pi * i / n - math.pi / 2
            return QPointF(cx + R * rad * math.cos(ang), cy + R * rad * math.sin(ang))

        pa.setPen(QPen(QColor(STROKE), 1))
        for ring in (0.34, 0.67, 1.0):
            pa.drawPolygon(QPolygonF([pt(i, ring) for i in range(n)]))
        pa.setPen(QPen(QColor(STROKE), 1))
        for i in range(n):
            pa.drawLine(QPointF(cx, cy), pt(i, 1.0))
        pa.setPen(QColor(INK_DIM))
        for i, (label, _v) in enumerate(self._items):
            edge = pt(i, 1.12)
            pa.drawText(QPointF(edge.x() - 12, edge.y() + 4), str(label)[:4])
        vpts = [pt(i, max(0.0, min(1.0, float(v)))) for i, (_l, v) in enumerate(self._items)]
        fill = QColor(self._color); fill.setAlpha(70)
        pa.setBrush(QBrush(fill)); pa.setPen(QPen(QColor(self._color), 2))
        pa.drawPolygon(QPolygonF(vpts))
        pa.end()
