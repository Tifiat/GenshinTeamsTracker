from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import ARTIFACT_POSITIONS, ArtifactItem, parse_hoyolab_stat_value
from .queries import artifact_db_exists, list_all_artifacts, list_custom_sets
from .stat_types import CRIT_VALUE, PROC_COUNT


@dataclass(frozen=True, slots=True)
class ArtifactSetOption:
    set_uid: str
    set_name: str
    count: int
    icon_path: Path | None = None


@dataclass(frozen=True, slots=True)
class CustomSetOption:
    tag_id: int
    name: str
    count: int


class ArtifactBrowserStore:
    def __init__(
            self,
            *,
            database_exists: bool,
            artifacts: list[ArtifactItem],
            custom_sets: list[dict] | None = None,
    ):
        self.database_exists = database_exists

        self.artifacts_by_id: dict[int, ArtifactItem] = {
            artifact.id: artifact
            for artifact in artifacts
        }

        self.ids_by_pos: dict[int, list[int]] = {
            pos: []
            for pos in ARTIFACT_POSITIONS
        }

        self.ids_by_game_set: dict[str, set[int]] = {}
        self.ids_by_custom_set: dict[int, set[int]] = {}

        for artifact in artifacts:
            self.ids_by_pos.setdefault(artifact.pos, []).append(artifact.id)
            if artifact.set_uid:
                self.ids_by_game_set.setdefault(artifact.set_uid, set()).add(artifact.id)

            for tag in artifact.tags:
                self.ids_by_custom_set.setdefault(tag.id, set()).add(artifact.id)

        self.game_set_options = self._build_game_set_options(artifacts)
        self.custom_set_options = self._build_custom_set_options(
            artifacts,
            custom_sets or [],
        )

    @classmethod
    def load_from_db(cls) -> "ArtifactBrowserStore":
        exists = artifact_db_exists()
        artifacts = list_all_artifacts() if exists else []
        custom_sets = list_custom_sets() if exists else []
        return cls(
            database_exists=exists,
            artifacts=artifacts,
            custom_sets=custom_sets,
        )

    @classmethod
    def empty(cls) -> "ArtifactBrowserStore":
        return cls(database_exists=False, artifacts=[], custom_sets=[])

    def artifact(self, artifact_id: int) -> ArtifactItem:
        return self.artifacts_by_id[artifact_id]

    def ids_for_position(self, pos: int) -> list[int]:
        return list(self.ids_by_pos.get(pos, []))

    def ids_for_game_sets(self, set_uids: set[str]) -> set[int]:
        result: set[int] = set()

        for set_uid in set_uids:
            result.update(self.ids_by_game_set.get(set_uid, set()))

        return result

    def ids_for_custom_sets(self, tag_ids: set[int]) -> set[int]:
        result: set[int] = set()

        for tag_id in tag_ids:
            result.update(self.ids_by_custom_set.get(tag_id, set()))

        return result

    def sort_artifact_ids(
        self,
        artifact_ids: list[int],
        selected_stat_types: list[int],
    ) -> list[int]:
        selected_stat_types = list(selected_stat_types[:4])

        if not selected_stat_types:
            return sorted(
                artifact_ids,
                key=lambda artifact_id: self._default_artifact_sort_key(
                    self.artifact(artifact_id),
                ),
            )

        return sorted(
            artifact_ids,
            key=lambda artifact_id: self._artifact_sort_key(
                self.artifact(artifact_id),
                selected_stat_types,
            ),
        )

    @staticmethod
    def _artifact_stat_value(artifact: ArtifactItem, property_type: int) -> float:
        if property_type == CRIT_VALUE:
            return artifact.cv

        if property_type == PROC_COUNT:
            return float(artifact.proc_count)

        if artifact.main_property_type == property_type:
            return parse_hoyolab_stat_value(artifact.main_property_value)

        total = 0.0

        for substat in artifact.substats:
            if substat.property_type == property_type:
                total += parse_hoyolab_stat_value(substat.value)

        return total

    @staticmethod
    def _default_artifact_sort_key(artifact: ArtifactItem) -> tuple:
        return (
            -artifact.rarity,
            -artifact.level,
            -artifact.cv,
            artifact.set_name.casefold(),
            artifact.name.casefold(),
            artifact.id,
        )

    @staticmethod
    def _main_stat_priority(
        artifact: ArtifactItem,
        selected_stat_types: list[int],
    ) -> int:
        for index, property_type in enumerate(selected_stat_types):
            if property_type in {CRIT_VALUE, PROC_COUNT}:
                continue

            if artifact.main_property_type == property_type:
                return index

        return 999

    @classmethod
    def _artifact_sort_key(
        cls,
        artifact: ArtifactItem,
        selected_stat_types: list[int],
    ) -> tuple:
        main_stat_priority = cls._main_stat_priority(
            artifact,
            selected_stat_types,
        )

        stat_values = [
            -cls._artifact_stat_value(artifact, property_type)
            for property_type in selected_stat_types
        ]

        return (
            -artifact.rarity,
            main_stat_priority,
            *stat_values,
            -artifact.level,
            -artifact.cv,
            artifact.set_name.casefold(),
            artifact.name.casefold(),
            artifact.id,
        )

    @staticmethod
    def _build_game_set_options(artifacts: list[ArtifactItem]) -> list[ArtifactSetOption]:
        counts: dict[str, int] = {}
        names: dict[str, str] = {}
        icon_paths: dict[str, Path | None] = {}

        for artifact in artifacts:
            if not artifact.set_uid:
                continue

            counts[artifact.set_uid] = counts.get(artifact.set_uid, 0) + 1
            names.setdefault(artifact.set_uid, artifact.set_name)

            if artifact.set_uid not in icon_paths or icon_paths[artifact.set_uid] is None:
                icon_paths[artifact.set_uid] = artifact.set_icon_path

        return sorted(
            [
                ArtifactSetOption(
                    set_uid=set_uid,
                    set_name=names[set_uid],
                    count=count,
                    icon_path=icon_paths.get(set_uid),
                )
                for set_uid, count in counts.items()
            ],
            key=lambda item: item.set_name.casefold(),
        )

    @staticmethod
    def _build_custom_set_options(
            artifacts: list[ArtifactItem],
            custom_sets: list[dict],
    ) -> list[CustomSetOption]:
        if custom_sets:
            return [
                CustomSetOption(
                    tag_id=int(item["tag_id"]),
                    name=str(item["name"]),
                    count=int(item["count"] or 0),
                )
                for item in custom_sets
            ]

        counts: dict[int, int] = {}
        names: dict[int, str] = {}

        for artifact in artifacts:
            for tag in artifact.tags:
                counts[tag.id] = counts.get(tag.id, 0) + 1
                names.setdefault(tag.id, tag.name)

        return sorted(
            [
                CustomSetOption(
                    tag_id=tag_id,
                    name=names[tag_id],
                    count=count,
                )
                for tag_id, count in counts.items()
            ],
            key=lambda item: item.name.casefold(),
        )
