"""Animation adapters — the procedural avatar adapter.

The file-decoder adapters (image / gif / video / bitmap / sprite) moved to the
media node (``mochi.nodes.media.decoders``) — media owns asset->frame decoding,
and the animation node imports them (registered at L1-L4 in mochi.nodes.runtime).
What stays here is the procedural layer: ``MathScript`` faces rendered in code.

  L4  PROCEDURAL   MathAdapter (+ MathScript base)
  L1-L3 / video    -> mochi.nodes.media.decoders
"""

from .math_adapter import MathAdapter, MathScript

__all__ = ["MathAdapter", "MathScript"]
