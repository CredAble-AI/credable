import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from app.schemas.assessment import (
    AssessmentDataSnapshotReference,
    AssessmentSnapshotType,
)
from app.schemas.base import ApiModel
from app.schemas.consent import ConsentSourceType


class SnapshotRepository(Protocol):
    def get_snapshot(self, session_id: str) -> ApiModel | None: ...


@dataclass(frozen=True)
class SnapshotSource:
    source_type: ConsentSourceType
    snapshot_type: AssessmentSnapshotType
    repository: SnapshotRepository
    observed_at_field: str = "observed_at"


class AssessmentDataLineageService:
    def __init__(self, sources: tuple[SnapshotSource, ...]) -> None:
        self.sources = sources

    def list_references(self, session_id: str) -> list[AssessmentDataSnapshotReference]:
        references: list[AssessmentDataSnapshotReference] = []
        for source in self.sources:
            snapshot = source.repository.get_snapshot(session_id)
            if snapshot is None:
                continue
            snapshot_json = json.dumps(
                snapshot.model_dump(mode="json", by_alias=True),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            references.append(
                AssessmentDataSnapshotReference(
                    source_type=source.source_type,
                    snapshot_type=source.snapshot_type,
                    observed_at=getattr(snapshot, source.observed_at_field),
                    loaded_at=snapshot.loaded_at,
                    data_version=snapshot.data_version,
                    snapshot_hash=hashlib.sha256(snapshot_json.encode()).hexdigest(),
                )
            )
        return references
