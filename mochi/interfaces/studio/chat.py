"""Character Chat tab — [ avatar | chat ].

Left: the AVATAR view (frames streamed by the animation node on
``/sense/avatar_frame``). Right: the rich TUI ``ChatWindow`` we already built, so
the user talks to the agent (the active character) and it works.

The avatar today is just the character's CARD — shown by routing it through the
animation node as a single held frame (the ``image`` adapter). That makes the
pipeline (node → /sense/avatar_frame → view) real from day one; richer animations
later are just different clips played on the same node.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from mochi.interfaces.avatar_player.window import AvatarView
from mochi.interfaces.studio.theme import INK_DIM, _label
from mochi.transport import topics


class ChatPage(QWidget):
    """The Character Chat surface: avatar (left) + the rich-TUI chat (right)."""

    def __init__(self, ctx: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._bus = getattr(ctx, "bus", None) if ctx is not None else None
        self._bridge: Any = None

        h = QHBoxLayout(self)
        h.setContentsMargins(18, 16, 18, 16)
        h.setSpacing(14)

        # ── avatar (left / center) ──
        stage = QFrame()
        stage.setObjectName("Stage")
        sv = QVBoxLayout(stage)
        sv.setContentsMargins(14, 12, 14, 14)
        sv.setSpacing(8)
        sv.addWidget(_label("AVATAR", color=INK_DIM, size=10, bold=True))
        self._avatar = AvatarView()
        sv.addWidget(self._avatar, stretch=1)
        h.addWidget(stage, stretch=3)

        # ── chat (right): the rich TUI ──
        if ctx is not None:
            try:
                from mochi.interfaces.pyside6.rich_tui.window import ChatWindow
                self._chat: Any = ChatWindow(ctx)
                h.addWidget(self._chat, stretch=2)
            except Exception:  # noqa: BLE001 — never let chat wiring break the tab
                h.addWidget(self._chat_placeholder(), stretch=2)
        else:
            h.addWidget(self._chat_placeholder(), stretch=2)

        # ── avatar frame stream (node → view) ──
        if self._bus is not None:
            try:
                from mochi.app.surfaces import make_bus_bridge
                self._bridge = make_bus_bridge(self._bus, [topics.SENSE_AVATAR_FRAME])
                self._bridge.message.connect(self._on_frame)
            except Exception:  # noqa: BLE001
                self._bridge = None

    # ── chat-less placeholder (standalone / no bus) ──
    def _chat_placeholder(self) -> QWidget:
        box = QFrame()
        box.setObjectName("Stage")
        v = QVBoxLayout(box)
        v.setContentsMargins(20, 20, 20, 20)
        v.addStretch(1)
        msg = _label("Chat connects when the agent is running.\n"
                     "Launch Mochi from the tray to talk.", color=INK_DIM, size=13)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        v.addWidget(msg)
        v.addStretch(1)
        return box

    # ── show the active character's card through the animation node ──
    def showEvent(self, e: Any) -> None:  # noqa: N802 — Qt override
        super().showEvent(e)
        self._show_avatar_card()

    def _show_avatar_card(self) -> None:
        card = self._active_card()
        if card is None:
            return
        # Show the card directly — reliable + immediate, and it re-reads the
        # ACTIVE character every time this tab is shown, so switching characters
        # then opening Chat updates the avatar.
        self._avatar.show_pixmap(QPixmap(str(card)))
        # Also drive it through the animation node — the real pipeline; its
        # frames replace the static card once the node renders + delivers.
        if self._bus is not None:
            self._bus.publish(topics.AnimationCommand(
                adapter="image", asset_path=str(card), duration_ms=0))

    def _active_card(self) -> Any:
        try:
            from mochi.core.instance.instance import resolve_instance_dir
            from mochi.personality.character import active_character
            ch = active_character(resolve_instance_dir())
            return ch.card_path() if ch is not None else None
        except Exception:  # noqa: BLE001
            return None

    def _on_frame(self, msg: Any) -> None:
        if getattr(msg, "topic", "") == topics.SENSE_AVATAR_FRAME:
            self._avatar.feed_frame(msg.data, msg.width, msg.height)
