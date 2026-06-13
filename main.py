"""Mochi root entry — JaegerApp chassis (Jaeger app format 0.1).

This file used to be the host: ~210 lines spawning a broker subprocess,
loading plugin specs, popening each plugin, polling every 5s, and
terminating the children on shutdown. Phase C of the Mochi adoption
(plan §3.2) hands all of that to the chassis:

  ``JaegerApp(PROJECT_ROOT).run()``
      ├── load manifest        jaeger.toml (declared in Phase B)
      ├── acquire instance     PID slot — second launch refuses
      ├── load config          config.yaml — behavior knobs
      ├── build bus            chassis ZMQ XPUB/XSUB broker thread
      │                        (replaces transport/broker.py subprocess)
      ├── start nodes          supervisor + subprocess backends
      │                        (replaces core/plugin_registry.py + the
      │                        Popen loop, adds systemd-style restart
      │                        policy + crash-loop protection that
      │                        run_host() never had)
      ├── start surfaces       gui.mochi_companion:run_surface as the
      │                        main Qt surface — replaces the companion
      │                        being one more subprocess plugin
      ├── run                  qt_app.exec()  (chassis owns the loop)
      └── shutdown             reverse order, signal-safe, atexit-
                               registered — windows die together,
                               broker stops, slot released

What's NOT migrated yet:
  * ``transport/node_base.py`` (MochiNodeBase) — Phase D ports it to
    ``app.node.FrameNode`` so subprocess nodes read ``JAEGER_BUS_*``
    natively. Until then the env-var translation below lets the
    chassis-launched subprocesses keep reading ``MOCHI_BROKER_*``.
  * ``transport/broker.py`` — orphaned now (chassis runs its own
    broker). Cleaned up in Phase E.
  * ``core/host_monitor.py``, ``core/plugin_registry.py`` — orphaned
    here, removed in Phase E. ``chassis.health.HealthCache`` already
    consumes ``/sys/node_health`` for "what's alive" queries.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def _bridge_legacy_env() -> None:
    """Translate Mochi's legacy env vars from config.yaml so
    pre-Phase-D nodes (animation, llm) and the companion (which still
    speaks raw addresses, not ``ctx.bus``) keep working.

    The chassis broker binds to the same ports config.yaml already
    declares, so subprocess nodes connect to the right endpoints just
    by reading the same env vars they always did."""
    cfg_path = PROJECT_ROOT / "config.yaml"
    if not cfg_path.exists():
        return
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    infra = cfg.get("infrastructure", {}) or {}

    broker = infra.get("broker") or {}
    os.environ.setdefault(
        "MOCHI_BROKER_XPUB",
        str(broker.get("frontend_addr", "tcp://127.0.0.1:5555")),
    )
    os.environ.setdefault(
        "MOCHI_BROKER_XSUB",
        str(broker.get("backend_addr", "tcp://127.0.0.1:5557")),
    )

    gui = infra.get("gui") or {}
    os.environ.setdefault(
        "MOCHI_GUI_CTRL_ADDR",
        str(gui.get("ctrl_address", "tcp://127.0.0.1:5556")),
    )

    display = infra.get("display") or {}
    os.environ.setdefault(
        "MOCHI_GUI_HEALTH_ADDR",
        str(display.get("sub_address", "tcp://127.0.0.1:5555")),
    )


def main() -> int:
    _bridge_legacy_env()
    from app import JaegerApp
    return JaegerApp(PROJECT_ROOT).run()


if __name__ == "__main__":
    raise SystemExit(main())
