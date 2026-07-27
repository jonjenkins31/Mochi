"""Basic smoke checks for Mochi configuration and plugin registry."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    config_path = project_root / "config.yaml"
    if not config_path.exists():
        print(f"Missing config: {config_path}")
        return 1

    with config_path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}

    # Ensure broker and monitor addresses exist
    broker = config.get("broker") or {}
    monitor = config.get("monitor") or {}
    if "frontend_addr" not in broker or "backend_addr" not in broker:
        print("Broker addresses incomplete in config.yaml")
        return 1
    if "rep_address" not in monitor:
        print("Monitor REP address missing in config.yaml")
        return 1

    ok = True
    for plugin in config.get("plugins", []) or []:
        entry = plugin.get("entry")
        module = plugin.get("module")
        pid = plugin.get("id")
        if not pid:
            print("Plugin entry missing 'id'")
            ok = False
            continue
        if not entry and not module:
            print(f"Plugin '{pid}' missing 'entry' or 'module'")
            ok = False
            continue
        if entry:
            entry_path = (project_root / entry).resolve()
            if not entry_path.exists():
                print(f"Plugin '{pid}' entry not found: {entry_path}")
                ok = False
        cwd = plugin.get("cwd")
        if cwd:
            cwd_path = (project_root / cwd).resolve()
            if not cwd_path.exists():
                print(f"Plugin '{pid}' cwd not found: {cwd_path}")
                ok = False
    if not ok:
        return 1

    print("Configuration smoke check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
