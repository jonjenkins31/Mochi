"""Mochi's own library code.

The project tier: what THIS app needs and no module provides. Today
that is one thing — reading a character pack (`characters.py`).

Named `core/` to match JP01-CC01, because two projects built alike is
what makes a layout a standard rather than a pair of one-offs.

Not a distributable package. Mochi is a WORKSPACE you run from its own
directory, the way a ROS workspace is: `python3 main.py`, with the
project root on `sys.path`. That is why `core` and `interfaces` can
have generic names — they never enter anyone's site-packages, so there
is nothing to collide with.

No `__version__` here: the app's version lives in `jaeger.toml`, and a
second copy would be one more thing to forget.
"""
