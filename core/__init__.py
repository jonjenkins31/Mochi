"""Shared infrastructure for Mochi (host monitoring + plugin loader).

After the JROS-style reorg, the bus + topics + messages + node_base
moved to transport/.  What stays here is what BOTH the agent + the
peripheral nodes consume — host monitoring + the plugin registry
that loads them.
"""

from .plugin_registry import PluginSpec, PluginProcess, load_plugin_specs
from .host_monitor import HostMonitor

__all__ = [
    "PluginSpec", "PluginProcess", "load_plugin_specs",
    "HostMonitor",
]
