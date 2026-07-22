from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...json_artifacts import read_json
from ...media_manifest import load_manifest
from ..contracts import RetrievalStep, SourceType
from .base import RetrieverAdapter, make_candidate


class LocalSparseRetriever(RetrieverAdapter):
    def retrieve(
        self,
        *,
        video_id: str,
        step: RetrievalStep,
        query_understanding: dict[str, Any],
    ) -> list[dict[str, Any]]:
        manifest = load_manifest(repo_root=self.repo_root, video_id=video_id)
        artifacts = manifest.get("artifacts", {})
        query_terms = _terms(step.query)
        rows: list[tuple[float, dict[str, Any], SourceType, str]] = []

        for path_key, item_key, source_type, id_key in [
            ("atoms_path", "atoms", SourceType.ATOM, "atom_id"),
            ("semantic_chunks_path", "chunks", SourceType.SEMANTIC_CHUNK, "chunk_id"),
            ("events_path", "events", SourceType.EVENT, "event_id"),
        ]:
            path = Path(artifacts.get(path_key, ""))
            if not path.exists():
                continue
            for item in read_json(path).get(item_key, []):
                text = _item_text(item)
                terms = _terms(text)
                overlap = query_terms & terms
                if not overlap:
                    continue
                score = len(overlap) / max(1, len(query_terms))
                rows.append((score, item, source_type, id_key))

        rows.sort(key=lambda row: row[0], reverse=True)
        candidates: list[dict[str, Any]] = []
        for rank, (score, item, source_type, id_key) in enumerate(rows[: step.top_k], start=1):
            source_id = item[id_key]
            candidates.append(
                make_candidate(
                    candidate_id=f"cand_{step.retriever}_{rank}",
                    video_id=video_id,
                    source_type=source_type,
                    source_id=source_id,
                    start_ms=item["start_ms"],
                    end_ms=item["end_ms"],
                    parent_chunk_id=item.get("semantic_chunk_id") or item.get("chunk_id"),
                    parent_event_id=item.get("parent_event_id") or item.get("event_id"),
                    text=_item_text(item),
                    transcript=item.get("transcript_text"),
                    entities=list(query_terms & _terms(_item_text(item))),
                    retriever=step.retriever,
                    rank=rank,
                    raw_score=score,
                    query_variant=step.query,
                    versions={"pipeline": manifest.get("pipeline_version", "")},
                )
            )
        return candidates


def _item_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key, ""))
        for key in ["title", "summary_text", "transcript_text", "text"]
        if item.get(key)
    )


def _terms(text: str) -> set[str]:
    stop = {"what", "where", "when", "why", "how", "does", "did", "the", "and", "from", "that", "this", "with", "about"}
    return {term.lower() for term in re.findall(r"[A-Za-z0-9]{3,}", text) if term.lower() not in stop}
