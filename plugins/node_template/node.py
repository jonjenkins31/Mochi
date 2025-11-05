"""Skeleton Mochi node that can be used as a starting point for new plugins."""

from __future__ import annotations

import os
from typing import Sequence

from core.node_base import MochiNodeBase
from .bootstrap import (
    PROJECT_ROOT,
    build_optional_topics,
    load_config,
    setup_logging,
)


class TemplateNode(MochiNodeBase):
    """
    Minimal example implementation of a Mochi node.

    Subclass :class:`MochiNodeBase` and override the lifecycle hooks to integrate
    new functionality. This template does not render frames; it simply publishes
    a heartbeat event once per second.
    """

    def __init__(
        self,
        node_id: str,
        config: dict,
        project_root: str,
        optional_topics: Sequence[bytes] | None = None,
    ):
        super().__init__(node_id, config, project_root, optional_topics)
        self._last_event_emit = 0.0

    # ------------------------------------------------------------------ required hooks
    def _update_tick(self, timestamp: float) -> None:
        """Perform per-frame updates here."""
        if timestamp - self._last_event_emit >= 1.0:
            self.enqueue_event("template.heartbeat", uptime_s=timestamp - self.start_time)
            self._last_event_emit = timestamp

    def _render_tick(self, timestamp: float):  # type: ignore[override]
        """
        Return a memoryview/bytes of RGB pixel data when rendering is needed.
        Returning None skips frame publication, which is suitable for headless nodes.
        """
        return None

    def _process_node_command(self, command: str, parts: list[str]) -> None:
        """Handle control commands targeted at this node."""
        self.logger.info("Received command: %s", command)

    # ------------------------------------------------------------------ metadata
    def get_health_details(self) -> dict:
        return {
            "logical_size": {"width": 0, "height": 0},
            "status": "idle",
        }

    def get_meta_details(self) -> dict:
        return {
            "description": "Template Mochi node",
            "project_root": self.project_root,
        }

    # ------------------------------------------------------------------ teardown
    def on_shutdown(self) -> None:
        self.logger.info("TemplateNode shutdown complete.")


def main(optional_topics: Sequence[bytes] | None = None) -> None:
    logger = setup_logging("TemplateNode")
    config = load_config(logger=logger)
    node_config = config.get("node", {})

    node_id = os.environ.get("MOCHI_NODE_ID") or node_config.get("id") or "template"

    topics = list(optional_topics or [])
    topics.extend(build_optional_topics(node_config, logger=logger))
    if topics:
        seen: set[bytes] = set()
        deduped: list[bytes] = []
        for topic in topics:
            if topic not in seen:
                deduped.append(topic)
                seen.add(topic)
        topics = deduped

    node = TemplateNode(
        node_id=node_id,
        config=node_config,
        project_root=str(PROJECT_ROOT),
        optional_topics=topics or None,
    )
    node.run()


if __name__ == "__main__":
    main()
