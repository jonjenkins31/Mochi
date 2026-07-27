"""Windowed-app entry — what ``python main.py`` runs (Pattern 1).

Boots JROS's PySide6 chat window + menu-bar tray through the chassis
``JaegerApp`` with a Tier-1 ``[core]``. All the substance — the model
boot, the bus bridge, teardown order — lives in the core
(``mochi.agent.loop.agent_core:AgentCore``) and the surfaces. This
module only points the chassis at ``mochi.windowed.toml`` and runs it,
so there is ONE app/host (the chassis), no second ``JaegerApp`` class.

The instance is resolved by ``boot_for_tui`` from ``JAEGER_INSTANCE_NAME``
(resolved from .mochi/active_instance), so no ``--instance`` plumbing.
"""

from __future__ import annotations

import pathlib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_MANIFEST = _REPO_ROOT / "mochi.windowed.toml"


def main() -> int:
    from mochi.app import JaegerApp
    from mochi.core.messages import MESSAGES

    return JaegerApp(_MANIFEST, registry=MESSAGES).run()


if __name__ == "__main__":
    raise SystemExit(main())
