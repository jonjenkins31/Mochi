"""The timeline — tracks, clips, a ruler and a playhead you can drag.

The operator half of `core/director.py`. The Director owns the clock;
this draws where it is and lets you put it somewhere else.

    ruler        0     5s     10s     15s     20s
    eric_face    ▓▓  ▓▓▓▓   ▓▓
    eric_voice       ▓▓▓▓▓▓▓
    light  ⚠     ░░    ░░           <- scheduled, dispatched nowhere

A TRACK THAT PLAYS NOWHERE IS DRAWN AS SUCH. The scheduler dispatches
animation and speech; the schema declares four more. Those clips are
hatched and their header carries a warning, because a lighting cue that
controls nothing looked exactly like one that works and that is how it
stayed broken.

DRAWN, NOT WIDGETED. A clip is a rectangle in a paint event rather than
a QWidget: a show has hundreds and the interesting operations are
hit-testing and scrubbing, neither of which wants a widget tree.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6 import QtCore, QtGui, QtWidgets

from core import director
from . import theme

HEADER_W = 132          # track-name column
RULER_H = 26
TRACK_H = 34
GAP = 3

#: Clip colour by track kind — the same categories the node view uses,
#: so a graph and a timeline read as the same vocabulary.
KIND_INK = {
    "animation": "#4a7ab0", "speech": "#3f9d6d", "script": "#8b7cff",
    "motion": "#c9873a", "light": "#c0a24a", "sound": "#3d8f95",
}


def _clock(ms: int) -> str:
    ms = max(0, int(ms))
    return f"{ms // 60000:d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


class TimelinePanel(QtWidgets.QWidget):
    """Draw a show, and scrub it."""

    def __init__(self, stage: director.Director,
                 on_pick: Callable[[Any], None] | None = None) -> None:
        super().__init__()
        self.stage = stage
        self._on_pick = on_pick or (lambda _cue: None)
        self.zoom = 0.06                 # pixels per millisecond
        self.selected: Any = None
        self._dragging = False
        self._region_from: int | None = None
        self.setMinimumHeight(RULER_H + TRACK_H * 3)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Expanding)

    # ── geometry ─────────────────────────────────────────────────

    def tracks(self) -> list:
        return list(self.stage.timeline.tracks) if self.stage.timeline else []

    def x_of(self, ms: float) -> float:
        return HEADER_W + ms * self.zoom

    def ms_at(self, x: float) -> int:
        return max(0, int((x - HEADER_W) / max(1e-6, self.zoom)))

    def row_of(self, index: int) -> int:
        return RULER_H + index * TRACK_H

    def sizeHint(self) -> QtCore.QSize:  # noqa: N802
        width = int(self.x_of(max(1000, self.stage.duration_ms)) + 40)
        return QtCore.QSize(width, RULER_H + TRACK_H * max(3, len(self.tracks())))

    def fit(self, width: int | None = None) -> None:
        """Zoom so the whole show is on screen — the default view, and
        what an operator expects a timeline to open at."""
        span = max(1, self.stage.duration_ms)
        usable = max(120, (width or self.width()) - HEADER_W - 24)
        self.zoom = usable / span
        self.updateGeometry()
        self.update()

    # ── painting ─────────────────────────────────────────────────

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        colour = theme.palette(getattr(self, "mode", theme.DEFAULT))
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(colour["sunken"]))
        dead = {name for name, _kind in self.stage.unsupported()}

        self._paint_ruler(painter, colour)
        for index, track in enumerate(self.tracks()):
            self._paint_track(painter, colour, index, track,
                              (track.name or track.kind) in dead)
        self._paint_region(painter, colour)
        self._paint_playhead(painter, colour)
        painter.end()

    def _paint_ruler(self, painter, colour) -> None:
        painter.fillRect(0, 0, self.width(), RULER_H,
                         QtGui.QColor(colour["panel"]))
        painter.setPen(QtGui.QColor(colour["rule"]))
        painter.drawLine(0, RULER_H, self.width(), RULER_H)
        # A tick every 1/2/5/10 seconds, whichever keeps them readable.
        for step in (1000, 2000, 5000, 10000, 30000):
            if step * self.zoom >= 46:
                break
        painter.setFont(QtGui.QFont("SF Mono", 8))
        at = 0
        while at <= max(self.stage.duration_ms, 1000):
            x = self.x_of(at)
            if x > self.width():
                break
            painter.setPen(QtGui.QColor(colour["rule"]))
            painter.drawLine(int(x), RULER_H - 6, int(x), RULER_H)
            painter.setPen(QtGui.QColor(colour["dim"]))
            painter.drawText(int(x) + 3, 13, f"{at // 1000}s")
            at += step

    def _paint_track(self, painter, colour, index, track, is_dead) -> None:
        top = self.row_of(index)
        painter.fillRect(0, top, HEADER_W, TRACK_H,
                         QtGui.QColor(colour["panel"]))
        painter.setPen(QtGui.QColor(colour["rule"]))
        painter.drawLine(0, top + TRACK_H, self.width(), top + TRACK_H)

        painter.setFont(QtGui.QFont("SF Mono", 9))
        painter.setPen(QtGui.QColor(colour["bad"] if is_dead else colour["ink"]))
        label = ("⚠ " if is_dead else "") + (track.name or track.kind)
        painter.drawText(8, top + 15, label[:18])
        painter.setPen(QtGui.QColor(colour["hint"]))
        painter.drawText(8, top + 28, track.kind[:18])

        ink = QtGui.QColor(KIND_INK.get(track.kind, colour["accent"]))
        for clip in track.clips:
            x = self.x_of(clip.t_offset_ms)
            width = max(3.0, clip.duration_ms * self.zoom)
            box = QtCore.QRectF(x, top + GAP, width, TRACK_H - GAP * 2 - 1)
            if is_dead:
                # Hatched: it is scheduled, and it goes nowhere.
                painter.setBrush(QtGui.QBrush(ink, QtCore.Qt.BDiagPattern))
            else:
                painter.setBrush(ink)
            selected = clip is getattr(self.selected, "clip", None)
            painter.setPen(QtGui.QPen(
                QtGui.QColor(colour["ink"] if selected else colour["sunken"]),
                2 if selected else 1))
            painter.drawRoundedRect(box, 3, 3)
            if width > 34:
                painter.setPen(QtGui.QColor("#ffffff"))
                painter.setFont(QtGui.QFont("SF Mono", 8))
                painter.drawText(
                    box.adjusted(5, 0, -3, 0), QtCore.Qt.AlignVCenter,
                    str(clip.label or self._summary(clip))[:int(width / 6)])

    @staticmethod
    def _summary(clip) -> str:
        payload = clip.payload or {}
        return str(payload.get("text") or payload.get("asset")
                   or payload.get("script") or "").split("/")[-1]

    def _paint_region(self, painter, colour) -> None:
        if self.stage.region is None:
            return
        start, end = self.stage.region
        box = QtCore.QRectF(self.x_of(start), 0,
                            max(1.0, (end - start) * self.zoom), self.height())
        painter.fillRect(box, QtGui.QColor(colour["accent"] + "22"))
        painter.setPen(QtGui.QPen(QtGui.QColor(colour["accent"]), 1,
                                  QtCore.Qt.DashLine))
        painter.drawLine(int(box.left()), 0, int(box.left()), self.height())
        painter.drawLine(int(box.right()), 0, int(box.right()), self.height())

    def _paint_playhead(self, painter, colour) -> None:
        x = int(self.x_of(self.stage.position_ms))
        painter.setPen(QtGui.QPen(QtGui.QColor(colour["bad"]), 2))
        painter.drawLine(x, 0, x, self.height())
        head = QtGui.QPolygon([QtCore.QPoint(x - 5, 0), QtCore.QPoint(x + 5, 0),
                               QtCore.QPoint(x, 9)])
        painter.setBrush(QtGui.QColor(colour["bad"]))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawPolygon(head)

    # ── interaction ──────────────────────────────────────────────

    def cue_at(self, x: float, y: float) -> Any:
        index = int((y - RULER_H) // TRACK_H)
        tracks = self.tracks()
        if not (0 <= index < len(tracks)):
            return None
        track = tracks[index]
        when = self.ms_at(x)
        for clip in track.clips:
            if clip.t_offset_ms <= when <= clip.t_offset_ms + max(
                    clip.duration_ms, 120):
                return director.Cue(int(clip.t_offset_ms), index, track.kind,
                                    track.target or "",
                                    track.name or track.kind, clip)
        return None

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        x, y = event.position().x(), event.position().y()
        if event.modifiers() & QtCore.Qt.AltModifier:
            self._region_from = self.ms_at(x)
            return
        if y <= RULER_H or x < HEADER_W:
            self._dragging = True
            self.stage.seek(self.ms_at(x))
            self.update()
            return
        cue = self.cue_at(x, y)
        self.selected = cue
        if cue is not None:
            self._on_pick(cue)
        else:
            self._dragging = True
            self.stage.seek(self.ms_at(x))
        self.update()

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        if self._dragging:
            self.stage.seek(self.ms_at(event.position().x()))
            self.update()
        elif self._region_from is not None:
            self.stage.set_region(self._region_from,
                                  self.ms_at(event.position().x()))
            self.update()

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802
        self._dragging = False
        self._region_from = None

    def wheelEvent(self, event: Any) -> None:  # noqa: N802
        """Zoom about the pointer, so the thing under the cursor stays
        under it — the one interaction every timeline has."""
        if not (event.modifiers() & (QtCore.Qt.ControlModifier
                                     | QtCore.Qt.MetaModifier)):
            return super().wheelEvent(event)
        anchor = self.ms_at(event.position().x())
        self.zoom = max(0.002, min(2.0, self.zoom * (
            1.15 if event.angleDelta().y() > 0 else 1 / 1.15)))
        self.updateGeometry()
        self.update()
        event.accept()


__all__ = ["TimelinePanel", "HEADER_W", "RULER_H", "TRACK_H", "KIND_INK"]
