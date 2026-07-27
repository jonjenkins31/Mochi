"""Mochi's own library code.

The project tier: what THIS app needs and no module provides — reading
a character pack, and (later) whatever policy turns a conversation into
a face. Named `core/` to match JP01-CC01, because two projects built
alike is what makes a layout a standard.

Not a distributable package. Mochi is a WORKSPACE you run from its own
directory, the way a ROS workspace is — `python3 main.py`, with the
project root on sys.path. That is why `core` and `interfaces` can have
generic names: they are never installed into anyone's site-packages,
so there is nothing to collide with.
"""

__version__ = "5.0.0"

__all__ = ["__version__"]
