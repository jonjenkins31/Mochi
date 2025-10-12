
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANIMATION_NODE_ENTRY = PROJECT_ROOT / "plugins" / "animation_node" / "main.py"


def launch_animation_node(python_executable: Optional[str] = None) -> subprocess.Popen:
    """
    Spawn the animation node plugin as a subprocess and return the handle.
    """
    python = python_executable or sys.executable
    if not ANIMATION_NODE_ENTRY.exists():
        raise FileNotFoundError(f"Animation node entry script missing: {ANIMATION_NODE_ENTRY}")

    print(f"Launching Animation Node plugin from: {ANIMATION_NODE_ENTRY}")
    return subprocess.Popen(
        [python, str(ANIMATION_NODE_ENTRY)],
        cwd=str(ANIMATION_NODE_ENTRY.parent),
    )


def run_host():
    """
    Mochi Host Application
    Launches and monitors Mochi plugins.
    """
    print("Starting Mochi Host...")
    plugin_process: Optional[subprocess.Popen] = None

    try:
        plugin_process = launch_animation_node()
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
        print(f"An error occurred while running the plugin: {exc}")
    finally:
        if plugin_process and plugin_process.poll() is None:
            print("Shutting down Animation Node plugin...")
            plugin_process.terminate()
            try:
                plugin_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Plugin did not exit promptly; forcing shutdown.")
                plugin_process.kill()


def main():
    run_host()


if __name__ == "__main__":
    main()
