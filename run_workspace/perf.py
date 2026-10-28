from __future__ import annotations

import os
from time import perf_counter
from typing import Any


TRUE_VALUES = {"1", "true", "yes", "on"}


def perf_enabled() -> bool:
    return os.environ.get("GTT_PERF_LOG", "").strip().casefold() in TRUE_VALUES


def perf_now() -> float:
    return perf_counter()


def perf_ms(start: float) -> float:
    return (perf_counter() - start) * 1000.0


def log_perf(label: str, **values: Any) -> None:
    if not perf_enabled():
        return
    parts = []
    for key, value in values.items():
        if isinstance(value, float):
            parts.append(f"{key}={value:.1f}ms")
        else:
            parts.append(f"{key}={value}")
    print(f"[PERF] {label} " + " ".join(parts), flush=True)
