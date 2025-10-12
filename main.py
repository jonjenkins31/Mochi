"""
Root entry point for the Mochi host application.

This script launches the host logic, which in turn starts the animation node
and other plugins as needed.
"""

from mochi_host.host import run_host


if __name__ == "__main__":
    run_host()
