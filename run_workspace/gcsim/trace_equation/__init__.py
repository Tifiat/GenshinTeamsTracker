"""Forensic trace mathematics retained only for future Theory/All-Sets work.

The production Selected button does not import this package.  The compatibility
lookup below is lazy and limited to retained Theory/reference modules, so one
import no longer recreates the historical all-in-one trace graph.
"""

from importlib import import_module


_RETAINED_MODULES = (
    ".contracts",
    ".artifact_variable_objective",
    ".coarse_rotation_objective",
    ".rotation_objective",
    ".support_fast_objective",
    ".support_objective",
    ".support_replay",
    ".ranking",
    ".observed_snapshot",
    ".reaction_evidence",
    ".provider_evidence",
    ".health_evidence",
    ".state_evidence",
    ".source_dependencies",
    ".engine_adapter",
    ".codec",
)

__all__: tuple[str, ...] = ()


def __getattr__(name: str):
    for module_name in _RETAINED_MODULES:
        module = import_module(module_name, __name__)
        if hasattr(module, name):
            value = getattr(module, name)
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
