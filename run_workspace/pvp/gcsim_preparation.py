"""Match-local preparation of PvP teams through the canonical GCSIM adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from run_workspace.gcsim.selected_team_config import (
    SelectedTeamFullConfigReport,
    build_selected_team_full_config_report,
)
from run_workspace.gcsim.settings import GcsimRunSettings


ReportBuilder = Callable[..., SelectedTeamFullConfigReport]


class PvpGcsimPreparation:
    """Prepare either PvP seat team without using account equipment fallbacks.

    The temporary root belongs to one match/seat adapter instance. Call
    :meth:`close` when that match-local equipment context is discarded.
    """

    def __init__(
        self,
        *,
        db_path: str | Path,
        report_builder: ReportBuilder | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self._report_builder = report_builder or build_selected_team_full_config_report
        self._temporary_directory: TemporaryDirectory | None = None
        self._output_root: Path | None = None
        self._closed = False

    @property
    def output_root(self) -> Path | None:
        """The owned temporary root, or ``None`` until the first preparation."""

        return self._output_root

    def prepare(
        self,
        *,
        team_index: int,
        selected_team: Mapping[str, Any],
        rotation_shell_text: str,
        run_settings: GcsimRunSettings,
        artifact_set_registry_source: str | Path,
    ) -> SelectedTeamFullConfigReport:
        normalized_team_index = _validated_team_index(team_index)
        if not _has_occupied_slots(selected_team):
            raise ValueError("selected PvP team has no occupied slots")
        if self._closed:
            raise RuntimeError("PvP GCSIM preparation is closed")

        output_root = self._ensure_output_root()
        run_dir = output_root / f"team-{normalized_team_index}"
        run_dir.mkdir(parents=True, exist_ok=True)
        rotation_shell_path = run_dir / "rotation_shell.txt"
        rotation_shell_path.write_text(rotation_shell_text, encoding="utf-8")

        return self._report_builder(
            db_path=self.db_path,
            selected_team=selected_team,
            team_index=normalized_team_index,
            rotation_shell_path=rotation_shell_path,
            run_dir=run_dir,
            write_config=True,
            run_settings=run_settings,
            artifact_set_registry_source=artifact_set_registry_source,
            allow_account_equipment_fallback=False,
        )

    def close(self) -> None:
        """Remove match-local GCSIM files; safe to call more than once."""

        if self._closed:
            return
        temporary_directory = self._temporary_directory
        if temporary_directory is not None:
            temporary_directory.cleanup()
        self._temporary_directory = None
        self._output_root = None
        self._closed = True

    def _ensure_output_root(self) -> Path:
        if self._temporary_directory is None:
            self._temporary_directory = TemporaryDirectory(prefix="gtt-pvp-gcsim-")
            self._output_root = Path(self._temporary_directory.name)
        assert self._output_root is not None
        return self._output_root


def _validated_team_index(team_index: int) -> int:
    if type(team_index) is not int or team_index not in (0, 1):
        raise ValueError("team_index must be the integer 0 or 1")
    return team_index


def _has_occupied_slots(selected_team: Mapping[str, Any]) -> bool:
    raw_slots = selected_team.get("slots")
    if not isinstance(raw_slots, (list, tuple)):
        return False
    for slot in raw_slots:
        if not isinstance(slot, Mapping):
            continue
        details = slot.get("character_details_data")
        details = details if isinstance(details, Mapping) else {}
        character = details.get("account_character") or slot.get("character")
        if isinstance(character, Mapping) and character:
            return True
        virtual = slot.get("gcsim_virtual_override")
        if isinstance(virtual, Mapping) and virtual:
            return True
    return False
