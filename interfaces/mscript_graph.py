"""The node view of a motion script — the same document, drawn.

A motion script is a PROGRAM, not a free-form graph: the engine walks it
top to bottom and `JMP` is the only thing that moves the counter. So the
canvas is a chain, and the one edge that is not "the next line" is a jump
back to its label — drawn on the right, where it reads as the loop it is.

Anything else would be a lie about what plays. A free 2D web of nodes
implies an execution order the engine does not have, and the first time
someone wired two branches they would find only one of them ever ran.

Nothing here parses or renders a script: it edits ``Step`` objects from
`mscript_editor`, which are the `[Main]` lines themselves. Save, Play,
Resources and the live preview never learn this view exists.

The language it draws is documented with the engine that runs it —
JaegerAnimation, ``jaeger_animation/docs/MSCRIPT.md``.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6 import QtCore, QtGui, QtWidgets

from .mscript_editor import Step, build_steps, parse_steps

NODE_W, NODE_H, GAP, MARGIN = 250, 62, 30, 24

#: command -> (accent, the arguments worth offering for it).
#: Straight from the engine's own dispatch table; a command missing here
#: still works, it just draws as unknown rather than getting a form.
COMMANDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "MATH":    ("#4a7ab0", ("K", "D", "EVENT", "FG", "BG")),
    "BITMAP":  ("#4a7ab0", ("K", "D", "FG", "BG")),
    "SPRITE":  ("#4a7ab0", ("K", "D", "SRC", "BG")),
    "MEDIA":   ("#4a7ab0", ("K", "D", "SPD", "FIT", "LOOP", "BG")),
    "IMAGE":   ("#4a7ab0", ("K", "D", "FIT", "BG")),
    "GIF":     ("#4a7ab0", ("K", "D", "SPD", "LOOP", "BG")),
    "VIDEO":   ("#4a7ab0", ("K", "D", "SPD", "FIT", "LOOP", "BG")),
    "MSCRIPT": ("#4a7ab0", ("K", "D")),
    "WAIT":    ("#5a6a80", ("D",)),
    "LBL":     ("#4f9d69", ("LBL",)),
    "JMP":     ("#c08a3e", ("LBL",)),
}

#: What a freshly added node starts as. A node with no arguments at all
#: is a node the engine skips, which reads as the editor being broken.
DEFAULTS = {
    "MATH": {"K": "1", "D": "1.0"}, "BITMAP": {"K": "1", "D": "1.0"},
    "SPRITE": {"K": "1", "D": "1.0", "SRC": "0,0,64,64"},
    "MEDIA": {"K": "1", "D": "auto"}, "IMAGE": {"K": "1", "D": "1.0"},
    "GIF": {"K": "1", "D": "auto"}, "VIDEO": {"K": "1", "D": "auto"},
    "MSCRIPT": {"K": "1", "D": "1.0"}, "WAIT": {"D": "0.5"},
    "LBL": {"LBL": "1"}, "JMP": {"LBL": "1"},
}

_UNKNOWN = "#a05050"
_NOTE = "#5a5a66"


def _accent(step: Step) -> str:
    if step.is_note:
        return _NOTE
    return COMMANDS.get(step.command, (_UNKNOWN, ()))[0]


class _StepItem(QtWidgets.QGraphicsItem):
    """One line of the program, as a card you can grab."""

    def __init__(self, step: Step, index: int, graph: "MscriptGraph") -> None:
        super().__init__()
        self.step, self.index, self._graph = step, index, graph
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsMovable
            | QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(1)

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(0, 0, NODE_W, NODE_H)

    def itemChange(self, change, value):
        # Vertical only. The order IS the program, so sideways travel
        # would be decoration that means nothing — and a node dragged
        # off to one side still runs exactly where it always did.
        if change == QtWidgets.QGraphicsItem.ItemPositionChange:
            return QtCore.QPointF(MARGIN, value.y())
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self._graph.reorder_from(self)

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        accent = QtGui.QColor(_accent(self.step))
        body = QtCore.QRectF(0, 0, NODE_W, NODE_H)
        painter.setBrush(QtGui.QColor("#1e1e26"))
        painter.setPen(QtGui.QPen(
            accent.lighter(140) if self.isSelected() else QtGui.QColor("#33333f"),
            2 if self.isSelected() else 1))
        painter.drawRoundedRect(body, 6, 6)

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(QtCore.QRectF(0, 0, 6, NODE_H), 3, 3)

        if self.step.is_note:
            painter.setPen(QtGui.QColor(_NOTE))
            font = painter.font()
            font.setItalic(True)
            painter.setFont(font)
            painter.drawText(
                QtCore.QRectF(16, 0, NODE_W - 24, NODE_H),
                QtCore.Qt.AlignVCenter,
                (self.step.raw.strip() or "(blank line)")[:40])
            return

        painter.setPen(QtGui.QColor("#e0e0e8"))
        title = painter.font()
        title.setBold(True)
        # A font defined by PIXEL size reports pointSize() == -1, and
        # setPointSize(0) is a Qt warning per node per repaint. Bold is
        # the part that matters; the extra point is a nicety.
        if title.pointSize() > 0:
            title.setPointSize(title.pointSize() + 1)
        painter.setFont(title)
        painter.drawText(QtCore.QRectF(16, 6, NODE_W - 24, 22),
                         QtCore.Qt.AlignVCenter, self._title())

        painter.setPen(QtGui.QColor("#8a8a98"))
        painter.setFont(QtGui.QFont("Menlo", 10))
        painter.drawText(QtCore.QRectF(16, 30, NODE_W - 24, 26),
                         QtCore.Qt.AlignVCenter, self._subtitle())

    def _title(self) -> str:
        if self.step.command == "LBL":
            return f"LBL[{self.step.args.get('LBL', '?')}]"
        known = self.step.command in COMMANDS
        return self.step.command + ("" if known else "  (unknown)")

    def _subtitle(self) -> str:
        shown = [f"{k}[{v}]" for k, v in self.step.args.items()
                 if not (self.step.command == "LBL" and k == "LBL")]
        return "  ".join(shown)[:38] or "—"


class MscriptGraph(QtWidgets.QWidget):
    """Edit a list of ``Step`` as a chain of nodes."""

    def __init__(self, on_changed: Callable[[], None]) -> None:
        super().__init__()
        self._steps: list[Step] = []
        self._items: list[_StepItem] = []
        self._on_changed = on_changed
        self._fields: dict[str, QtWidgets.QLineEdit] = {}
        self._selected: int | None = None
        self._syncing = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        bar = QtWidgets.QHBoxLayout()
        self.palette_box = QtWidgets.QComboBox()
        self.palette_box.addItems(list(COMMANDS))
        bar.addWidget(QtWidgets.QLabel("Add"))
        bar.addWidget(self.palette_box)
        for label, slot in (("＋", self.add_step), ("▲", self.move_up),
                            ("▼", self.move_down), ("✕", self.delete_step)):
            button = QtWidgets.QPushButton(label)
            button.setFixedWidth(34)
            button.clicked.connect(slot)
            bar.addWidget(button)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.scene = QtWidgets.QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._selection_changed)
        self.view = QtWidgets.QGraphicsView(self.scene)
        self.view.setRenderHint(QtGui.QPainter.Antialiasing)
        self.view.setBackgroundBrush(QtGui.QColor("#0b0b0e"))
        layout.addWidget(self.view, 1)

        self.form_box = QtWidgets.QGroupBox("Step")
        self.form = QtWidgets.QFormLayout(self.form_box)
        self.form_box.setMaximumHeight(190)
        layout.addWidget(self.form_box)

    # ── the document ─────────────────────────────────────────────

    def set_text(self, main: str) -> None:
        """Draw what the text editor currently holds."""
        self._steps = parse_steps(main.splitlines())
        self._selected = None
        self._rebuild()

    def text(self) -> str:
        return build_steps(self._steps)

    def _changed(self) -> None:
        self._rebuild()
        self._on_changed()

    # ── drawing ──────────────────────────────────────────────────

    def _rebuild(self) -> None:
        self._syncing = True
        self.scene.clear()
        self._items = []
        for index, step in enumerate(self._steps):
            item = _StepItem(step, index, self)
            item.setPos(MARGIN, MARGIN + index * (NODE_H + GAP))
            self.scene.addItem(item)
            self._items.append(item)
        self._draw_flow()
        self._draw_jumps()
        height = MARGIN * 2 + max(1, len(self._steps)) * (NODE_H + GAP)
        self.scene.setSceneRect(0, 0, NODE_W + MARGIN * 4, height)
        if self._selected is not None and self._selected < len(self._items):
            self._items[self._selected].setSelected(True)
        self._syncing = False
        self._build_form()

    def _draw_flow(self) -> None:
        pen = QtGui.QPen(QtGui.QColor("#33333f"), 2)
        for index in range(len(self._items) - 1):
            top = MARGIN + index * (NODE_H + GAP) + NODE_H
            line = self.scene.addLine(
                MARGIN + NODE_W / 2, top, MARGIN + NODE_W / 2, top + GAP, pen)
            line.setZValue(0)

    def _draw_jumps(self) -> None:
        """Every JMP gets an edge to its LBL — or a red stub if the label
        is missing, which is exactly the typo the engine warns about at
        runtime and nothing showed you before."""
        labels = {step.label(): index
                  for index, step in enumerate(self._steps)
                  if step.command == "LBL" and step.label() is not None}
        for index, step in enumerate(self._steps):
            if step.command != "JMP":
                continue
            target = labels.get(step.label())
            y_from = MARGIN + index * (NODE_H + GAP) + NODE_H / 2
            if target is None:
                pen = QtGui.QPen(QtGui.QColor(_UNKNOWN), 2, QtCore.Qt.DashLine)
                stub = self.scene.addLine(
                    MARGIN + NODE_W, y_from, MARGIN + NODE_W + 26, y_from, pen)
                stub.setZValue(0)
                continue
            y_to = MARGIN + target * (NODE_H + GAP) + NODE_H / 2
            bulge = MARGIN + NODE_W + 26 + abs(index - target) * 6
            path = QtGui.QPainterPath(QtCore.QPointF(MARGIN + NODE_W, y_from))
            path.cubicTo(bulge, y_from, bulge, y_to, MARGIN + NODE_W, y_to)
            edge = self.scene.addPath(
                path, QtGui.QPen(QtGui.QColor("#c08a3e"), 2))
            edge.setZValue(0)

    # ── editing ──────────────────────────────────────────────────

    def reorder_from(self, item: _StepItem) -> None:
        """Turn where a node was dropped into where it runs."""
        slot = round((item.pos().y() - MARGIN) / (NODE_H + GAP))
        slot = max(0, min(len(self._steps) - 1, int(slot)))
        if slot == item.index:
            self._rebuild()          # snap it back onto the rail
            return
        step = self._steps.pop(item.index)
        self._steps.insert(slot, step)
        self._selected = slot
        self._changed()

    def add_step(self) -> None:
        command = self.palette_box.currentText()
        step = Step(command=command)
        step.retype(command, DEFAULTS.get(command, {}))
        at = len(self._steps) if self._selected is None else self._selected + 1
        self._steps.insert(at, step)
        self._selected = at
        self._changed()

    def delete_step(self) -> None:
        if self._selected is None:
            return
        del self._steps[self._selected]
        self._selected = min(self._selected, len(self._steps) - 1) or None
        self._changed()

    def move_up(self) -> None:
        self._nudge(-1)

    def move_down(self) -> None:
        self._nudge(1)

    def _nudge(self, delta: int) -> None:
        if self._selected is None:
            return
        target = self._selected + delta
        if not 0 <= target < len(self._steps):
            return
        steps = self._steps
        steps[self._selected], steps[target] = steps[target], steps[self._selected]
        self._selected = target
        self._changed()

    # ── the selected step's arguments ────────────────────────────

    def _selection_changed(self) -> None:
        if self._syncing:
            return
        chosen = [i for i in self.scene.selectedItems() if isinstance(i, _StepItem)]
        self._selected = chosen[0].index if chosen else None
        self._build_form()

    def _build_form(self) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        self._fields = {}
        if self._selected is None or self._selected >= len(self._steps):
            self.form_box.setTitle("Step — nothing selected")
            return
        step = self._steps[self._selected]
        if step.is_note:
            self.form_box.setTitle("Comment")
            edit = QtWidgets.QLineEdit(step.raw)
            edit.editingFinished.connect(self._note_edited)
            self._fields["_raw"] = edit
            self.form.addRow("Text", edit)
            return

        self.form_box.setTitle(f"Step {self._selected + 1} — {step.command}")
        known = COMMANDS.get(step.command, (None, ()))[1]
        # The arguments it HAS first, in the order written, then the ones
        # this command accepts and does not have yet — so a blank row is
        # an offer rather than a mystery.
        for key in list(step.args) + [k for k in known if k not in step.args]:
            edit = QtWidgets.QLineEdit(step.args.get(key, ""))
            edit.setPlaceholderText("unset")
            edit.editingFinished.connect(self._args_edited)
            self._fields[key] = edit
            self.form.addRow(key, edit)

    def _note_edited(self) -> None:
        if self._selected is None:
            return
        self._steps[self._selected].raw = self._fields["_raw"].text()
        self._changed()

    def _args_edited(self) -> None:
        if self._selected is None:
            return
        step = self._steps[self._selected]
        args = {key: field.text().strip()
                for key, field in self._fields.items() if field.text().strip()}
        if args == step.args:
            return                   # focus moved, nothing was typed
        step.retype(step.command, args)
        self._changed()


__all__ = ["MscriptGraph", "COMMANDS"]
