from __future__ import annotations

from typing import Any

from ...hierarchy_indexing import (
    COLLECTION_ATOMS_TEXT,
    COLLECTION_CHUNKS_TEXT,
    COLLECTION_CHUNKS_VISUAL,
    COLLECTION_EVENTS,
    EMBED_MODEL,
)
from ...hierarchy_retrieval import HierarchyRetriever
from ..contracts import RetrievalStep
from .base import RetrieverAdapter, make_candidate, source_type_from_hierarchy


COLLECTION_BY_RETRIEVER = {
    "transcript_dense": COLLECTION_ATOMS_TEXT,
    "atom_dense": COLLECTION_ATOMS_TEXT,
    "chunk_dense": COLLECTION_CHUNKS_TEXT,
    "semantic_chunk_dense": COLLECTION_CHUNKS_TEXT,
    "event_dense": COLLECTION_EVENTS,
    "visual_dense": COLLECTION_CHUNKS_VISUAL,
}


class ChromaDenseRetriever(RetrieverAdapter):
    def __init__(self, repo_root):
        super().__init__(repo_root)
        self.hierarchy = HierarchyRetriever(repo_root=repo_root)

    def retrieve(
        self,
        *,
        video_id: str,
        step: RetrievalStep,
        query_understanding: dict[str, Any],
    ) -> list[dict[str, Any]]:
        collection = COLLECTION_BY_RETRIEVER.get(step.retriever)
        if not collection:
            return []
        rows = self.hierarchy._query_collection(
            collection,
            step.query,
            video_id,
            n_results=step.top_k,
        )
        loaded = self.hierarchy._load_hierarchy(video_id)
        candidates: list[dict[str, Any]] = []
        for rank, row in enumerate(rows, start=1):
            expanded = self.hierarchy._expand(row, loaded)
            raw_score = expanded.get("score")
            if raw_score is None:
                raw_score = 1.0 - min(1.0, float(expanded.get("distance", 1.0)))
            candidates.append(
                make_candidate(
                    candidate_id=f"cand_{step.retriever}_{rank}",
                    video_id=video_id,
                    source_type=source_type_from_hierarchy(expanded.get("source_type")),
                    source_id=expanded["source_id"],
                    start_ms=expanded["start_ms"],
                    end_ms=expanded["end_ms"],
                    parent_chunk_id=expanded.get("parent_chunk_id"),
                    parent_event_id=expanded.get("parent_event_id"),
                    text=expanded.get("document") or expanded.get("transcript_text"),
                    transcript=expanded.get("transcript_text") or expanded.get("nearby_transcript"),
                    visual_summary=_visual_summary(expanded),
                    media_refs={
                        "frames": expanded.get("representative_frame_ids", []),
                        "clip_paths": expanded.get("clip_paths", []),
                    },
                    retriever=step.retriever,
                    rank=rank,
                    raw_score=float(raw_score),
                    query_variant=step.query,
                    versions={"embedding": EMBED_MODEL},
                )
            )
        return candidates


def _visual_summary(expanded: dict[str, Any]) -> str:
    records = expanded.get("visual_evidence") or []
    frame_count = sum(len(record.get("frame_references", [])) for record in records)
    clip_count = len(expanded.get("clip_paths") or [])
    if frame_count or clip_count:
        return f"{frame_count} frame references and {clip_count} clip references are attached."
    return ""
