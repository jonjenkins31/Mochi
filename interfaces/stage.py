"""Stage — the character in the middle, and everything you can do to it.

    triggers ─┐                          ┌─ what it did
              ├──▶  the character  ◀─────┤
    a line ───┘      (live frames)       └─ what it heard

This is the proof-of-concept surface for CONTROL. Every other tab shows
one subsystem; this one shows a character being driven — a scene fired
from a button, a line typed straight to the mind, an expression forced
by hand — with the face big in the middle so you can see whether it
worked.

WHY THE TRIGGERS ARE A LIST AND NOT A MENU. A performance you cannot
start in one click is a performance nobody demos. Each button is a whole
scene; the log beside it says which step is running, because a scene
that is waiting for you to answer looks exactly like one that has hung.

TALKING TO IT IS TWO DIFFERENT THINGS, and the split matters:

    Say to Mochi   → the mind. An LLM turn, answered in character.
    Answer         → the SCENE. Satisfies a LISTEN step.

The same words mean different things depending on whether a scene is
waiting, so the box relabels itself rather than guessing.
"""

from __future__ import annotations

import pathlib
from typing import Any

from jaeger_os import topics

from core import expressive, scenes as scene_lib
from modules import jaeger_agent as mind
from modules import jaeger_animation as animation
from modules import jaeger_kokoro_tts as tts

_FRAME = topics.ACT_DISPLAY_FRAME


def load_scenes(character: Any) -> tuple:
    """The character's repertoire: its own mscripts/, nothing else.

    Performances are DATA saved with the character, so they are the same
    files the MScript Editor opens and the node graph draws. Nothing
    here is code — an author writes a scene without touching Python.
    """
    return scene_lib.available(character)


class StageTab:
    """Drive a character: scenes, expressions, and a line to the mind."""

    def __init__(self, app: Any, qt: tuple) -> None:
        QtCore, QtGui, QtWidgets = qt
        self._QtCore, self._QtGui, self._QtWidgets = QtCore, QtGui, QtWidgets
        self.app = app
        self.bus = app.bus
        self._frame = None
        self._pending: list[str] = []
        self.character = animation.load("bitmap_man")
        self.runner = scene_lib.SceneRunner(
            app, self.character, on_event=self._pending.append)

        self.widget = QtWidgets.QWidget()
        root = QtWidgets.QHBoxLayout(self.widget)
        root.setContentsMargins(8, 8, 8, 8)

        # ── left: what you can trigger ──
        left = QtWidgets.QVBoxLayout()
        self.pack_box = QtWidgets.QComboBox()
        self.pack_box.addItems(animation.available())
        self.pack_box.setCurrentText(self.character.name)
        self.pack_box.currentTextChanged.connect(self._pack_picked)
        left.addWidget(QtWidgets.QLabel("character"))
        left.addWidget(self.pack_box)

        self.triggers = QtWidgets.QGroupBox("Scenes")
        self.trigger_layout = QtWidgets.QVBoxLayout(self.triggers)
        left.addWidget(self.triggers)

        self.expressions = QtWidgets.QGroupBox("Expressions")
        self.expression_layout = QtWidgets.QVBoxLayout(self.expressions)
        left.addWidget(self.expressions)

        stop = QtWidgets.QPushButton("■ Stop")
        stop.clicked.connect(self.stop)
        left.addWidget(stop)
        left.addStretch(1)
        root.addLayout(left)

        # ── middle: the character ──
        middle = QtWidgets.QVBoxLayout()
        self.screen = QtWidgets.QLabel("press a scene")
        self.screen.setAlignment(QtCore.Qt.AlignCenter)
        self.screen.setMinimumSize(380, 380)
        self.screen.setStyleSheet("background:#000; border:1px solid #22222c;")
        middle.addWidget(self.screen, 1)

        self.status = QtWidgets.QLabel("idle")
        self.status.setStyleSheet("color:#8aaad0;")
        middle.addWidget(self.status)

        row = QtWidgets.QHBoxLayout()
        self.entry = QtWidgets.QLineEdit()
        self.entry.returnPressed.connect(self.send)
        self.send_button = QtWidgets.QPushButton("Say")
        self.send_button.clicked.connect(self.send)
        row.addWidget(self.entry, 1)
        row.addWidget(self.send_button)
        middle.addLayout(row)
        root.addLayout(middle, 1)

        # ── right: what happened ──
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(400)
        self.log.setMinimumWidth(300)
        self.log.setPlaceholderText(
            "every step a scene runs, in order.\n\n"
            "A scene that says `listen …` is waiting for YOU — answer it "
            "in the box, or out loud if the mic is on.")
        root.addWidget(self.log)

        self._rebuild_for_character()
        self._teach_faces()
        self.bus.subscribe(_FRAME, self._on_frame)
        self.bus.subscribe(mind.CHAT_REPLY, self._on_reply)
        self._timer = QtCore.QTimer(self.widget)
        self._timer.timeout.connect(self._drain)
        self._timer.start(33)

    # ── building ─────────────────────────────────────────────────

    def _rebuild_for_character(self) -> None:
        QtWidgets = self._QtWidgets
        for layout in (self.trigger_layout, self.expression_layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        self.scenes = load_scenes(self.character)
        for scene in self.scenes:
            button = QtWidgets.QPushButton(
                f"▶ {scene.name}" + ("  ⟳" if scene.loop else ""))
            button.setToolTip(scene.description + (
                "\n\nWaits for you to answer." if scene.interactive else ""))
            button.clicked.connect(
                lambda _c=False, s=scene: self.play(s))
            self.trigger_layout.addWidget(button)
        if not self.scenes:
            note = QtWidgets.QLabel("no scenes.py in this pack")
            note.setStyleSheet("color:#6a6a78;")
            self.trigger_layout.addWidget(note)

        for expression in self.character.expressions:
            button = QtWidgets.QPushButton(expression)
            button.clicked.connect(
                lambda _c=False, e=expression: self.show(e))
            self.expression_layout.addWidget(button)

    def _pack_picked(self, name: str) -> None:
        self.stop()
        try:
            self.character = animation.load(name)
        except Exception as exc:  # noqa: BLE001
            self._pending.append(f"! {exc}")
            return
        self.runner = scene_lib.SceneRunner(
            self.app, self.character, on_event=self._pending.append)
        self._rebuild_for_character()
        self._teach_faces()

    def _teach_faces(self) -> None:
        """Tell the mind which faces this character has.

        One line of prompt, versus ~3,600 tokens for even a scoped tool
        catalogue. Appended to the persona rather than replacing it, so
        a character keeps its voice and gains a face.
        """
        from core import persona

        sheet = persona.read(pathlib.Path(self.character.root))
        base = persona.compose(sheet) if sheet.get("prompt") else ""
        mind.set_persona(self.app, expressive.prompt_for(self.character, base))

    # ── driving it ───────────────────────────────────────────────

    def play(self, scene: Any) -> None:
        self._pending.append(f"▶ {scene.name}")
        self.runner.start(scene)

    def stop(self) -> None:
        self.runner.stop()
        animation.stop(self.bus)

    def show(self, expression: str) -> None:
        """Force one expression by hand — the smallest possible trigger."""
        self.runner.stop()
        try:
            animation.play(self.bus, self.character, expression)
            self._pending.append(f"face  {expression}")
        except Exception as exc:  # noqa: BLE001
            self._pending.append(f"! {exc}")

    def send(self) -> None:
        """The same box means two things, and which one depends on
        whether a scene is holding a LISTEN open."""
        text = self.entry.text().strip()
        if not text:
            return
        self.entry.clear()
        if self.runner.running:
            self._pending.append(f"you   {text!r}")
            self.runner.heard(text)
        else:
            self._pending.append(f"you   {text!r}  → the mind")
            mind.ask(self.bus, text, session="stage")

    # ── bus thread ───────────────────────────────────────────────

    def _on_frame(self, msg: Any) -> None:
        if not msg.data or msg.width <= 0 or msg.height <= 0:
            return
        image = self._QtGui.QImage(
            bytes(msg.data), msg.width, msg.height, msg.width * 4,
            self._QtGui.QImage.Format_RGBA8888)
        self._frame = image.copy()

    def _on_reply(self, msg: Any) -> None:
        """The mind answered. A plain chat model has no tools, so the
        only way it can drive the FACE is a marker in the text — see
        core/expressive.py. Applied here and stripped before speaking."""
        expression, line = expressive.split(
            str(getattr(msg, "text", "")), self.character.expressions)
        if expression:
            self._pending.append(f"face  {expression}   (from the reply)")
            try:
                animation.play(self.bus, self.character, expression)
            except Exception:  # noqa: BLE001
                pass
        self._pending.append(f"mochi {line!r}")
        if line and tts.audible(self.app):
            tts.say(self.bus, line, voice=tts.voice(self.app))

    # ── GUI thread ───────────────────────────────────────────────

    def _drain(self) -> None:
        while self._pending:
            self.log.appendPlainText(self._pending.pop(0))
        running = self.runner.running
        scene = self.runner.scene
        self.status.setText(
            f"playing: {scene.name}" if running and scene else "idle")
        self.send_button.setText("Answer" if running else "Say")
        self.entry.setPlaceholderText(
            "answer the scene…" if running else "say something to the mind…")
        frame, self._frame = self._frame, None
        if frame is not None:
            self.screen.setPixmap(self._QtGui.QPixmap.fromImage(frame).scaled(
                self.screen.size(), self._QtCore.Qt.KeepAspectRatio,
                self._QtCore.Qt.FastTransformation))

    def close(self) -> None:
        self._timer.stop()
        self.runner.stop()
        for topic, handler in ((_FRAME, self._on_frame),
                               (mind.CHAT_REPLY, self._on_reply)):
            try:
                self.bus.unsubscribe(topic, handler)
            except Exception:  # noqa: BLE001
                pass


__all__ = ["StageTab", "load_scenes"]
