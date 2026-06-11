from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from run_workspace.app_settings import get_app_bool_setting, set_app_bool_setting


GCSIM_BOOSTED_ENERGY_ENABLED_SETTING = "gcsim_boosted_energy_enabled"
DEFAULT_GCSIM_BOOSTED_ENERGY_LINE = "energy every interval=480,720 amount=100;"
WARNING_GCSIM_BOOSTED_ENERGY_LINE_APPENDED = (
    "gcsim_boosted_energy_line_appended_no_existing_energy_line"
)


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
