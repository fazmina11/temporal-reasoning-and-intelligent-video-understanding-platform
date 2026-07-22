from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..contracts import CandidateEvidence, RetrievalStep, SourceType, model_to_dict


class RetrieverAdapter(ABC):
    name: str

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    @abstractmethod
    def retrieve(
        self,
        *,
        video_id: str,
        step: RetrievalStep,
        query_understanding: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return normalized CandidateEvidence dictionaries."""


def source_type_from_hierarchy(value: str | None) -> SourceType:
    normalized = str(value or "").strip().lower()
    if normalized in {"atom", "atom_text", "atomic_span"}:
        return SourceType.ATOM
    if normalized in {"semantic_chunk", "semantic_chunk_text", "chunk"}:
        return SourceType.SEMANTIC_CHUNK
    if normalized in {"semantic_chunk_visual", "visual_chunk"}:
        return SourceType.VISUAL_CHUNK
    if normalized == "event":
        return SourceType.EVENT
    return SourceType.UNKNOWN


def candidate_to_dict(candidate: CandidateEvidence) -> dict[str, Any]:
    return model_to_dict(candidate)


def make_candidate(
    *,
    candidate_id: str,
    video_id: str,
    source_type: SourceType,
    source_id: str,
    start_ms: int,
    end_ms: int,
    retriever: str,
    rank: int,
    raw_score: float,
    query_variant: str,
    parent_chunk_id: str | None = None,
    parent_event_id: str | None = None,
    text: str | None = None,
    transcript: str | None = None,
    visual_summary: str | None = None,
    ocr_text: list[str] | None = None,
    entities: list[str] | None = None,
    media_refs: dict[str, Any] | None = None,
    versions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return candidate_to_dict(
        CandidateEvidence(
            candidate_id=candidate_id,
            video_id=video_id,
            source_type=source_type,
            source_id=source_id,
            start_ms=int(start_ms),
            end_ms=int(end_ms),
            parent_chunk_id=parent_chunk_id,
            parent_event_id=parent_event_id,
            text=text,
            transcript=transcript,
            visual_summary=visual_summary,
            ocr_text=ocr_text or [],
            entities=entities or [],
            media_refs=media_refs or {},
            retrieval={
                "retriever": retriever,
                "raw_score": round(float(raw_score), 6),
                "rank": int(rank),
                "query_variant": query_variant,
            },
            versions=versions or {},
        )
    )
