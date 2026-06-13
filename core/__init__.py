"""Shared infrastructure for Mochi.

Phase C (jaeger app format migration, 2026-06-13) emptied this
package's public surface: ``host_monitor`` and ``plugin_registry``
moved off the main-line boot path when ``main.py`` rebased onto
``JaegerApp``. The chassis now owns those roles —
``app.health.HealthCache`` for the SUB cache, ``app.supervisor``
for child-process lifecycle. The legacy modules remain in this
directory and stay importable by full path until Phase E removes
them; they are no longer re-exported here.
"""

__all__: list[str] = []
