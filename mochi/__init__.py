"""Mochi — a virtual character you can run.

v5 is a JaegerOS APP and owns no engine code. The face is rendered by
whichever module fills the `animation` slot; Mochi composes, shows a
window, and gets out of the way. `jaeger.toml` is the whole app.

v5.0 is a PLAYER: a character on screen and nothing else. No AI, no
microphone, no network — the same thing Mochi 3.0 was, rebuilt on the
framework. A face that works before a mind that talks.

v5.1 adds the mind and the voice as three more [[node]] blocks in
jaeger.toml. No code in this package changes when it does; that is the
test of whether the composition is real.
"""

__version__ = "5.0.0"

__all__ = ["__version__"]
