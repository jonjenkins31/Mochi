"""Shared infrastructure for Mochi.

Phase E (jaeger app format migration, 2026-06-13) emptied this
package: ``host_monitor`` and ``plugin_registry`` were the only two
modules left and they no longer have callers — the chassis owns
their roles. ``app.health.HealthCache`` is the SUB cache;
``app.supervisor.Supervisor`` is the child-process lifecycle.

This package is kept as a directory so existing imports (``from core
import …``) don't fail noisily; the public surface is empty.
"""

__all__: list[str] = []
