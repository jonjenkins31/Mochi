"""Characters page — a character-library card grid.

Embedded as the Studio "Characters" tab. Reads the character library
(``personality/characters/``) and renders each character as a card: the card
art fills it, with the name / role / level / key stats overlaid on a bottom
gradient, plus SELECT (play this character) + EDIT (trait editor). Pure view
over :mod:`mochi.personality.character`.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
)
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget,
)

from mochi.interfaces.studio.theme import (
    ACCENT, ACCENT_HI, BG, GOOD, INK, INK_DIM, PANEL, PANEL_HI, STROKE, _label,
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


_CARD_QSS = f"""
QLabel#LvlBadge {{
    background: rgba(124,92,255,0.85); color: white; font-size: 11px;
    font-weight: 700; border-radius: 9px; padding: 3px 9px;
}}
QPushButton#CardSelect {{
    background: {ACCENT}; color: white; border: none; border-radius: 9px;
    padding: 8px; font-weight: 700; font-size: 12px;
}}
QPushButton#CardSelect:hover {{ background: {ACCENT_HI}; }}
QPushButton#CardActive {{
    background: {GOOD}; color: #0A0910; border: none; border-radius: 9px;
    padding: 8px; font-weight: 700; font-size: 12px;
}}
QPushButton#CardEdit {{
    background: rgba(255,255,255,0.12); color: {INK}; border: none;
    border-radius: 9px; padding: 8px; font-weight: 700; font-size: 12px;
}}
QPushButton#CardEdit:hover {{ background: rgba(255,255,255,0.20); }}
"""


class CharacterCard(QFrame):
    """A library card â art fill + name/role/level/key-stats over a bottom
    gradient, with SELECT (play this character) + EDIT (trait editor)."""

    CARD_W, CARD_H = 276, 356

    def __init__(self, character: Character, *, active: bool,
                 on_select: Any, on_edit: Any, parent: Any = None) -> None:
        super().__init__(parent)
        self._char = character
        self._active = active
        self.setFixedSize(self.CARD_W, self.CARD_H)
        card = character.card_path()
        self._pix = QPixmap(str(card)) if card is not None else None

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 16)
        v.setSpacing(3)
        top = QHBoxLayout()
        top.addStretch(1)
        badge = QLabel(self._level_text())
        badge.setObjectName("LvlBadge")
        top.addWidget(badge)
        v.addLayout(top)
        v.addStretch(1)

        v.addWidget(_label(character.name.upper(), size=19, bold=True))
        v.addWidget(_label(character.role or "—", color="#C9C4E0", size=11))
        v.addSpacing(4)
        v.addLayout(self._stats_row())
        v.addSpacing(9)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        sel = QPushButton("PLAYING" if active else "SELECT")
        sel.setObjectName("CardActive" if active else "CardSelect")
        sel.setCursor(Qt.CursorShape.PointingHandCursor)
        sel.clicked.connect(lambda: on_select(character))
        edit = QPushButton("EDIT")
        edit.setObjectName("CardEdit")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(lambda: on_edit(character))
        btns.addWidget(sel, stretch=2)
        btns.addWidget(edit, stretch=1)
        v.addLayout(btns)

    def _level_text(self) -> str:
        sp = layer_items(self._char.personality.special)
        avg = sum(_f(val) for _, val in sp) / max(1, len(sp))
        return f"Lv {max(1, int(round(avg * 60)))}"

    def _stats_row(self) -> QHBoxLayout:
        sp = dict(layer_items(self._char.personality.special))
        row = QHBoxLayout()
        row.setSpacing(16)
        for key, short in (("intelligence", "INT"), ("charisma", "CHA"), ("strength", "STR")):
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(_label(short, color="#A29DC0", size=9, bold=True))
            col.addWidget(_label(str(int(round(_f(sp.get(key, 0.5)) * 100))), size=14, bold=True))
            row.addLayout(col)
        row.addStretch(1)
        return row

    def paintEvent(self, e: Any) -> None:  # noqa: N802 â Qt override
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rf = QRectF(self.rect().adjusted(0, 0, -1, -1))
        path = QPainterPath()
        path.addRoundedRect(rf, 16, 16)
        p.setClipPath(path)
        if self._pix is not None and not self._pix.isNull():
            sc = self._pix.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                  Qt.TransformationMode.SmoothTransformation)
            sx = max(0, (sc.width() - self.width()) // 2)
            sy = max(0, (sc.height() - self.height()) // 2)
            p.drawPixmap(0, 0, sc, sx, sy, self.width(), self.height())
        else:
            p.fillRect(rf, QColor(PANEL))
        grad = QLinearGradient(0, self.height() * 0.32, 0, self.height())
        grad.setColorAt(0.0, QColor(8, 7, 12, 0))
        grad.setColorAt(0.55, QColor(8, 7, 12, 205))
        grad.setColorAt(1.0, QColor(8, 7, 12, 246))
        p.fillRect(rf, QBrush(grad))
        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(ACCENT) if self._active else QColor(STROKE),
                      2 if self._active else 1))
        p.drawRoundedRect(rf, 16, 16)
        p.end()


class CharactersPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._chars: list[Character] = list_characters()
        self._active_id = self._read_active()
        self.setStyleSheet(_CARD_QSS)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)
        head = QHBoxLayout()
        head.addWidget(_label("Character Library", size=20, bold=True))
        self._count_lbl = _label(f"·  {len(self._chars)} characters", color=INK_DIM, size=12)
        head.addWidget(self._count_lbl)
        head.addStretch(1)
        new = QPushButton("+  New Character")
        new.setObjectName("Accent")
        new.setCursor(Qt.CursorShape.PointingHandCursor)
        new.clicked.connect(self._new_character)
        head.addWidget(new)
        root.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        host = QWidget()
        host.setStyleSheet("background:transparent;")
        self._grid = QGridLayout(host)
        self._grid.setSpacing(18)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(host)
        root.addWidget(scroll, stretch=1)
        self._populate()

    def _populate(self) -> None:
        while self._grid.count():
            it = self._grid.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        if not self._chars:
            self._grid.addWidget(_label("No characters found.", color=INK_DIM), 0, 0)
            return
        cols = 3
        for i, c in enumerate(self._chars):
            card = CharacterCard(c, active=(c.id == self._active_id),
                                 on_select=self._use, on_edit=self._edit_traits)
            self._grid.addWidget(card, i // cols, i % cols)

    # ── actions ──
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
        self._populate()

    def _edit_traits(self, c: Character) -> None:
        dlg = TraitEditor(c, self)
        if dlg.exec():
            save_character_traits(c.root, dlg.values())
            self._chars = list_characters()
            self._populate()

    def _new_character(self) -> None:
        dlg = NewCharacterDialog(self)
        if not dlg.exec():
            return
        name, role, ci = dlg.values()
        if not name.strip():
            return
        create_character(name.strip(), role=role.strip(), custom_instructions=ci.strip())
        self._chars = list_characters()
        self._count_lbl.setText(f"·  {len(self._chars)} characters")
        self._populate()


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
