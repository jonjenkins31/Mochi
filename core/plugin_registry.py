"""Plugin discovery and lifecycle helpers for Mochi host."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional


@dataclass
class PluginSpec:
    """Describes how to launch a plugin as a subprocess."""

    id: str
    entry: Path
    cwd: Path
    config_key: Optional[str] = None
    type: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    args: Optional[Iterable[str]] = None

    def command(self, python_executable: Optional[str] = None) -> list[str]:
        python = python_executable or sys.executable
        cmd = [python, str(self.entry)]
        if self.args:
            cmd.extend(map(str, self.args))
        return cmd


class PluginProcess:
    """Wrapper around a plugin subprocess with convenience helpers."""

    def __init__(self, spec: PluginSpec, process: subprocess.Popen[bytes]):
        self.spec = spec
        self.process = process

    def poll(self) -> Optional[int]:
        return self.process.poll()

    def terminate(self) -> None:
        self.process.terminate()

    def kill(self) -> None:
        self.process.kill()

    def wait(self, timeout: Optional[float] = None) -> Optional[int]:
        return self.process.wait(timeout=timeout)


def load_plugin_specs(config: dict, project_root: Path) -> list[PluginSpec]:
    specs: list[PluginSpec] = []
    for item in config.get("plugins", []) or []:
        entry = Path(project_root, item.get("entry", "")).resolve()
        cwd = Path(project_root, item.get("cwd", entry.parent)).resolve()
        spec = PluginSpec(
            id=str(item.get("id")),
            entry=entry,
            cwd=cwd,
            config_key=item.get("config_key"),
            type=item.get("type"),
            args=item.get("args"),
            env=item.get("env"),
        )
        specs.append(spec)
    return specs
