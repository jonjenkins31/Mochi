"""Reusable scaffolding for building Mochi plugin nodes."""

from .bootstrap import (
    PROJECT_ROOT,
    setup_logging,
    load_config,
    build_optional_topics,
)

__all__ = ["PROJECT_ROOT", "setup_logging", "load_config", "build_optional_topics"]
