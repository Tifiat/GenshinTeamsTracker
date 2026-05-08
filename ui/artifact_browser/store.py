from __future__ import annotations

from dataclasses import dataclass

from .models import ARTIFACT_POSITIONS, ArtifactItem
from .queries import artifact_db_exists, list_all_artifacts


@dataclass(frozen=True, slots=True)
class ArtifactSetOption:
    set_id: int | None
    set_name: str
    count: int


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

        self.ids_by_game_set: dict[int | None, set[int]] = {}
        self.ids_by_custom_set: dict[int, set[int]] = {}

        for artifact in artifacts:
            self.ids_by_pos.setdefault(artifact.pos, []).append(artifact.id)
            self.ids_by_game_set.setdefault(artifact.set_id, set()).add(artifact.id)

            for tag in artifact.tags:
                self.ids_by_custom_set.setdefault(tag.id, set()).add(artifact.id)

        self.game_set_options = self._build_game_set_options(artifacts)
        self.custom_set_options = self._build_custom_set_options(artifacts)

    @classmethod
    def load_from_db(cls) -> "ArtifactBrowserStore":
        exists = artifact_db_exists()
        artifacts = list_all_artifacts() if exists else []
        return cls(database_exists=exists, artifacts=artifacts)

    @classmethod
    def empty(cls) -> "ArtifactBrowserStore":
        return cls(database_exists=False, artifacts=[])

    def artifact(self, artifact_id: int) -> ArtifactItem:
        return self.artifacts_by_id[artifact_id]

    def ids_for_position(self, pos: int) -> list[int]:
        return list(self.ids_by_pos.get(pos, []))

    def ids_for_game_sets(self, set_ids: set[int | None]) -> set[int]:
        result: set[int] = set()

        for set_id in set_ids:
            result.update(self.ids_by_game_set.get(set_id, set()))

        return result

    def ids_for_custom_sets(self, tag_ids: set[int]) -> set[int]:
        result: set[int] = set()

        for tag_id in tag_ids:
            result.update(self.ids_by_custom_set.get(tag_id, set()))

        return result

    @staticmethod
    def _build_game_set_options(artifacts: list[ArtifactItem]) -> list[ArtifactSetOption]:
        counts: dict[int | None, int] = {}
        names: dict[int | None, str] = {}

        for artifact in artifacts:
            counts[artifact.set_id] = counts.get(artifact.set_id, 0) + 1
            names.setdefault(artifact.set_id, artifact.set_name)

        return sorted(
            [
                ArtifactSetOption(
                    set_id=set_id,
                    set_name=names[set_id],
                    count=count,
                )
                for set_id, count in counts.items()
            ],
            key=lambda item: item.set_name.casefold(),
        )

    @staticmethod
    def _build_custom_set_options(artifacts: list[ArtifactItem]) -> list[CustomSetOption]:
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