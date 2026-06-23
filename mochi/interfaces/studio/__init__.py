"""Mochi Studio — the main desktop surface.

A NEW bus surface (a peer of ``rich_tui.window`` and ``tray``). It plugs into
the same event gateway and changes NOTHING in the agent core, the bus, or the
existing surfaces — "transports, not endpoints". The window widget is
bus-agnostic (pure view); :func:`make_surface` is the thin connector that
subscribes it to the bus.

Preview the UI with no model/instance/bus:
    python -m mochi.interfaces.studio
"""

from __future__ import annotations
