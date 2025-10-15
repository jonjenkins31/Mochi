"""
Root entry point for the Mochi host application.

The host is responsible for launching shared infrastructure (e.g. the message
broker) and spawning plugin processes such as the animation node.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

from core.host_monitor import HostMonitor
from core.plugin_registry import PluginProcess, load_plugin_specs

PROJECT_ROOT = Path(__file__).resolve().parent
BROKER_ENTRY = PROJECT_ROOT / "core" / "broker.py"
ROOT_CONFIG = PROJECT_ROOT / "config.yaml"

DEFAULT_XPUB = "tcp://127.0.0.1:5555"
DEFAULT_XSUB = "tcp://127.0.0.1:5557"
DEFAULT_CTRL = "tcp://127.0.0.1:5556"
DEFAULT_MONITOR_REP = "tcp://127.0.0.1:5560"


def _load_root_config() -> dict:
    """
    Load the shared Mochi configuration from the project root, returning an empty
    dictionary when the file does not exist or cannot be parsed.
    """
    try:
        with ROOT_CONFIG.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        print(f"Config not found at {ROOT_CONFIG}; using defaults.")
    except Exception as exc:
        print(f"Failed to read {ROOT_CONFIG}: {exc}; using defaults.")
    return {}


def launch_broker(
    python_executable: Optional[str] = None,
    *,
    xpub_addr: str,
    xsub_addr: str,
) -> subprocess.Popen:
    """
    Spawn the ZeroMQ broker that mediates between publishers and subscribers.
    """
    python = python_executable or sys.executable
    if not BROKER_ENTRY.exists():
        raise FileNotFoundError(f"Broker entry script missing: {BROKER_ENTRY}")

    broker_env = os.environ.copy()
    broker_env["MOCHI_BROKER_XPUB"] = xpub_addr
    broker_env["MOCHI_BROKER_XSUB"] = xsub_addr

    print(f"Launching Mochi broker (XPUB={xpub_addr}, XSUB={xsub_addr})")
    return subprocess.Popen(
        [python, str(BROKER_ENTRY)],
        cwd=str(BROKER_ENTRY.parent),
        env=broker_env,
    )


def run_host():
    """
    Mochi Host Application
    Launches and monitors Mochi plugins.
    """
    print("Starting Mochi Host...")
    config = _load_root_config()
    broker_cfg = config.get("broker", {}) or {}
    node_cfg = config.get("node", {}) or {}
    monitor_cfg = config.get("monitor", {}) or {}

    xpub_addr = str(broker_cfg.get("frontend_addr") or node_cfg.get("pub_address") or DEFAULT_XPUB)
    xsub_addr = str(broker_cfg.get("backend_addr") or os.environ.get("MOCHI_BROKER_XSUB") or DEFAULT_XSUB)
    ctrl_addr = str(node_cfg.get("ctrl_address") or DEFAULT_CTRL)
    node_id = str(node_cfg.get("id") or os.environ.get("MOCHI_NODE_ID") or "animation")
    monitor_rep = str(monitor_cfg.get("rep_address") or DEFAULT_MONITOR_REP)

    broker_process: Optional[subprocess.Popen] = None
    plugin_processes: list[PluginProcess] = []

    plugin_specs = load_plugin_specs(config, PROJECT_ROOT)
    if not plugin_specs:
        print("No plugins defined in config; host will still run broker and monitor.")

    monitor = HostMonitor(frontend_addr=xpub_addr, rep_addr=monitor_rep)
    monitor.start()
    print(f"Host monitor listening on {monitor_rep}")

    try:
        broker_process = launch_broker(xpub_addr=xpub_addr, xsub_addr=xsub_addr)
        for spec in plugin_specs:
            env = os.environ.copy()
            env.update({
                "MOCHI_BROKER_XPUB": xpub_addr,
                "MOCHI_BROKER_XSUB": xsub_addr,
                "MOCHI_HOST_MONITOR_REP": monitor_rep,
            })
            if spec.id:
                env.setdefault("MOCHI_NODE_ID", spec.id)
            if spec.id == node_id:
                env.setdefault("MOCHI_NODE_CTRL_ADDR", ctrl_addr)
            if spec.env:
                env.update({k: str(v) for k, v in spec.env.items()})
            if spec.config_key:
                cfg_payload = config.get(spec.config_key, {}) or {}
                env["MOCHI_PLUGIN_CONFIG_JSON"] = json.dumps({spec.config_key: cfg_payload})
            if spec.module:
                existing = env.get("PYTHONPATH")
                if existing:
                    env["PYTHONPATH"] = os.pathsep.join([str(PROJECT_ROOT), existing])
                else:
                    env["PYTHONPATH"] = str(PROJECT_ROOT)

            process = subprocess.Popen(
                spec.command(),
                cwd=str(spec.cwd),
                env=env,
            )
            plugin_processes.append(PluginProcess(spec, process))
            print(f"Plugin '{spec.id}' started with PID: {process.pid}")

        # Keep the host running, monitoring plugins
        while True:
            time.sleep(5)
            dead = [pp for pp in plugin_processes if pp.poll() is not None]
            if dead:
                for pp in dead:
                    print(f"Plugin '{pp.spec.id}' exited with code {pp.poll()}")
                break
    except KeyboardInterrupt:
        print("Host interrupted; shutting down.")
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
    except Exception as exc:
        print(f"An error occurred while running the host: {exc}")
    finally:
        for plugin_proc in plugin_processes:
            if plugin_proc.poll() is None:
                print(f"Shutting down plugin '{plugin_proc.spec.id}'...")
                plugin_proc.terminate()
                try:
                    plugin_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"Plugin '{plugin_proc.spec.id}' did not exit promptly; forcing shutdown.")
                    plugin_proc.kill()

        if broker_process and broker_process.poll() is None:
            print("Shutting down Mochi broker...")
            broker_process.terminate()
            try:
                broker_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Broker did not exit promptly; forcing shutdown.")
                broker_process.kill()

        monitor.stop()
        monitor.join(timeout=2)


def main():
    run_host()


if __name__ == "__main__":
    main()
