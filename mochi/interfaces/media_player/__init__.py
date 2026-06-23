"""Mochi media player — play an image / gif / video in a floating window.

The mochi-v4 "play a specific file in a floating window" function, on
Qt-native rendering (QPixmap / QMovie / QMediaPlayer). :class:`MediaView` is
the embeddable surface (used by the Studio Media tab);
:class:`FloatingMediaPlayer` wraps it in a frameless draggable window.

A new bus surface — it changes nothing in the core; ``make_surface`` is the
only bus coupling (renders whatever the media node says is playing).
"""

from __future__ import annotations
