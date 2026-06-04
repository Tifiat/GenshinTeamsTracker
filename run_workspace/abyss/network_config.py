"""Shared Abyss source-data network concurrency defaults."""

from __future__ import annotations


DEFAULT_ABYSS_SOURCE_NETWORK_WORKERS = 10


def normalize_network_workers(value: int | str | None) -> int:
    try:
        return max(1, int(value or DEFAULT_ABYSS_SOURCE_NETWORK_WORKERS))
    except (TypeError, ValueError):
        return DEFAULT_ABYSS_SOURCE_NETWORK_WORKERS
