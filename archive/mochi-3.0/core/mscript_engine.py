"""Re-export of the 3.0 mscript engine from where the archive kept it.

The Studio tool imports `core.mscript_engine`; archiving filed the module
under plugins/animation_node/plugin_core/ instead, so the import died and
the window never drew. This restores the link rather than editing the
tool to look somewhere its own docstring does not describe.
"""

from plugin_core.mscript_engine import *  # noqa: F401,F403
from plugin_core.mscript_engine import MscriptScript  # noqa: F401
