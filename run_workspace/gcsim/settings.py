from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from run_workspace.app_settings import (
    get_app_bool_setting,
    get_app_setting,
    set_app_bool_setting,
    set_app_setting,
)


GCSIM_BOOSTED_ENERGY_ENABLED_SETTING = "gcsim_boosted_energy_enabled"
DEFAULT_GCSIM_BOOSTED_ENERGY_LINE = "energy every interval=480,720 amount=100;"
WARNING_GCSIM_BOOSTED_ENERGY_LINE_APPENDED = (
    "gcsim_boosted_energy_line_appended_no_existing_energy_line"
)
GCSIM_OPTIMIZER_SET_GROUP_LIMIT_SETTING = "gcsim_optimizer_set_group_limit"
GCSIM_OPTIMIZER_BUILDS_PER_GROUP_SETTING = "gcsim_optimizer_builds_per_group"
GCSIM_OPTIMIZER_FAST_MODE_SETTING = "gcsim_optimizer_fast_mode"
GCSIM_OPTIMIZER_EXPANDED_LIMITS_SETTING = "gcsim_optimizer_expanded_limits"
GCSIM_OPTIMIZER_LIMIT_MIN = 1


def optimizer_output_limits(fast_mode: bool, expanded_limits: bool = False) -> tuple[int, int]:
    """Recommended limits, or high technical bounds after explicit opt-in."""
    if expanded_limits:
        return 50, 101
    return (10, 41) if fast_mode else (5, 11)


def optimizer_output_defaults(fast_mode: bool) -> tuple[int, int]:
    """Defaults for fresh/reset settings; total rows include the group leader."""
    return (5, 21) if fast_mode else (3, 3)


@dataclass(frozen=True, slots=True)
class GcsimRunSettings:
    boosted_energy_enabled: bool = False
    boosted_energy_line: str = DEFAULT_GCSIM_BOOSTED_ENERGY_LINE

    def to_dict(self) -> dict[str, Any]:
        return {
            "boosted_energy_enabled": self.boosted_energy_enabled,
            "boosted_energy_line": self.boosted_energy_line,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSettings:
    set_group_limit: int = 3
    builds_per_group: int = 3
    fast_mode: bool = False
    expanded_limits: bool = False


def effective_gcsim_optimizer_settings(
    *,
    settings_file: str | Path | None = None,
) -> GcsimOptimizerSettings:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    fast_mode = get_app_bool_setting(
        GCSIM_OPTIMIZER_FAST_MODE_SETTING,
        False,
        **kwargs,
    )
    expanded_limits = get_app_bool_setting(GCSIM_OPTIMIZER_EXPANDED_LIMITS_SETTING, False, **kwargs)
    group_max, build_max = optimizer_output_limits(fast_mode, expanded_limits)
    group_default, build_default = optimizer_output_defaults(fast_mode)
    return GcsimOptimizerSettings(
        set_group_limit=_bounded_optimizer_limit(
            GCSIM_OPTIMIZER_SET_GROUP_LIMIT_SETTING,
            group_default,
            maximum=group_max,
            **kwargs,
        ),
        builds_per_group=_bounded_optimizer_limit(
            GCSIM_OPTIMIZER_BUILDS_PER_GROUP_SETTING,
            build_default,
            maximum=build_max,
            **kwargs,
        ),
        fast_mode=fast_mode,
        expanded_limits=expanded_limits,
    )


def set_gcsim_optimizer_set_group_limit(
    value: int,
    *,
    settings_file: str | Path | None = None,
) -> None:
    _set_optimizer_limit(
        GCSIM_OPTIMIZER_SET_GROUP_LIMIT_SETTING,
        value,
        settings_file=settings_file,
    )


def set_gcsim_optimizer_builds_per_group(
    value: int,
    *,
    settings_file: str | Path | None = None,
) -> None:
    _set_optimizer_limit(
        GCSIM_OPTIMIZER_BUILDS_PER_GROUP_SETTING,
        value,
        settings_file=settings_file,
    )


def is_gcsim_optimizer_fast_mode_enabled(
    *,
    settings_file: str | Path | None = None,
) -> bool:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    return get_app_bool_setting(
        GCSIM_OPTIMIZER_FAST_MODE_SETTING,
        False,
        **kwargs,
    )


def set_gcsim_optimizer_fast_mode_enabled(
    enabled: bool,
    *,
    settings_file: str | Path | None = None,
) -> None:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    set_app_bool_setting(
        GCSIM_OPTIMIZER_FAST_MODE_SETTING,
        bool(enabled),
        **kwargs,
    )


def set_gcsim_optimizer_expanded_limits_enabled(
    enabled: bool,
    *,
    settings_file: str | Path | None = None,
) -> None:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    set_app_bool_setting(
        GCSIM_OPTIMIZER_EXPANDED_LIMITS_SETTING,
        bool(enabled),
        **kwargs,
    )
    if not enabled:
        settings = effective_gcsim_optimizer_settings(settings_file=settings_file)
        _set_optimizer_limit(
            GCSIM_OPTIMIZER_SET_GROUP_LIMIT_SETTING,
            settings.set_group_limit,
            settings_file=settings_file,
        )
        _set_optimizer_limit(
            GCSIM_OPTIMIZER_BUILDS_PER_GROUP_SETTING,
            settings.builds_per_group,
            settings_file=settings_file,
        )


def _bounded_optimizer_limit(
    key: str,
    default: int,
    *,
    maximum: int,
    settings_file: str | Path | None = None,
) -> int:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    value = get_app_setting(key, default, **kwargs)
    if isinstance(value, bool):
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return max(GCSIM_OPTIMIZER_LIMIT_MIN, min(maximum, normalized))


def _set_optimizer_limit(
    key: str,
    value: int,
    *,
    settings_file: str | Path | None = None,
) -> None:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    fast_mode = get_app_bool_setting(GCSIM_OPTIMIZER_FAST_MODE_SETTING, False, **kwargs)
    defaults = optimizer_output_defaults(fast_mode)
    default = defaults[0] if key == GCSIM_OPTIMIZER_SET_GROUP_LIMIT_SETTING else defaults[1]
    if isinstance(value, bool):
        normalized = default
    else:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            normalized = default
    group_max, build_max = optimizer_output_limits(
        fast_mode,
        get_app_bool_setting(GCSIM_OPTIMIZER_EXPANDED_LIMITS_SETTING, False, **kwargs),
    )
    limit_max = group_max if key == GCSIM_OPTIMIZER_SET_GROUP_LIMIT_SETTING else build_max
    normalized = max(GCSIM_OPTIMIZER_LIMIT_MIN, min(limit_max, normalized))
    set_app_setting(key, normalized, **kwargs)


@dataclass(frozen=True, slots=True)
class GcsimEnergyModeReport:
    enabled: bool
    line: str = ""
    shell_path: str = ""
    source_shell_path: str = ""
    replaced_existing_energy_line: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def mode(self) -> str:
        return "boosted" if self.enabled else "normal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "line": self.line,
            "shell_path": self.shell_path,
            "source_shell_path": self.source_shell_path,
            "replaced_existing_energy_line": self.replaced_existing_energy_line,
            "warnings": list(self.warnings),
        }


def is_gcsim_boosted_energy_enabled(
    *,
    settings_file: str | Path | None = None,
) -> bool:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    return get_app_bool_setting(
        GCSIM_BOOSTED_ENERGY_ENABLED_SETTING,
        False,
        **kwargs,
    )


def set_gcsim_boosted_energy_enabled(
    enabled: bool,
    *,
    settings_file: str | Path | None = None,
) -> None:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    set_app_bool_setting(
        GCSIM_BOOSTED_ENERGY_ENABLED_SETTING,
        bool(enabled),
        **kwargs,
    )


def effective_gcsim_run_settings(
    *,
    settings_file: str | Path | None = None,
) -> GcsimRunSettings:
    return GcsimRunSettings(
        boosted_energy_enabled=is_gcsim_boosted_energy_enabled(
            settings_file=settings_file,
        )
    )


def apply_gcsim_energy_settings_to_shell_text(
    shell_text: str,
    settings: GcsimRunSettings,
) -> tuple[str, GcsimEnergyModeReport]:
    if not settings.boosted_energy_enabled:
        return str(shell_text or ""), GcsimEnergyModeReport(enabled=False)

    line = str(settings.boosted_energy_line or "").strip()
    if not line.startswith("energy ") or not line.endswith(";"):
        raise ValueError("boosted energy line must be a complete GCSIM energy line")

    output_lines: list[str] = []
    replaced = False
    for existing in str(shell_text or "").splitlines():
        if not replaced and existing.strip().startswith("energy "):
            output_lines.append(line)
            replaced = True
        else:
            output_lines.append(existing)
    if not replaced:
        output_lines.append(line)
    warnings = () if replaced else (WARNING_GCSIM_BOOSTED_ENERGY_LINE_APPENDED,)
    return "\n".join(output_lines) + "\n", GcsimEnergyModeReport(
        enabled=True,
        line=line,
        replaced_existing_energy_line=replaced,
        warnings=warnings,
    )


def write_shell_with_gcsim_energy_settings(
    rotation_shell_path: str | Path,
    *,
    run_dir: str | Path,
    settings: GcsimRunSettings,
) -> tuple[Path, GcsimEnergyModeReport]:
    source_path = Path(rotation_shell_path)
    if not settings.boosted_energy_enabled:
        return source_path, GcsimEnergyModeReport(
            enabled=False,
            source_shell_path=str(source_path),
        )

    shell_text = source_path.read_text(encoding="utf-8-sig")
    replaced_text, report = apply_gcsim_energy_settings_to_shell_text(
        shell_text,
        settings,
    )
    destination_dir = Path(run_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / "rotation_shell.boosted_energy.txt"
    destination_path.write_text(replaced_text, encoding="utf-8")
    return destination_path, GcsimEnergyModeReport(
        enabled=report.enabled,
        line=report.line,
        shell_path=str(destination_path),
        source_shell_path=str(source_path),
        replaced_existing_energy_line=report.replaced_existing_energy_line,
        warnings=report.warnings,
    )
