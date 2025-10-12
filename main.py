"""
Root entry point for the Mochi host application.

The host is responsible for launching shared infrastructure (e.g. the message
broker) and spawning plugin processes such as the animation node.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent
ANIMATION_NODE_ENTRY = PROJECT_ROOT / "plugins" / "animation_node" / "main.py"
BROKER_ENTRY = PROJECT_ROOT / "core" / "broker.py"
ROOT_CONFIG = PROJECT_ROOT / "config.yaml"

DEFAULT_XPUB = "tcp://127.0.0.1:5555"
DEFAULT_XSUB = "tcp://127.0.0.1:5557"
DEFAULT_CTRL = "tcp://127.0.0.1:5556"


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


def launch_animation_node(
    python_executable: Optional[str] = None,
    *,
    extra_env: Optional[dict[str, str]] = None,
) -> subprocess.Popen:
    """
    Spawn the animation node plugin as a subprocess and return the handle.
    """
    python = python_executable or sys.executable
    if not ANIMATION_NODE_ENTRY.exists():
        raise FileNotFoundError(f"Animation node entry script missing: {ANIMATION_NODE_ENTRY}")

    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    print(f"Launching Animation Node plugin from: {ANIMATION_NODE_ENTRY}")
    return subprocess.Popen(
        [python, str(ANIMATION_NODE_ENTRY)],
        cwd=str(ANIMATION_NODE_ENTRY.parent),
        env=env,
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

    xpub_addr = str(broker_cfg.get("frontend_addr") or node_cfg.get("pub_address") or DEFAULT_XPUB)
    xsub_addr = str(broker_cfg.get("backend_addr") or os.environ.get("MOCHI_BROKER_XSUB") or DEFAULT_XSUB)
    ctrl_addr = str(node_cfg.get("ctrl_address") or DEFAULT_CTRL)

    broker_process: Optional[subprocess.Popen] = None
    plugin_process: Optional[subprocess.Popen] = None

    try:
        broker_process = launch_broker(xpub_addr=xpub_addr, xsub_addr=xsub_addr)
        plugin_env = {
            "MOCHI_BROKER_XPUB": xpub_addr,
            "MOCHI_BROKER_XSUB": xsub_addr,
            "MOCHI_NODE_CTRL_ADDR": ctrl_addr,
        }
        plugin_process = launch_animation_node(extra_env=plugin_env)
        print(f"Animation Node plugin started with PID: {plugin_process.pid}")

        # Keep the host running, monitoring the plugin
        while True:
            time.sleep(5)
            if plugin_process.poll() is not None:
                print("Animation Node plugin has terminated.")
                break
    except KeyboardInterrupt:
        print("Host interrupted; shutting down.")
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
    except Exception as exc:
        print(f"An error occurred while running the host: {exc}")
    finally:
        if plugin_process and plugin_process.poll() is None:
            print("Shutting down Animation Node plugin...")
            plugin_process.terminate()
            try:
                plugin_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Plugin did not exit promptly; forcing shutdown.")
                plugin_process.kill()

        if broker_process and broker_process.poll() is None:
            print("Shutting down Mochi broker...")
            broker_process.terminate()
            try:
                broker_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Broker did not exit promptly; forcing shutdown.")
                broker_process.kill()


def main():
    run_host()


if __name__ == "__main__":
    main()
