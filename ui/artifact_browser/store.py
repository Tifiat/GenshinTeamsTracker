from __future__ import annotations

from dataclasses import dataclass

from .models import ARTIFACT_POSITIONS, ArtifactItem
from .queries import artifact_db_exists, list_all_artifacts


@dataclass(frozen=True, slots=True)
class ArtifactSetOption:
    set_id: int | None
    set_name: str
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

        for artifact in artifacts:
            self.ids_by_pos.setdefault(artifact.pos, []).append(artifact.id)

        self.set_options = self._build_set_options(artifacts)

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

    @staticmethod
    def _build_set_options(artifacts: list[ArtifactItem]) -> list[ArtifactSetOption]:
        counts: dict[int | None, int] = {}
        names: dict[int | None, str] = {}

        for artifact in artifacts:
            key = artifact.set_id
            counts[key] = counts.get(key, 0) + 1
            names.setdefault(key, artifact.set_name)

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