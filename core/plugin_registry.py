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
    cwd: Path
    entry: Optional[Path] = None
    module: Optional[str] = None
    config_key: Optional[str] = None
    type: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    args: Optional[Iterable[str]] = None
    enabled: bool = True
    config_path: Optional[Path] = None

    def command(self, python_executable: Optional[str] = None) -> list[str]:
        python = python_executable or sys.executable
        if self.module:
            cmd = [python, "-m", self.module]
        elif self.entry:
            cmd = [python, str(self.entry)]
        else:
            raise ValueError(f"Plugin '{self.id}' missing module/entry")
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
        entry_value = item.get("entry")
        module_value = item.get("module")
        entry_path = Path(project_root, entry_value).resolve() if entry_value else None
        if entry_path is None and not module_value:
            raise ValueError(f"Plugin config for '{item}' missing 'entry' or 'module'")
        if "cwd" in item and item["cwd"] is not None:
            cwd = Path(project_root, item["cwd"]).resolve()
        elif entry_path is not None:
            cwd = entry_path.parent
        else:
            cwd = project_root
        config_path_value = item.get("config_path")
        config_path = None
        if config_path_value:
            config_path = Path(project_root, config_path_value).resolve()
        spec = PluginSpec(
            id=str(item.get("id")),
            cwd=cwd,
            entry=entry_path,
            module=item.get("module"),
            config_key=item.get("config_key"),
            type=item.get("type"),
            args=item.get("args"),
            env=item.get("env"),
            enabled=bool(item.get("enabled", True)),
            config_path=config_path,
        )
        specs.append(spec)
    return specs
